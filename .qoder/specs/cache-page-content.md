# API 响应缓存方案 - 页面第一页数据缓存

## 概述

在现有 `CacheManager` 基础上，为各模块的默认第一页请求（无搜索条件）建立响应级缓存。数据库未更新时直接从内存返回，避免 Flash 读取。

**修改文件**: 仅 `src/main.py`（CacheManager 无需改动）

---

## 1. 缓存键与 TTL

| 缓存键 | 对应 API | TTL | 预估内存 |
|--------|---------|-----|---------|
| `api:poems:page1` | `GET /api/poems?page=1&limit=10` | 无(写入失效) | ~15KB |
| `api:activities:page1` | `GET /api/activities?page=1&limit=10` | 无 | ~5KB |
| `api:tasks:page1` | `GET /api/tasks?page=1&limit=10` | 无 | ~1KB |
| `api:members:page1` | `GET /api/members?page=1&limit=10`(非public) | 无 | ~3KB |
| `api:finance:page1` | `GET /api/finance?page=1&limit=20` | 无 | ~2KB |
| `api:finance:stats` | `GET /api/finance/stats` | 无 | ~0.2KB |
| `api:weekly:YYYY` | `GET /api/poems/weekly-stats?year=YYYY` | 3600s | ~1KB/年 |
| `api:points:ranking` | `GET /api/points/yearly_ranking` | 无 | ~2KB |
| `api:system:stats` | `GET /api/system/stats` | 无 | ~0.1KB |

**不缓存**: `/api/poems/random`（需随机性）、带 `?q=` 搜索的请求、`?public=1` 公开模式

**总内存峰值**: ~30KB（全部页面访问后），在 320KB SRAM + 2MB PSRAM 下完全可控。

**TTL 策略**: 绝大多数缓存不设 TTL，仅靠写入操作精确失效；`weekly-stats` 因按年份动态注册，设 1 小时 TTL 兜底。

---

## 2. 实现步骤

### 步骤 1: 注册缓存槽 + 辅助函数（约第 62 行 `app = Microdot()` 之后）

在 `app = Microdot()` 之后、`MAINTENANCE_WHITELIST` 之前，添加：

```python
# --- API 响应缓存 ---
_API_CACHE_KEYS = [
    'api:poems:page1', 'api:activities:page1', 'api:tasks:page1',
    'api:members:page1', 'api:finance:page1', 'api:finance:stats',
    'api:points:ranking', 'api:system:stats'
]
for _ck in _API_CACHE_KEYS:
    cache.register(_ck, ctype='value')
del _ck
info("API响应缓存已注册", "Cache")

def invalidate_api_cache(*keys):
    """批量失效 API 缓存"""
    for k in keys:
        cache.invalidate(k)

def invalidate_module_cache(module):
    """按模块失效全部相关 API 缓存（备份导入用）"""
    m = {
        'poems': ['api:poems:page1', 'api:system:stats'],
        'activities': ['api:activities:page1', 'api:system:stats'],
        'tasks': ['api:tasks:page1', 'api:system:stats'],
        'members': ['api:members:page1', 'api:points:ranking', 'api:system:stats'],
        'finance': ['api:finance:page1', 'api:finance:stats', 'api:system:stats'],
        'points_logs': ['api:points:ranking'],
    }
    for k in m.get(module, []):
        cache.invalidate(k)
    # 诗歌/活动变动影响周统计，清除所有已注册的 weekly 缓存
    if module in ('poems', 'activities'):
        for k in list(cache._cfg.keys()):
            if k.startswith('api:weekly:'):
                cache.invalidate(k)
```

### 步骤 2: 改造 9 个 GET API（读取时加缓存）

每个函数的改造模式一致：判断是否为默认第一页请求 → 是则走缓存 → 否则走原逻辑。

#### 2.1 `list_poems` (行 1119)

```python
def list_poems(request):
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 10))
        q = request.args.get('q', None)
        if q: q = simple_unquote(q)
        # 默认第一页且无搜索：走缓存
        if page == 1 and limit == 10 and not q:
            cached = cache.get_val('api:poems:page1')
            if cached is not None:
                return cached
            items, _ = db_poems.fetch_page(1, 10, reverse=True)
            cache.set_val('api:poems:page1', items)
            return items
        items, _ = db_poems.fetch_page(page, limit, reverse=True, search_term=q)
        return items
    except Exception as e:
        error(f"获取诗歌列表失败: {e}", "API")
        return []
```

#### 2.2 `list_activities` (行 1282) — 同模式，cache key = `api:activities:page1`

#### 2.3 `list_tasks` (行 1336) — 同模式，cache key = `api:tasks:page1`

#### 2.4 `list_members` (行 1585)

仅缓存条件: `page == 1 and limit == 10 and not q and not public_mode`。在 `if page > 0 and limit > 0:` 分支内添加缓存判断，缓存的是已去除 password 字段的 items。

#### 2.5 `list_finance` (行 2115) — cache key = `api:finance:page1`，默认 limit=20

#### 2.6 `finance_stats` (行 2128)

在计算前检查 `cache.get_val('api:finance:stats')`，命中直接返回；未命中执行原逻辑后 `set_val`。

#### 2.7 `weekly_poem_stats` (行 1166)

按年份动态注册缓存键 `api:weekly:{year}`：
```python
cache_key = f'api:weekly:{year}'
if cache_key not in cache._cfg:
    cache.register(cache_key, ctype='value', ttl=3600)
cached = cache.get_val(cache_key)
if cached is not None:
    return cached
# ... 原计算逻辑 ...
result = {'year': year, 'weeks': weeks, 'act_weeks': act_weeks}
cache.set_val(cache_key, result)
return result
```

#### 2.8 `yearly_points_ranking` (行 1879) — cache key = `api:points:ranking`

#### 2.9 `sys_stats` (行 2615) — cache key = `api:system:stats`

---

### 步骤 3: 在所有写操作后插入缓存失效

| 函数 | 行号 | 插入位置 | 失效的缓存键 |
|-----|------|---------|------------|
| `create_poem` | 1227 | `if db_poems.append(data):` 后、`return data` 前 | `api:poems:page1`, `api:weekly:{year}`, `api:system:stats` |
| `update_poem` | 1258 | `if db_poems.update(pid, updater):` 后 | `api:poems:page1`, `api:weekly:{year}` |
| `delete_poem` | ~1278 | `if db_poems.delete(pid):` 后 | `api:poems:page1`, `api:system:stats` + 清除所有 `api:weekly:*` |
| `create_activity` | 1303 | `db_activities.append(data)` 后 | `api:activities:page1`, `api:weekly:{year}`, `api:system:stats` |
| `update_activity` | 1322 | `if db_activities.update(...)` 后 | `api:activities:page1` + 清除所有 `api:weekly:*` |
| `delete_activity` | 1330 | `if db_activities.delete(pid):` 后 | `api:activities:page1`, `api:system:stats` + 清除所有 `api:weekly:*` |
| `create_task` | 1386 | `db_tasks.append(task)` 后 | `api:tasks:page1`, `api:system:stats` |
| `update_task` | 1416 | `if updated:` 内 | `api:tasks:page1` |
| `claim_task` | 1442 | `if not task_found:` 之前 | `api:tasks:page1` |
| `unclaim_task` | 1470 | `db_tasks.update(tid, task_updater)` 后 | `api:tasks:page1` |
| `submit_task` | 1496 | `db_tasks.update(tid, task_updater)` 后 | `api:tasks:page1` |
| `approve_task` | 1549 | `return` 前 | `api:tasks:page1`, `api:members:page1`, `api:points:ranking` |
| `reject_task` | 1570 | `if not task_found:` 之前 | `api:tasks:page1` |
| `delete_task` | 1579 | `if db_tasks.delete(tid):` 后 | `api:tasks:page1`, `api:system:stats` |
| `create_member` | ~1690 | `db_members.append(data)` 后 | `api:members:page1`, `api:system:stats` |
| `update_member_route` | 1789 | `if db_members.update(mid, updater):` 内 | `api:members:page1` + 若积分变动则 `api:points:ranking` |
| `delete_member_route` | 1873 | `if db_members.delete(member_id):` 后 | `api:members:page1`, `api:system:stats` |
| `add_finance` | 2199 | `db_finance.append(data)` 后 | `api:finance:page1`, `api:finance:stats`, `api:system:stats` |
| `update_finance` | 2225 | `if _rewrite_finance_file(...)` 后 | `api:finance:page1`, `api:finance:stats` |
| `delete_finance` | 2238 | `if _rewrite_finance_file(...)` 后 | `api:finance:page1`, `api:finance:stats`, `api:system:stats` |
| `record_points_change` | 984 | `db_points_logs.append(log)` 后 | `api:points:ranking` |
| `backup_import_table` | 2758 | 写入成功后（已有 members 角色缓存清除处） | 调用 `invalidate_module_cache(table)` |

**周统计缓存失效细节**:
- 新增/修改诗歌或活动时，从 `data.get('date', '')[:4]` 提取年份，失效 `api:weekly:{year}`
- 删除操作因记录可能已不可读，统一清除所有 `api:weekly:*` 键

---

## 3. 关键设计决策

1. **无 TTL + 写入失效**: 大部分缓存不设 TTL，靠精确的写入失效保证数据一致性。比 TTL 更省内存（无需定期重算），也保证数据实时性。

2. **`get_val` 返回 `None` 即缓存未命中**: `CacheManager.get_val()` 在未注册、过期、或值为 `None` 时均返回 `None`。由于注册时 `initial` 默认为 `None`，首次请求必定 miss。API 返回值为 `list` 或 `dict`，不会是 `None`，因此 `is not None` 判断安全。

3. **`list_members` 特殊处理**: 仅缓存非公开模式的分页请求（去除 password 后的数据）。公开模式和无分页的 `get_all()` 调用不缓存。

4. **低内存保护**: 已有的 `cache.flush_all()` 机制会清除所有 `value` 类型缓存（包括新增的 API 缓存），无需额外处理。

---

## 4. 验证方案

1. **功能验证**: 
   - 访问诗歌列表两次 → 通过 `/api/system/cache-stats` 确认 `api:poems:page1` 的 `hits` 增长
   - 新增诗歌后访问列表 → 确认返回最新数据（缓存已失效）
   - 带搜索参数 `?q=test` 访问 → 确认不走缓存（每次读文件）

2. **内存验证**: 通过 `/api/system/info` 查看 `free_memory`，访问所有页面后确认空闲内存仍 > 200KB

3. **边界验证**: 
   - 备份导入后确认对应模块缓存已清除
   - 事务审批（approve_task）后确认 tasks、members、points 三个缓存均已失效
