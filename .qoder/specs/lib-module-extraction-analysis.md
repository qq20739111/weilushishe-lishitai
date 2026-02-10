# main.py 模块提取方案

## 现状

- `src/main.py` 共 **3,297 行**
- 现有 lib 模块 7 个：BreathLED, CacheManager, Logger, SystemStatus, Watchdog, WifiConnector, microdot

## 实施范围

提取 P0 级别的 4 个模块（Validator、JsonlDB、Settings、Auth），依赖方式为**直接 import**。
Settings 虽原属 P1，但它是 Auth 的必要前置依赖（`hash_password`/`_get_token_expire_seconds` 都调用 `get_settings()`），因此纳入本次实施。

---

## 完整分析（P0 + P1 + 不建议提取）

### P0 - 本次实施

#### 1. Validator.py - 数据验证模块
- **来源**: main.py 行 192-359（~168 行）
- **函数**: `validate_phone`, `validate_password_strength`, `validate_name`, `validate_alias`, `validate_birthday`, `validate_points`, `validate_custom_fields`
- **依赖**: 无
- **理由**: 纯函数，零耦合，提取后只改 import

#### 2. JsonlDB.py - JSONL 数据库引擎
- **来源**: main.py 行 161-166 (`file_exists`) + 行 480-793（~320 行）
- **内容**: `JsonlDB` 类 + `file_exists` 辅助函数
- **依赖**: `json`, `os`, `gc` + `lib.Logger` + `lib.CacheManager`
- **理由**: 核心基础组件，7 个 db 实例复用，完全独立于路由逻辑

#### 3. Settings.py - 系统设置管理
- **来源**: main.py 行 369（`DEFAULT_TOKEN_EXPIRE_DAYS`）+ 行 822-827（`SETTINGS_KEYS`）+ 行 1055-1118（~70 行）
- **内容**: `SETTINGS_KEYS`, `DEFAULT_TOKEN_EXPIRE_DAYS`, `get_settings`, `save_settings`, `invalidate_settings_cache`
- **依赖**: `json`, `os` + `lib.CacheManager` + `lib.Logger`
- **理由**: Auth 的必要前置依赖；被全系统大量引用

#### 4. Auth.py - 认证与 Token 管理
- **来源**: main.py 行 168-186 + 行 371-451（~100 行）
- **内容**: `hash_password`, `verify_password`, `generate_token`, `verify_token`, `check_token`, `simple_unquote`, `_get_token_expire_seconds`, `_get_token_secret`
- **依赖**: `uhashlib`, `ubinascii`, `time`, `json` + `lib.Logger` + `lib.CacheManager` + `lib.Settings` + `lib.microdot.Response`
- **理由**: 安全核心模块，逻辑内聚；集中管理便于审计

### P1 - 后续可选（本次不实施）

#### Permission.py - 权限与角色管理
- **来源**: main.py 行 817-1009（~193 行）
- **内容**: 角色常量、`can_assign_role`, `can_manage_member`, `get_operator_role`, `require_login`, `require_permission` 装饰器等
- **依赖**: Auth + CacheManager + db_members 实例
- **提取难点**: `get_operator_role` 需要遍历 `db_members`，装饰器需要 `Response`；可在 Auth 和 JsonlDB 稳定后再提取

#### ChatRoom.py - 聊天室模块
- **来源**: main.py 行 2950-3262（~313 行，含 6 个路由）
- **依赖**: cache, Settings, db_members, get_operator_role, api_route 装饰器
- **提取难点**: 路由注册需传入 `app` 实例；需设计 `register_chat_routes(app, deps)` 模式

### 不建议提取

| 功能块 | 行数 | 理由 |
|--------|------|------|
| 财务辅助函数 | ~91 | 仅服务 3 个路由，`_` 前缀私有函数，紧耦合 |
| WiFi 配置函数 | ~40 | 代码量过小 |
| 缓存失效管理 | ~36 | 全局缓存策略协调点，代码量小 |
| 看门狗定时器 | ~30 | 与启动流程耦合，代码量小 |
| API 路由装饰器 | ~58 | 核心调度逻辑，依赖全局状态过多 |
| 日志记录函数 | ~41 | 仅是 db 写入封装 |
| 各业务路由 | ~1800 | 与 app 实例绑定，拆分增加复杂度 |

---

## 实施计划（4 个 P0 模块）

### 提取顺序（按依赖链）

```
1. Validator.py   -- 零依赖
2. JsonlDB.py     -- 依赖 Logger + CacheManager（已有）
3. Settings.py    -- 依赖 CacheManager + Logger（已有）
4. Auth.py        -- 依赖 Settings + CacheManager + Logger + microdot
```

### Step 1: 创建 `src/lib/Validator.py`

**操作**:
- 从 main.py 行 192-359 迁移全部 validate_* 函数
- main.py 添加: `from lib.Validator import validate_phone, validate_password_strength, validate_name, validate_alias, validate_birthday, validate_points, validate_custom_fields`
- 删除 main.py 中对应的函数定义

**文件结构**:
```python
# src/lib/Validator.py
# 数据验证工具集

def validate_phone(phone): ...
def validate_password_strength(password): ...
def validate_name(name, max_length=10): ...
def validate_alias(alias, max_length=10): ...
def validate_birthday(birthday): ...
def validate_points(points): ...
def validate_custom_fields(custom_data, custom_fields_config): ...
```

### Step 2: 创建 `src/lib/JsonlDB.py`

**操作**:
- 从 main.py 迁移 `file_exists` (行 161-166) 和 `JsonlDB` 类 (行 480-793)
- main.py 添加: `from lib.JsonlDB import JsonlDB, file_exists`
- 删除 main.py 中对应代码
- db_* 实例化语句（行 797-803）保留在 main.py

**文件结构**:
```python
# src/lib/JsonlDB.py
import json
import os
import gc
from lib.Logger import debug, error
from lib.CacheManager import cache

def file_exists(path): ...

class JsonlDB:
    def __init__(self, filepath, auto_migrate=True): ...
    def _ensure_dir(self): ...
    def _migrate_legacy_json(self): ...
    def append(self, record): ...
    def get_max_id(self): ...
    def fetch_page(self, page=1, limit=10, ...): ...
    def update(self, id_val, update_func): ...
    def delete(self, id_val): ...
    def get_all(self): ...
    def get_by_id(self, id_val): ...
    def iter_records(self): ...
    def count(self): ...
```

### Step 3: 创建 `src/lib/Settings.py`

**操作**:
- 从 main.py 迁移:
  - `DEFAULT_TOKEN_EXPIRE_DAYS` (行 369)
  - `SETTINGS_KEYS` (行 823-827)
  - 缓存注册 `cache.register('settings', ...)` (行 1055)
  - `invalidate_settings_cache` (行 1057-1059)
  - `get_settings` (行 1061-1098)
  - `save_settings` (行 1100-1118)
- main.py 添加: `from lib.Settings import get_settings, save_settings, invalidate_settings_cache, SETTINGS_KEYS, DEFAULT_TOKEN_EXPIRE_DAYS`
- 删除 main.py 中对应代码

**文件结构**:
```python
# src/lib/Settings.py
import json
from lib.Logger import error
from lib.CacheManager import cache

DEFAULT_TOKEN_EXPIRE_DAYS = 30
SETTINGS_KEYS = [
    'custom_member_fields', 'password_salt', 'points_name', 'system_name',
    'token_expire_days', 'site_open', 'allow_guest',
    'chat_enabled', 'chat_guest_max', 'chat_max_users', 'chat_cache_size'
]

cache.register('settings', ctype='value', ttl=3600, initial=None)

def invalidate_settings_cache(): ...
def get_settings(): ...
def save_settings(data): ...
```

### Step 4: 创建 `src/lib/Auth.py`

**操作**:
- 从 main.py 迁移:
  - `hash_password` (行 168-177)
  - `verify_password` (行 179-186)
  - `_get_token_expire_seconds` (行 371-375)
  - `_get_token_secret` (行 377-379)
  - `generate_token` (行 381-398)
  - `verify_token` (行 400-434)
  - `check_token` (行 436-451)
  - `simple_unquote` (行 453-475)
- main.py 添加: `from lib.Auth import hash_password, verify_password, generate_token, verify_token, check_token, simple_unquote`
- 删除 main.py 中对应代码

**文件结构**:
```python
# src/lib/Auth.py
import json
import time
import uhashlib
import ubinascii
from lib.Logger import debug
from lib.CacheManager import cache
from lib.Settings import get_settings, DEFAULT_TOKEN_EXPIRE_DAYS
from lib.microdot import Response

def hash_password(password): ...
def verify_password(password, hashed): ...
def _get_token_expire_seconds(): ...
def _get_token_secret(): ...
def generate_token(user_id): ...
def verify_token(token): ...
def check_token(request): ...
def simple_unquote(s): ...
```

### Step 5: 更新 main.py 的 import 区块

main.py 顶部 import 变更为：
```python
import json
import os
import gc
import network
import time
import machine
import uhashlib        # 可能仍有其他地方使用
import ubinascii       # 同上
from lib.microdot import Microdot, Response, send_file
from lib.Logger import log, debug, info, warn, error
from lib.Watchdog import watchdog
from lib.SystemStatus import status_led
from lib.CacheManager import cache
from lib.Validator import (validate_phone, validate_password_strength,
    validate_name, validate_alias, validate_birthday,
    validate_points, validate_custom_fields)
from lib.JsonlDB import JsonlDB, file_exists
from lib.Settings import (get_settings, save_settings,
    invalidate_settings_cache, SETTINGS_KEYS, DEFAULT_TOKEN_EXPIRE_DAYS)
from lib.Auth import (hash_password, verify_password, generate_token,
    verify_token, check_token, simple_unquote)
```

**注意**: 需检查 main.py 中是否还有其他地方直接使用 `uhashlib`/`ubinascii`，如无则可移除顶部 import。

---

## ESP32 内存影响

- 4 个新模块 import 增量：约 6-10KB SRAM
- main.py 减小后编译开销降低：约 -5-8KB
- **净影响**: 接近中性（±3KB）
- 可用 `mpy-cross` 预编译进一步优化

## 预期收益

- main.py 从 3,297 行减少到约 **2,600 行**（减少 ~21%）
- 核心基础组件（DB、Auth、Validator、Settings）独立可维护
- 安全代码（Auth）集中管理，便于审计
- 为后续 P1 提取（Permission、ChatRoom）打好基础

## 验证方法

1. 将修改后的文件上传到 ESP32
2. 重启设备，观察串口日志确认无 ImportError
3. 测试关键 API:
   - `GET /api/poems` — 验证 JsonlDB 分页正常
   - `POST /api/login` — 验证 Auth 登录/Token 正常
   - `POST /api/members` — 验证 Validator 数据验证正常
   - `GET /api/settings/system` — 验证 Settings 读取正常
   - `POST /api/settings/system` — 验证 Settings 写入正常
4. 通过 `GET /api/system/info` 对比重构前后 `gc.mem_free()` 值

## 涉及文件

| 操作 | 文件路径 |
|------|---------|
| 新建 | `src/lib/Validator.py` |
| 新建 | `src/lib/JsonlDB.py` |
| 新建 | `src/lib/Settings.py` |
| 新建 | `src/lib/Auth.py` |
| 修改 | `src/main.py`（删除已迁移代码，更新 import）|
