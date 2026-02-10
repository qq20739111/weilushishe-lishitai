# 围炉诗社·理事台 — 系统安全审计报告

> **审计范围**：全系统安全排查（排除"密码存储"相关问题）
> **目标平台**：ESP32-S2 MicroPython（320KB SRAM / 2MB Flash / 2MB PSRAM）
> **报告性质**：安全分析与改进建议（仅报告，不包含实施）

---

## 一、关键（Critical）— 必须修复

### C1. 登录接口无暴力破解防护
- **位置**：`src/main.py:1884-1924` `/api/login`
- **风险**：攻击者可无限次尝试登录，暴力破解账户；大量请求可导致 ESP32 资源耗尽（DoS）
- **修复方案**：在内存中维护失败记录字典 `{phone: [timestamps]}`，5分钟内失败超5次则拒绝登录（返回 429），定期清理过期记录。内存开销约 2KB，对 ESP32 友好
- **涉及文件**：`src/main.py` — 在 `login_route` 开头增加限流检查

### C2. 配置文件保存非原子操作
- **位置**：`src/main.py:1035-1036` `save_settings()`
- **风险**：直接 `open('w')` 写入 `config.json`，若写入中断电/崩溃，配置文件损坏导致系统无法启动
- **对比**：JSONL 数据库操作（L604-620）已使用 `.tmp` 临时文件 + `os.rename()` 原子替换
- **修复方案**：复用 JSONL 的原子写入模式：写入 `config.json.tmp` → `os.remove` 旧文件 → `os.rename` 临时文件。失败时清理临时文件
- **涉及文件**：`src/main.py:1022-1040`

### C3. 备份导出泄露 WiFi 密码明文
- **位置**：`src/main.py:2622-2635` `/api/backup/export-table`（`wifi_config`表）
- **风险**：导出时直接返回 `wifi_password` 和 `ap_password` 明文；与 `/api/wifi/config` GET（L2396-2403）已掩码为 `********` 的处理不一致
- **修复方案**：导出 `wifi_config` 时统一将密码字段替换为 `********`，与 GET 接口行为保持一致
- **涉及文件**：`src/main.py:2622-2635`

---

## 二、高（High）— 建议尽快修复

### H1. 多个 GET 端点无需认证即可访问
- **位置及影响**：
  | 端点 | 行号 | 暴露内容 |
  |------|------|----------|
  | `/api/poems` GET | L1078 | 全部诗词（含 author_id） |
  | `/api/poems/random` GET | L1103 | 随机诗词 |
  | `/api/poems/weekly-stats` GET | L1125 | 统计数据 |
  | `/api/activities` GET | L1241 | 全部活动 |
  | `/api/chat/messages` GET | L2865 | 全部聊天消息 |
  | `/api/chat/users` GET | L2883 | 在线用户列表 |
  | `/api/settings/system` GET | L2227 | 系统配置（名称、功能开关、聊天参数等） |
  | `/api/settings/token_expire` GET | L2325 | Token 过期天数 |
  | `/api/settings/fields` GET | L2202 | 自定义字段定义 |
- **风险**：未授权用户可获取用户ID列表、聊天记录、系统配置等信息，辅助枚举攻击和系统指纹识别
- **修复方案**：
  1. **`/api/settings/system` GET**：将返回字段分为两类——
     - **页面渲染必需（无需登录）**：`system_name`、`points_name`、`allow_guest`、`chat_enabled` 等前端未登录状态下需要的展示/判断字段
     - **管理配置（需登录）**：`maintenance_mode`、`chat_guest_max`、`chat_max_users`、`chat_cache_size` 等仅管理后台使用的字段，未登录时不返回
  2. **`/api/settings/token_expire` GET** 和 **`/api/settings/fields` GET**：改为 `@require_login`
  3. **业务数据类**接口根据 `allow_guest` 开关控制：关闭时要求登录，开启时对游客进行字段脱敏（如移除 `author_id`、限制单页条数）
  4. **聊天接口**至少要求已加入聊天室（通过检查 `_chat_users` / `_chat_guests` 状态）
- **涉及文件**：`src/main.py` 对应各路由，以及 `PUBLIC_DATA_WHITELIST`（L62-72）

### H2. Token 可通过请求体传递
- **位置**：`src/main.py:393-396`（`check_token`）、`L830-833`（`get_operator_role`）、`L863-866`（`require_login`装饰器）
- **风险**：请求体可能被记录到调试日志或错误日志中，导致 Token 泄露 → 会话劫持
- **修复方案**：移除从 `request.json.get('token')` 读取 Token 的逻辑，仅保留 `Authorization: Bearer` header 方式。前端 `app.js` 已全面使用 header，无需修改前端
- **涉及文件**：`src/main.py:393-396, L830-833, L863-866`

### H3. 配置文件中敏感数据与普通配置混存
- **位置**：`src/data/config.json`
- **风险**：WiFi密码、AP密码、密码盐值与普通配置项（系统名称、功能开关等）存储在同一文件中。若通过备份、日志或其他渠道泄露 config.json，所有敏感信息暴露
- **修复方案**：
  1. 将 `wifi_password`、`ap_password`、`password_salt` 等敏感字段移到独立文件 `data/secrets.json`
  2. `load_config()` 合并加载两个文件
  3. 备份导出/导入逻辑中排除 `secrets.json`
- **涉及文件**：`src/main.py:990-991`（加载配置）、`src/boot.py:20-27`、`src/data/config.json`

---

## 三、中等（Medium）— 改善整体安全水平

### M1. 错误消息直接返回异常详情
- **位置**：`src/main.py:2654` 等多处 `str(e)` 直接返回客户端
- **风险**：可能泄露内部文件路径、数据结构等信息
- **修复方案**：封装 `safe_error_response(e, module)` 函数 — 生产环境返回通用消息，debug 模式下返回详情。全局替换所有暴露 `str(e)` 的地方
- **涉及文件**：`src/main.py` — 搜索所有 `str(e)` 和 `{e}` 返回给客户端的位置

### M2. 缺少 Content-Security-Policy 安全头
- **位置**：`src/lib/microdot.py:198-199`（已有 `X-Content-Type-Options` 和 `X-Frame-Options`）
- **风险**：缺少 CSP 头，无法从浏览器层面限制脚本、样式、图片等资源来源，降低 XSS 防御深度
- **修复方案**：在响应头注入位置添加：
  ```
  Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'
  ```
  注意：由于 `index.html:844-846` 有内联脚本，暂时需要 `'unsafe-inline'`
- **涉及文件**：`src/lib/microdot.py:198-199`

### M3. 缺少数据修改审计日志
- **位置**：全局
- **风险**：系统已有登录日志（`login_logs.jsonl`），但对诗词/成员/活动/财务/设置等的增删改操作无记录，事后无法追溯
- **修复方案**：新增 `data/audit_logs.jsonl`，在关键写操作路由中记录 `{user_id, action, target_type, target_id, timestamp, ip}`，最多保留 500 条（约 50KB Flash），复用 `login_logs` 的清理机制
- **涉及文件**：`src/main.py` — 所有 POST 路由

### M4. localStorage 存储 Token 的 XSS 风险
- **位置**：`src/static/app.js:743`
- **风险**：Token 存储在 `localStorage`，若存在 XSS 漏洞可被脚本直接读取。系统已集成 DOMPurify（L5000-5018）和 `escapeHtml()`（L4974），但 `app.js` 中有 50+ 处 `innerHTML` 使用需审查
- **修复方案**：
  1. 逐一审查所有 `innerHTML` 使用，确保用户数据均经过 `escapeHtml()` 或 DOMPurify 处理
  2. 纯文本场景改用 `textContent`
  3. 考虑将默认 Token 有效期从 30 天（L321）缩短至 7 天
- **涉及文件**：`src/static/app.js` — 所有 `innerHTML` 位置

---

## 四、低（Low）— 长期完善

### L1. AP 模式默认弱口令
- **位置**：`src/boot.py:141-142` — 默认密码 `admin1234`
- **风险**：仅在设备无法连接 WiFi 启动 AP 模式时暴露，但仍属弱口令
- **修复方案**：提升默认密码复杂度（如 `WeiluPoetry2026!`），或首次启动时生成随机密码打印到串口

### L2. 聊天室游客无限制
- **位置**：`src/main.py:2899+` — 游客无需认证即可加入并发消息
- **风险**：垃圾信息污染、内存资源浪费
- **修复方案**：添加游客消息限流（每分钟最多 5 条），或将默认 `chat_guest_max` 改为 0（仅登录用户可用）

### L3. WiFi 密码导入缺少格式验证
- **位置**：`src/main.py:2727`
- **风险**：导入备份时直接接受 WiFi 密码，无长度/格式检查
- **修复方案**：复用 WiFi 配置接口中已有的验证逻辑（密码长度 8-63 字符）

---

## 五、资源影响评估

| 改进项 | 内存增加 | Flash 增加 | CPU 开销 |
|--------|----------|-----------|---------|
| C1 登录限流 | ~2KB | ~100B | 极低 |
| C2 配置原子写入 | 0 | ~300B | 极低 |
| C3 密码掩码 | 0 | ~200B | 无 |
| H1 API 权限细化 | ~1KB | ~500B | 低 |
| H2 禁用 Body Token | 0 | -100B | 无 |
| H3 敏感配置隔离 | 0 | ~1KB | 无 |
| M1 错误脱敏 | 0 | ~300B | 无 |
| M2 CSP 头 | 0 | ~200B | 无 |
| M3 审计日志 | ~1KB | ~50KB | 低 |
| M4 Token/XSS 优化 | 0 | ~200B | 无 |
| **总计** | **~4KB** | **~53KB** | **低** |

所有改进措施对 ESP32 资源影响极小，可安全实施。

---

## 六、关键修改文件

| 文件 | 涉及改进项 |
|------|-----------|
| `src/main.py` | C1, C2, C3, H1, H2, M1, M3 |
| `src/boot.py` | H3, L1 |
| `src/data/config.json` | H3 |
| `src/lib/microdot.py` | M2 |
| `src/static/app.js` | M4 |

---

## 七、验证方法

1. **暴力破解**：脚本在 5 分钟内发 20 次错误登录，验证第 6 次返回 429
2. **配置损坏**：修改设置后强制断电，验证 `config.json` 未损坏
3. **备份安全**：导出 `wifi_config`，验证密码字段为 `********`
4. **权限穿越**：使用普通用户 Token 访问管理接口，验证 403
5. **XSS 测试**：在诗词标题输入 `<script>alert(1)</script>`，验证被转义
6. **CSP 测试**：浏览器控制台检查 CSP 头生效，外部脚本被拦截
