# 围炉诗社·理事台 - 系统资源优化方案

## 概述

在不改变业务逻辑和功能的前提下，对整个项目进行系统性性能优化。涵盖：补充 gc.collect()、减少文件 I/O、引入缓存机制、提升代码效率、降低内存泄漏风险、前端请求去重。

按优先级分为 P0（零风险速赢）、P1（低风险缓存）、P2（中等风险高级缓存）、P3（前端优化）四个阶段。

---

## 涉及文件

| 文件 | 阶段 | 改动量 |
|------|------|--------|
| `src/main.py` | P0/P1/P2 | ~30处 |
| `src/boot.py` | P0 | 3处 |
| `src/static/app.js` | P3 | ~2处 |

---

## P0: 零风险速赢优化

### P0-1: 补充缺失的 gc.collect()

**5处修改，每处1行：**

1. **`src/main.py:1874`** - `yearly_points_ranking()` return 前
   - 在 `ranking.sort(...)` 之后、`return ranking[:10]` 之前插入 `gc.collect()`
   - 原因：构建了 member_yearly_points 字典 + member_alias_map 字典 + ranking 列表

2. **`src/main.py:974`** - `record_login_log()` 日志清理完成后
   - 在 `except` 块末尾（第974行之后）插入 `gc.collect()`
   - 原因：get_all() 全量加载 + 临时文件写入 + 文件替换

3. **`src/boot.py:48`** - NTP同步成功后
   - 在 `info(f"NTP时间同步成功...")` 后、`return True` 前插入 `gc.collect()`

4. **`src/boot.py:111`** - WiFi连接成功后
   - 在 `break` 前插入 `gc.collect()`
   - 释放连接过程中产生的临时对象

5. **`src/boot.py:62`** - load_config() 加载配置后
   - 在 `config = load_config()` 返回后、使用 config 之前不方便插入
   - 改为：在 `load_config()` 函数内部，`json.load(f)` 后先赋值局部变量再返回，并在 connect_wifi() 中 WiFi 参数提取完毕后（第78行之后）插入 `gc.collect()` 释放 config 中未使用的字段

### P0-2: 优化 _get_member_display_name() 使用 db.get_by_id()

**文件**: `src/main.py:2817-2827`

当前实现手动打开 members.jsonl 逐行扫描，应改用已有的 `db_members.get_by_id()`：

```python
def _get_member_display_name(member_id):
    """获取成员显示名称（优先雅号）"""
    member = db_members.get_by_id(member_id)
    if member:
        return member.get('alias') or member.get('name') or '未知'
    return '未知'
```

### P0-3: 预定义 api_route 装饰器中的错误响应对象

**文件**: `src/main.py:74-111`

在装饰器外部预定义常量响应（约第73行前）：

```python
_RESP_MAINTENANCE = Response('{"error": "系统维护中，请稍后再试"}', 503, {'Content-Type': 'application/json'})
_RESP_GUEST_DENIED = Response('{"error": "请先登录后访问"}', 401, {'Content-Type': 'application/json'})
```

装饰器内部（第93-94行、第102-103行）直接返回预定义对象，同时删除内部多余的 `from lib.microdot import Response` 导入语句。

### P0-4: 优化 _estimate_msg_size() 避免完整 JSON 序列化

**文件**: `src/main.py:2790-2792`

用字段长度估算替代 `json.dumps()`：

```python
def _estimate_msg_size(msg):
    """估算单条消息占用的内存大小（快速估算）"""
    size = 80  # JSON结构基础开销
    size += len(str(msg.get('content', '')))
    size += len(str(msg.get('user_name', '')))
    return size
```

### P0-5: 聊天消息列表改用 deque 优化 pop(0)

**文件**: `src/main.py`

ESP32 MicroPython v1.25.0 支持 `collections.deque`（但不支持 maxlen）。

1. 文件顶部导入区添加：`from collections import deque`
2. 第2784行：`_chat_messages = []` 改为 `_chat_messages = deque((), 500)`
   - 注意：MicroPython deque 构造函数需要 `(iterable, maxlen)`，但不支持 maxlen 自动淘汰
   - 实际上 MicroPython 的 deque 支持有限，仅支持 `append()` 和 `popleft()`
   - 修改：使用 `deque((), 2000)` 预留足够槽位（deque 在 MicroPython 中需要指定最大长度）
3. 第2801行：`_chat_messages.pop(0)` 改为 `_chat_messages.popleft()`
4. 第2877行 `list(_chat_messages)` - 保持不变，deque 支持迭代转 list
5. 消息追加的 `.append()` - 保持不变

**注意**: MicroPython 的 deque 行为与 CPython 不同，构造函数 `deque(iterable, maxlen)` 中 maxlen 是必需参数且固定。如果实测发现兼容性问题，回退为 list 并保留 `pop(0)` 即可（这是最低优先级的 P0 项）。

---

## P1: 低风险缓存优化

### P1-1: JsonlDB 添加 max_id 缓存

**文件**: `src/main.py` JsonlDB 类 (432-718行)

修改点：

1. `__init__()` (433行) 添加：`self._max_id_cache = None`

2. `get_max_id()` (475行) 改为缓存优先：
   ```python
   def get_max_id(self):
       if self._max_id_cache is not None:
           return self._max_id_cache
       # ... 原有扫描逻辑 ...
       self._max_id_cache = max_id
       return max_id
   ```

3. `append()` (465行) 写入成功后更新缓存：
   ```python
   if 'id' in record:
       rid = int(record['id'])
       if self._max_id_cache is None or rid > self._max_id_cache:
           self._max_id_cache = rid
   ```

4. `update()` / `delete()` 文件重写后重置：`self._max_id_cache = None`

### P1-2: JsonlDB 添加 count 缓存

**文件**: `src/main.py` JsonlDB 类

修改点：

1. `__init__()` 添加：`self._count_cache = None`

2. `count()` (705行) 改为缓存优先：
   ```python
   def count(self):
       if self._count_cache is not None:
           return self._count_cache
       # ... 原有计数逻辑 ...
       self._count_cache = count
       return count
   ```

3. `append()` 成功后：
   ```python
   if self._count_cache is not None:
       self._count_cache += 1
   ```

4. `delete()` 成功后：
   ```python
   if self._count_cache is not None:
       self._count_cache -= 1
   ```

5. `update()` 完成后：保持不变（update不改变记录数）

**收益**: `sys_stats()` (2564行) 同时调用5个 count()，首次后全部走缓存。

### P1-3: 优化 login_route() 减少字典复制

**文件**: `src/main.py:1908-1913`

将 `m.copy()` + `del password` 替换为显式构造：

```python
token, expires_in = generate_token(m.get('id'))
m_safe = {
    'id': m.get('id'),
    'name': m.get('name'),
    'alias': m.get('alias', ''),
    'phone': m.get('phone'),
    'role': m.get('role'),
    'points': m.get('points', 0),
    'birthday': m.get('birthday', ''),
    'joined_at': m.get('joined_at', ''),
    'custom': m.get('custom', {}),
    'token': token,
    'expires_in': expires_in
}
```

需要仔细检查前端 `app.js` 中 login 响应使用了哪些字段，确保不遗漏。

### P1-4: 优化 _chat_cleanup 中 any() 线性扫描

**文件**: `src/main.py` 聊天系统 (2764-3081行)

1. 第2788行附近添加全局计数器：
   ```python
   _chat_user_msg_count = {}  # {user_id: 消息条数}
   ```

2. 消息发送时（chat_send_message 中 append 消息后）递增：
   ```python
   _chat_user_msg_count[user_id] = _chat_user_msg_count.get(user_id, 0) + 1
   ```

3. `_chat_cleanup()` 中用计数器替代 any()：
   ```python
   user_id = old_msg.get('user_id')
   _chat_user_msg_count[user_id] = _chat_user_msg_count.get(user_id, 1) - 1
   if _chat_user_msg_count.get(user_id, 0) <= 0:
       _chat_user_msg_count.pop(user_id, None)
       _chat_users.pop(user_id, None)
       _chat_guests.pop(user_id, None)
   ```

   复杂度从 O(n*m) 降至 O(n)。

---

## P2: 中等风险高级缓存

### P2-1: 成员名称缓存

**文件**: `src/main.py` 聊天系统区域

在 `_get_member_display_name()` 中添加简单的字典缓存：

```python
_member_name_cache = {}  # {member_id: display_name}

def _get_member_display_name(member_id):
    if member_id in _member_name_cache:
        return _member_name_cache[member_id]
    member = db_members.get_by_id(member_id)
    name = '未知'
    if member:
        name = member.get('alias') or member.get('name') or '未知'
    _member_name_cache[member_id] = name
    return name
```

在成员更新/删除 API 成功后清空缓存：
- `update_member` 成功后：`_member_name_cache.pop(member_id, None)`
- `delete_member` 成功后：`_member_name_cache.pop(member_id, None)`

### P2-2: sys_stats() 统计结果缓存

**文件**: `src/main.py:2564-2578`

```python
_sys_stats_cache = None
_sys_stats_ts = 0

@api_route('/api/system/stats')
@require_login
def sys_stats(request):
    global _sys_stats_cache, _sys_stats_ts
    now = time.time()
    if _sys_stats_cache and (now - _sys_stats_ts < 60):
        return _sys_stats_cache
    try:
        _sys_stats_cache = {
            "members": db_members.count(),
            "poems": db_poems.count(),
            "activities": db_activities.count(),
            "tasks": db_tasks.count(),
            "finance": db_finance.count()
        }
        _sys_stats_ts = now
        return _sys_stats_cache
    except Exception as e:
        error(f"获取统计数据失败: {e}", "Stats")
        return {}
```

### P2-3: Token 验证结果短期缓存

**文件**: `src/main.py:352-386`

```python
_token_cache = {}       # {token_str: (valid, user_id, cache_expire_ts)}
_token_cache_calls = 0  # 调用计数，用于定期清理

def verify_token(token):
    global _token_cache, _token_cache_calls
    if not token:
        return False, None, "未提供Token"
    
    now = int(time.time())
    
    # 每200次调用清理过期缓存
    _token_cache_calls += 1
    if _token_cache_calls >= 200:
        _token_cache_calls = 0
        _token_cache = {k: v for k, v in _token_cache.items() if v[2] > now}
    
    # 查缓存
    if token in _token_cache:
        valid, uid, exp = _token_cache[token]
        if now < exp:
            return valid, uid, None if valid else "Token验证失败"
        del _token_cache[token]
    
    # ... 原有验证逻辑(360-386行) ...
    
    # 验证成功后写入缓存（缓存60秒）
    if valid:
        _token_cache[token] = (True, user_id, now + 60)
    
    return valid, user_id, err_msg
```

**收益**: 同一用户60秒内重复请求跳过 SHA256 计算。

---

## P3: 前端请求去重

### P3-1: 消除 /api/settings/system 重复调用

**文件**: `src/static/app.js`

分析调用链：页面初始化时 `checkLogin()` -> `checkSystemSettings()` -> `fetchSystemSettings()`，以及独立的 `loadSystemSettings()`，导致同一接口被调用2-3次。

优化方式：在 `fetchSystemSettings()` 中添加简单的 Promise 去重：

```javascript
let _settingsPromise = null;
let _settingsExpire = 0;

async function fetchSystemSettings(forceRefresh = false) {
    const now = Date.now();
    if (!forceRefresh && _systemSettings && now < _settingsExpire) {
        return _systemSettings;
    }
    if (_settingsPromise) {
        return _settingsPromise;
    }
    _settingsPromise = (async () => {
        try {
            const res = await fetch(`${API_BASE}/settings/system`);
            const data = await res.json();
            _systemSettings = data;
            _settingsExpire = now + 60000; // 缓存60秒
            return data;
        } finally {
            _settingsPromise = null;
        }
    })();
    return _settingsPromise;
}
```

在设置保存成功后调用 `_settingsExpire = 0` 强制下次刷新。

---

## 实施顺序

1. **P0 全部** (5项) - 逐项修改并验证
2. **P1-1 + P1-2** (JsonlDB缓存) - 一起实施，改动集中在同一个类
3. **P1-3** (login优化) - 需先确认前端使用的字段列表
4. **P1-4** (聊天计数器) - 聊天系统独立修改
5. **P2 全部** (3项) - 逐项实施
6. **P3-1** (前端去重) - 最后实施

---

## 验证方案

每个阶段完成后的验证步骤：

1. **内存监控**: 在 `sys_info` API 中观察 `free_ram` 变化
2. **功能回归**:
   - 登录/登出正常
   - 诗歌/活动/任务/财务 CRUD 正常
   - 聊天室消息发送和接收正常
   - 积分排行榜正常
   - 系统统计数据正确
   - 备份导入/导出正常
3. **缓存一致性**:
   - 成员更新后名称缓存刷新
   - 数据增删后 count/max_id 缓存正确
   - Token 验证结果与实际一致
4. **压力观察**: 连续快速请求同一接口，观察内存是否稳定（不持续增长）
