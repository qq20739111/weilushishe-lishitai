# 后端缓存统一管理重构方案

## 概述

将 `src/main.py` 中分散的 5 类内存缓存（共 12+ 个全局/实例变量）统一到 `src/lib/CacheManager.py` 集中管理，新增 `/api/system/cache-stats` 监控接口。

---

## 一、当前缓存现状（待重构）

| 类别 | 变量 | 位置(main.py) | 问题 |
|------|------|---------------|------|
| **角色缓存** | `_role_cache` (dict) | L832 | 无界增长、无TTL |
| **设置缓存** | `_settings_cache` (dict\|None) | L999 | 失效点分散(L1060,2411,2735,2749,2779) |
| **DB缓存** | `JsonlDB._max_id_cache` (int\|None) x7 | L437 | 分散在实例内，无法统一监控 |
| **DB缓存** | `JsonlDB._count_cache` (int\|None) x7 | L438 | 同上 |
| **聊天缓存** | `_chat_messages` (list) | L2813 | 6个global变量耦合 |
| **聊天缓存** | `_chat_users` (dict) | L2814 | 同上 |
| **聊天缓存** | `_chat_guests` (dict) | L2815 | 同上 |
| **聊天缓存** | `_chat_current_size` (int) | L2816 | 同上 |
| **聊天缓存** | `_chat_msg_id` (int) | L2817 | 同上 |
| **聊天缓存** | `_chat_user_msg_count` (dict) | L2818 | 同上 |
| **运行时** | `_RUNTIME_TOKEN_SECRET` (str) | L25 | 固定值，仅纳入监控 |
| **运行时** | `_system_start_time` (float) | L22 | 固定值，仅纳入监控 |

---

## 二、CacheManager 设计

### 核心原则

- **零业务逻辑**：CacheManager 只管数据存储和策略执行，不理解业务含义
- **MicroPython 兼容**：不用 property、weakref、dataclass 等高级特性
- **最小开销**：对 dict/list 返回可变引用，调用方直接操作；对 int/None 用 get_val/set_val
- **统一监控**：所有缓存通过 `stats()` 获取状态

### 缓存槽类型

| 类型 | 存储方式 | 访问方式 | 适用对象 |
|------|---------|---------|---------|
| `dict` | 内部字典 | `store(name)` 返回引用 | role_cache, chat_users, chat_guests, chat_user_msg_count |
| `list` | 内部列表 | `store(name)` 返回引用 | chat_messages |
| `value` | 内部持有 | `get_val(name)` / `set_val(name, v)` | settings_cache, DB的max_id/count, chat_current_size, chat_msg_id |
| `const` | 内部持有 | `get_val(name)` 只读 | token_secret, start_time |

### 策略支持

- **TTL**（可选）：注册时指定秒数，`get_val/store` 自动检查过期并清除
- **max_size**（可选，仅 dict 类型）：超限时 FIFO 淘汰最早插入的条目
- **命中统计**：记录 hit/miss 次数，供 stats() 输出

### 类骨架（src/lib/CacheManager.py）

```python
import time
import gc

class CacheManager:
    """轻量级缓存管理器 - ESP32 MicroPython"""

    def __init__(self):
        self._data = {}    # {name: actual_data}
        self._cfg = {}     # {name: {type, ttl, max_size, created, hits, misses}}

    def register(self, name, ctype='dict', ttl=None, max_size=None, initial=None):
        """注册缓存槽。ctype: dict|list|value|const"""
        if ctype == 'dict':
            self._data[name] = initial if initial is not None else {}
        elif ctype == 'list':
            self._data[name] = initial if initial is not None else []
        elif ctype in ('value', 'const'):
            self._data[name] = initial
        self._cfg[name] = {
            'type': ctype,
            'ttl': ttl,
            'max_size': max_size,
            'ts': time.time(),     # 创建/最后重置时间
            'hits': 0,
            'misses': 0
        }

    def store(self, name):
        """获取 dict/list 类型缓存的可变引用（直接操作）"""
        cfg = self._cfg.get(name)
        if not cfg:
            return None
        if cfg['ttl'] and (time.time() - cfg['ts']) > cfg['ttl']:
            self._clear_slot(name)
            cfg['misses'] += 1
            return self._data[name]
        cfg['hits'] += 1
        return self._data[name]

    def get_val(self, name):
        """获取 value/const 类型缓存的当前值"""
        cfg = self._cfg.get(name)
        if not cfg:
            return None
        if cfg['type'] != 'const' and cfg['ttl'] and (time.time() - cfg['ts']) > cfg['ttl']:
            self._clear_slot(name)
            cfg['misses'] += 1
            return None
        cfg['hits'] += 1
        return self._data.get(name)

    def set_val(self, name, value):
        """设置 value 类型缓存的值"""
        cfg = self._cfg.get(name)
        if cfg and cfg['type'] != 'const':
            self._data[name] = value
            cfg['ts'] = time.time()

    def invalidate(self, name, key=None):
        """清除缓存。key=None清除整个槽，key!=None清除dict中指定key"""
        cfg = self._cfg.get(name)
        if not cfg:
            return
        if key is not None and cfg['type'] == 'dict':
            self._data[name].pop(key, None)
        else:
            self._clear_slot(name)

    def enforce_max_size(self, name):
        """强制执行 dict 类型的 max_size 限制（FIFO淘汰）"""
        cfg = self._cfg.get(name)
        if not cfg or not cfg['max_size'] or cfg['type'] != 'dict':
            return
        d = self._data[name]
        while len(d) > cfg['max_size']:
            first_key = next(iter(d))
            del d[first_key]

    def stats(self):
        """获取所有缓存的统计信息"""
        result = {}
        for name, cfg in self._cfg.items():
            data = self._data[name]
            if cfg['type'] == 'dict':
                size = len(data) if data else 0
            elif cfg['type'] == 'list':
                size = len(data) if data else 0
            else:
                size = 0 if data is None else 1
            total = cfg['hits'] + cfg['misses']
            result[name] = {
                'type': cfg['type'],
                'size': size,
                'ttl': cfg['ttl'],
                'max_size': cfg['max_size'],
                'hits': cfg['hits'],
                'misses': cfg['misses'],
                'hit_rate': round(cfg['hits'] / total * 100) if total > 0 else 0
            }
        return result

    def flush_all(self):
        """紧急内存释放：清除所有非 const 缓存"""
        for name, cfg in self._cfg.items():
            if cfg['type'] != 'const':
                self._clear_slot(name)
        gc.collect()

    def _clear_slot(self, name):
        """内部：清除单个缓存槽"""
        cfg = self._cfg[name]
        if cfg['type'] == 'dict':
            self._data[name].clear()
        elif cfg['type'] == 'list':
            self._data[name].clear()
        elif cfg['type'] == 'value':
            self._data[name] = None
        cfg['ts'] = time.time()


# 全局单例
cache = CacheManager()
```

---

## 三、各缓存迁移方案

### 3.1 角色缓存 _role_cache

**改动位置**：main.py L832-872 + L1774, L1856, L2735

```python
# 旧：
_role_cache = {}
def invalidate_role_cache(user_id=None): ...
def get_operator_role(request):
    if user_id in _role_cache: ...
    _role_cache[user_id] = role

# 新：
from lib.CacheManager import cache
cache.register('role', ctype='dict', ttl=1800, max_size=50)

def invalidate_role_cache(user_id=None):
    cache.invalidate('role', key=user_id)

def get_operator_role(request):
    ...
    role_store = cache.store('role')
    if user_id in role_store:
        return user_id, role_store[user_id]
    member = db_members.get_by_id(user_id)
    if member:
        role = member.get('role', 'member')
        role_store[user_id] = role
        cache.enforce_max_size('role')
        return user_id, role
```

- 删除 `global _role_cache` 及其原始声明
- `invalidate_role_cache()` 调用点（L1774, L1856, L2735）**不变**，函数签名保持一致

### 3.2 系统设置缓存 _settings_cache

**改动位置**：main.py L999-1062 + L1060, L2411, L2749, L2779

```python
# 旧：
_settings_cache = None
def invalidate_settings_cache(): ...
def get_settings(): global _settings_cache; ...
def save_settings(data): ...; invalidate_settings_cache()

# 新：
cache.register('settings', ctype='value', initial=None)

def invalidate_settings_cache():
    cache.set_val('settings', None)

def get_settings():
    cached = cache.get_val('settings')
    if cached is not None:
        return cached
    # ... 从文件加载 ...
    cache.set_val('settings', result)
    return result
```

- 删除 `global _settings_cache`
- `invalidate_settings_cache()` 调用点（L1060, L2411, L2749, L2779）**不变**

### 3.3 JsonlDB 实例缓存

**改动位置**：main.py L434-506, L669-671, L725-737 (JsonlDB类内部)

每个 JsonlDB 实例使用 filepath 作为命名空间注册两个 value 槽：

```python
class JsonlDB:
    def __init__(self, filepath, auto_migrate=True):
        self.filepath = filepath
        # 注册到 CacheManager（替代 self._max_id_cache / self._count_cache）
        self._ck_maxid = 'db:' + filepath + ':maxid'
        self._ck_count = 'db:' + filepath + ':count'
        cache.register(self._ck_maxid, ctype='value', initial=None)
        cache.register(self._ck_count, ctype='value', initial=None)
        self._ensure_dir()
        if auto_migrate:
            self._migrate_legacy_json()

    def get_max_id(self):
        cached = cache.get_val(self._ck_maxid)
        if cached is not None:
            return cached
        # ... 扫描文件 ...
        cache.set_val(self._ck_maxid, max_id)
        return max_id

    def append(self, record):
        # ... 写文件 ...
        cnt = cache.get_val(self._ck_count)
        if cnt is not None:
            cache.set_val(self._ck_count, cnt + 1)
        if 'id' in record:
            mid = cache.get_val(self._ck_maxid)
            if mid is not None:
                pid = int(record['id'])
                if pid > mid:
                    cache.set_val(self._ck_maxid, pid)

    def delete(self, id_val):
        # ... 重写文件 ...
        cnt = cache.get_val(self._ck_count)
        if cnt is not None and cnt > 0:
            cache.set_val(self._ck_count, cnt - 1)
        cache.set_val(self._ck_maxid, None)  # 删除后max_id可能变化

    def count(self):
        cached = cache.get_val(self._ck_count)
        if cached is not None:
            return cached
        # ... 扫描文件 ...
        cache.set_val(self._ck_count, count)
        return count
```

- 删除 `self._max_id_cache` 和 `self._count_cache`
- 7 个实例初始化时自动注册 14 个缓存槽

### 3.4 聊天室缓存

**改动位置**：main.py L2812-2818 + 所有 `global _chat_*` 函数（L2826, L2858, L2929, L2977, L3051）

注册 6 个缓存槽：

```python
# 替换原来的 6 个全局变量声明（L2812-2818）
cache.register('chat:messages', ctype='list')
cache.register('chat:users', ctype='dict')
cache.register('chat:guests', ctype='dict')
cache.register('chat:size', ctype='value', initial=0)
cache.register('chat:msg_id', ctype='value', initial=0)
cache.register('chat:msg_count', ctype='dict')
```

聊天函数改造模式（以 `_chat_cleanup` 为例）：

```python
def _chat_cleanup():
    """清理过期消息"""
    messages = cache.store('chat:messages')
    users = cache.store('chat:users')
    guests = cache.store('chat:guests')
    msg_count = cache.store('chat:msg_count')

    max_size = get_chat_max_size()
    current_size = cache.get_val('chat:size')

    while current_size > max_size and messages:
        old_msg = messages.pop(0)
        current_size -= _estimate_msg_size(old_msg)
        user_id = old_msg.get('user_id')
        cnt = msg_count.get(user_id, 1) - 1
        if cnt <= 0:
            msg_count.pop(user_id, None)
            users.pop(user_id, None)
            guests.pop(user_id, None)
        else:
            msg_count[user_id] = cnt

    cache.set_val('chat:size', current_size)
    gc.collect()
```

- 删除所有 `global _chat_*` 声明
- 删除 6 个全局变量声明
- 每个函数开头通过 `cache.store()` / `cache.get_val()` 获取缓存引用

### 3.5 运行时常量

```python
cache.register('runtime:token_secret', ctype='const',
               initial=ubinascii.hexlify(os.urandom(16)).decode('utf-8'))
cache.register('runtime:start_time', ctype='const', initial=time.time())
```

- 删除 `_RUNTIME_TOKEN_SECRET` 和 `_system_start_time` 全局变量
- 使用处改为 `cache.get_val('runtime:token_secret')` 和 `cache.get_val('runtime:start_time')`

---

## 四、新增 API 接口

### /api/system/cache-stats（需超级管理员权限）

**改动位置**：main.py，在系统管理API区域新增

```python
@api_route('/api/system/cache-stats')
@require_permission(ROLE_SUPER_ADMIN)
def api_cache_stats(request):
    """获取缓存统计信息"""
    gc.collect()
    stats = cache.stats()
    # 补充聊天室内存用量（cache.stats()只返回条目数，不含字节数）
    stats['chat:size_bytes'] = cache.get_val('chat:size')
    stats['chat:size_limit'] = get_chat_max_size()
    stats['memory_free'] = gc.mem_free()
    gc.collect()
    return stats
```

前端系统监控页面展示缓存统计（可选，作为后续任务）。

---

## 五、关键文件清单

| 文件 | 操作 | 改动说明 |
|------|------|---------|
| `src/lib/CacheManager.py` | **新建** | CacheManager 类，约 120 行 |
| `src/main.py` | **修改** | 导入CacheManager、删除分散缓存变量、改造缓存读写、新增API |

### main.py 改动区域明细

| 区域 | 行号 | 改动内容 |
|------|------|---------|
| 导入区 | L1-16 | 新增 `from lib.CacheManager import cache` |
| 运行时常量 | L22-25 | 改为 cache.register + cache.get_val |
| Token辅助函数 | 引用 `_RUNTIME_TOKEN_SECRET` 处 | 改为 `cache.get_val('runtime:token_secret')` |
| 系统运行时间 | 引用 `_system_start_time` 处 | 改为 `cache.get_val('runtime:start_time')` |
| JsonlDB类 | L434-438 | 删除实例变量，改用cache.register |
| JsonlDB.append | L469-484 | 改用 cache.get_val/set_val |
| JsonlDB.get_max_id | L486-506 | 改用 cache.get_val/set_val |
| JsonlDB.delete | L644-676 | 改用 cache.get_val/set_val |
| JsonlDB.count | L723-738 | 改用 cache.get_val/set_val |
| 角色缓存 | L831-872 | 删除全局变量，改用 cache.store/invalidate |
| 设置缓存 | L998-1062 | 删除全局变量，改用 cache.get_val/set_val |
| 聊天室缓存声明 | L2812-2818 | 替换为 cache.register 调用 |
| _chat_cleanup | L2824-2847 | 改用 cache.store/get_val/set_val |
| _allocate_guest_name | L2856-2883 | 改用 cache.store('chat:guests') |
| _get_guest_name | L2885-2890 | 改用 cache.store('chat:guests') |
| chat_get_messages | L2892-2908 | 改用 cache.store('chat:messages') |
| chat_get_users | L2910-2924 | 改用 cache.store |
| chat_join | L2926-2972 | 改用 cache.store，删除 global 声明 |
| chat_send_message | L2974-3046 | 改用 cache.store/get_val/set_val，删除 global |
| chat_leave | L3048-3068 | 改用 cache.store，删除 global |
| chat_status | L3070-3092 | 改用 cache.get_val/store |
| 新增 | 系统API区 | 新增 /api/system/cache-stats 接口 |

---

## 六、实施步骤

### Step 1: 创建 CacheManager.py
- 新建 `src/lib/CacheManager.py`
- 实现完整的 CacheManager 类（如上述骨架）
- 导出全局单例 `cache`

### Step 2: 迁移运行时常量
- 替换 `_RUNTIME_TOKEN_SECRET` 和 `_system_start_time`
- 涉及 main.py 顶部和引用这两个变量的函数

### Step 3: 迁移 JsonlDB 实例缓存
- 修改 `JsonlDB.__init__` 注册缓存槽
- 修改 `get_max_id`, `append`, `delete`, `count` 方法
- 删除 `self._max_id_cache` 和 `self._count_cache`

### Step 4: 迁移角色缓存
- 注册 `role` 缓存（TTL=1800, max_size=50）
- 改造 `get_operator_role()` 和 `invalidate_role_cache()`
- 删除 `_role_cache` 全局变量

### Step 5: 迁移设置缓存
- 注册 `settings` 缓存
- 改造 `get_settings()`, `save_settings()`, `invalidate_settings_cache()`
- 删除 `_settings_cache` 全局变量

### Step 6: 迁移聊天室缓存
- 注册 6 个聊天缓存槽
- 改造所有聊天室相关函数（删除 global 声明，改用 cache 方法）
- 删除 6 个 `_chat_*` 全局变量

### Step 7: 新增缓存监控 API
- 新增 `/api/system/cache-stats` 接口（require_permission ROLE_SUPER_ADMIN）

### Step 8: 清理与验证
- 确认无残留的旧缓存变量引用
- 全局搜索 `_role_cache`, `_settings_cache`, `_chat_messages` 等确认已清除

---

## 七、验证方案

### 功能验证

1. **角色缓存**：登录后访问需权限的API，验证鉴权正常；修改成员角色后验证缓存失效
2. **设置缓存**：修改系统设置（系统名称、聊天开关等），验证生效
3. **DB缓存**：新增/删除诗歌、成员，验证ID自增和计数正确
4. **聊天缓存**：发送消息、加入/离开聊天室、游客过期，验证功能正常
5. **缓存监控**：访问 `/api/system/cache-stats`，验证返回所有缓存统计

### 内存验证

1. 启动后访问 `/api/system/info` 记录初始内存
2. 执行各功能操作后再次查看内存，确认无异常增长
3. 模拟大量操作后查看 role_cache 是否正确淘汰（max_size=50）

### 回归验证

1. 诗歌增删改查、分页、搜索
2. 成员管理、权限变更
3. 活动/事务/财务增删改查
4. 聊天室消息发送、增量获取、在线用户列表
5. 系统设置修改与保存
6. 数据备份导出/导入
7. 登录/登出

---

## 八、风险控制

- **回退方案**：每个 Step 完成后可独立验证，发现问题可逐步回退
- **关键风险**：聊天室缓存迁移改动面最大（5个函数 x 6个变量），需逐函数仔细核对
- **MicroPython 兼容**：CacheManager 仅使用基础语法（dict, list, time, gc），无兼容风险
- **内存开销**：CacheManager 自身约增加 2-3KB 内存（元数据字典），可接受
