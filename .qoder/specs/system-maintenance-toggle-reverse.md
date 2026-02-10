# 修改"全站维护模式"开关为"开启网站访问" [已完成]

## 需求
将系统基础设置中的"全站维护模式"开关改为"开启网站访问"，反转开关语义：
- 开关ON：网站正常开放，所有用户可访问
- 开关OFF：进入维护状态，非管理员显示维护提示

## 实现策略
**前后端统一重命名字段。** 将 `maintenance_mode` 字段替换为 `site_open`，语义从"是否维护"反转为"是否开放"，前后端直接映射，无需取反。

## 修改清单

### 1. `src/static/index.html`
- 开关标题：`全站维护模式` → `开启网站访问`
- 开关描述：`开启后仅管理员可访问，其他用户显示维护提示` → `关闭后其他用户显示维护提示，仅管理员可访问`
- 元素ID：`setting-maintenance-mode` → `setting-site-open`

### 2. `src/static/app.js`
- **loadSiteSettings()**：元素ID改为 `setting-site-open`，`checked = data.site_open !== false`
- **saveSiteSettings()**：元素ID改为 `setting-site-open`，`settings.site_open = siteOpenEl.checked`
- **checkLogin()**：判断条件 `settings.maintenance_mode && !isAdmin` → `!settings.site_open && !isAdmin`
- **checkSystemSettings()**：默认值 `{ maintenance_mode: false }` → `{ site_open: true }`

### 3. `src/main.py`
- **SETTINGS_KEYS**：`maintenance_mode` → `site_open`
- **get_settings()**：字段名改为 `site_open`，默认值 `True`
- **api_route() 装饰器**：检查条件 `s.get('maintenance_mode', False)` → `not s.get('site_open', True)`
- **登录路由**：同上逻辑反转
- **settings_system() API GET**：返回字段 `site_open` 替代 `maintenance_mode`
- **settings_system() API POST**：接收字段 `site_open` 替代 `maintenance_mode`

### 4. `src/data/config.json`
- `"maintenance_mode": false` → `"site_open": true`

## 验证方法
1. 开关默认状态应为ON（`site_open` 默认 `true`，`checked=true`）
2. 关闭开关 → 保存 → 后端 `site_open` 变为 `false` → 非管理员用户看到维护页面
3. 打开开关 → 保存 → 后端 `site_open` 变为 `true` → 所有用户可正常访问
