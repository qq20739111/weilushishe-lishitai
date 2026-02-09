# 数据备份导入导出功能修复方案

## 问题摘要

`settings` 表的**导出包含 11 个字段**，但**导入只恢复了 4 个字段**，导致备份恢复后丢失 7 个系统设置。

## 问题详情

### config.json 中的全部 24 个配置字段分布

| 分组 | 字段 | 导出 | 导入 |
|------|------|------|------|
| **settings (11)** | `custom_member_fields` | ✅ | ✅ |
| | `password_salt` | ✅ | ✅ |
| | `points_name` | ✅ | ✅ |
| | `system_name` | ✅ | ✅ |
| | `token_expire_days` | ✅ | ❌ 缺失 |
| | `maintenance_mode` | ✅ | ❌ 缺失 |
| | `allow_guest` | ✅ | ❌ 缺失 |
| | `chat_enabled` | ✅ | ❌ 缺失 |
| | `chat_guest_max` | ✅ | ❌ 缺失 |
| | `chat_max_users` | ✅ | ❌ 缺失 |
| | `chat_cache_size` | ✅ | ❌ 缺失 |
| **wifi_config (10)** | wifi_ssid, wifi_password, sta_use_static_ip, sta_ip, sta_subnet, sta_gateway, sta_dns, ap_ssid, ap_password, ap_ip | ✅ | ✅ |
| **system_config (3)** | debug_mode, watchdog_enabled, watchdog_timeout | ✅ | ✅ |
| **JSONL 业务数据 (7表)** | members, poems, activities, tasks, finance, points_logs, login_logs | ✅ | ✅ |

## 修复方案

### 核心思路

提取一个全局常量 `SETTINGS_KEYS`，在 `get_settings()`、`save_settings()` 和 `backup_import_table()` 三处统一引用，避免未来新增字段时再次遗漏。

### 修改文件

**`src/main.py`** — 唯一需要修改的文件

### 步骤 1: 定义全局常量

在 `main.py` 顶部常量区域（约第 740 行附近，角色常量定义处）新增：

```python
# 系统设置字段列表（get_settings / save_settings / backup 共用）
SETTINGS_KEYS = [
    'custom_member_fields', 'password_salt', 'points_name', 'system_name',
    'token_expire_days', 'maintenance_mode', 'allow_guest',
    'chat_enabled', 'chat_guest_max', 'chat_max_users', 'chat_cache_size'
]
```

### 步骤 2: 修改 save_settings()（第 1001 行）

**当前代码**:
```python
for key in ['custom_member_fields', 'password_salt', 'points_name', 'system_name', 'token_expire_days',
            'maintenance_mode', 'allow_guest', 'chat_enabled', 'chat_guest_max', 'chat_max_users', 'chat_cache_size']:
```

**修改为**:
```python
for key in SETTINGS_KEYS:
```

### 步骤 3: 修改 backup_import_table() 中 settings 导入（第 2451 行）— 核心修复

**当前代码**:
```python
for key in ['custom_member_fields', 'password_salt', 'points_name', 'system_name']:
```

**修改为**:
```python
for key in SETTINGS_KEYS:
```

### 不修改的部分

- `get_settings()` 函数（第 965-976 行）：因为它返回一个带默认值的字典，无法简单用列表替代，保持现有逻辑不变。但其返回的键需与 `SETTINGS_KEYS` 保持一致（代码审查时人工确认）。
- WiFi 配置和系统配置的导入导出：已完整覆盖，无需修改。
- 前端代码：无需修改，前端只负责传递数据。
- JSONL 数据表：导入导出均正常。

## 验证方法

1. 检查 `SETTINGS_KEYS` 常量包含的 11 个字段与 `get_settings()` 返回的 11 个键完全一致
2. 检查 `save_settings()` 和 `backup_import_table()` 的 settings 分支都使用 `SETTINGS_KEYS`
3. 手动验证：在系统中修改所有 11 个设置字段为非默认值 -> 导出备份 -> 重置设置 -> 导入备份 -> 确认所有 11 个字段都已恢复
