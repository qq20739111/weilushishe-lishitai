# 修复：Token 统一使用 Authorization Header 传输

## 问题描述
前端 `fetchWithAuth` 函数对 GET 请求将 Token 附加到 URL 参数 `?token=xxx`，导致 Token 暴露在浏览器历史、日志和 Referer 头中。

## 修改方案

### 涉及文件
- `src/static/app.js` — 前端请求封装（主要修改）
- `src/main.py` — 后端Token提取（移除URL参数回退）

### 修改 1：前端 `fetchWithAuth` 统一使用 Header
**文件**: `src/static/app.js` 第 791-822 行

将 GET 请求从 URL 参数改为 Authorization Header：
```javascript
async function fetchWithAuth(url, options = {}) {
    const token = getAuthToken();
    if (!token && options.requireAuth) {
        throw new Error('请先登录');
    }
    // 所有请求统一通过 Header 传输 Token
    options.headers = options.headers || {};
    if (!options.method || options.method.toUpperCase() === 'GET') {
        // GET 请求不需要 Content-Type
    } else {
        options.headers['Content-Type'] = options.headers['Content-Type'] || 'application/json';
    }
    if (token) {
        options.headers['Authorization'] = `Bearer ${token}`;
    }
    const response = await fetch(url, options);
    if (response.status === 401 && currentUser) {
        handleTokenExpired();
    }
    return response;
}
```

### 修改 2：前端 `checkLogin` 中 check-token 调用
**文件**: `src/static/app.js` 第 591 行

将裸 `fetch` 调用改为使用 Header：
```javascript
// 原: const res = await fetch(`${API_BASE}/check-token?token=${token}`);
// 改为:
const res = await fetch(`${API_BASE}/check-token`, {
    headers: { 'Authorization': `Bearer ${token}` }
});
```

### 修改 3：后端移除 URL 参数 Token 回退（可选加固）
**文件**: `src/main.py` 共 5 处

移除以下函数中的 `request.args.get('token', '')` 回退，只保留 Header 方式：
- `check_token` 第 398 行
- `get_operator_role` 第 821 行
- `require_login` 第 854 行
- `check_login` 第 897 行
- `check_login_get` 第 915 行

**注意**: 后端这些函数都已优先从 `Authorization` Header 读取 Token，URL参数只是备用。移除后不影响功能，但可彻底防止 Token 通过 URL 泄露。保留 POST body 中的 `token` 字段读取（兼容旧请求体格式，安全性可接受）。

## 验证方案
1. 登录后访问各功能页面，用浏览器开发者工具 Network 面板检查：
   - GET 请求的 URL 中不再包含 `token=` 参数
   - 所有请求的 Request Headers 中包含 `Authorization: Bearer xxx`
2. 刷新页面，确认 Token 校验正常（不被踢出登录）
3. 测试各模块功能：诗歌列表、成员列表、财务、任务、聊天室、系统设置、备份

---

# 围炉诗社·理事台 - 全方位安全性与Bug审计报告及改进计划

## 审计范围

| 文件 | 类型 | 行数 |
|---|---|---|
| `src/main.py` | 后端主逻辑（API路由+DB+鉴权） | ~3033 |
| `src/boot.py` | 系统引导 | ~197 |
| `src/lib/microdot.py` | Web框架 | ~237 |
| `src/lib/Logger.py` | 日志模块 | ~128 |
| `src/lib/Watchdog.py` | 看门狗 | ~119 |
| `src/lib/SystemStatus.py` | LED状态 | ~133 |
| `src/static/app.js` | 前端SPA | ~5400 |
| `src/static/style.css` | 样式 | ~5100 |
| `src/static/index.html` | HTML入口 | ~4700 |
| `src/data/config.json` | 配置文件 | 1 |
| `src/data/members.jsonl` | 成员数据 | 10 |

---

## 一、安全漏洞（按严重程度排序）

### [严重-S1] config.json 明文存储 WiFi 密码和 AP 密码

**位置**: `src/data/config.json`
**问题**: WiFi密码 `lei67837729`、AP密码 `weilu2018` 以明文存储在配置文件中，且该文件已被提交到 Git 仓库。
**风险**: 任何能访问代码仓库的人都可以获取 WiFi 凭据；设备被物理接触后也可直接读取。
**改进方案**:
1. 立即从 Git 历史中清除敏感数据（使用 `git filter-branch` 或 `BFG Repo-Cleaner`）
2. 将 `config.json` 加入 `.gitignore`，仓库中只保留 `config.json.template`（占位值）
3. 考虑对 WiFi 密码进行简单的混淆存储（ESP32 资源限制下，至少不以纯文本方式暴露）

### [严重-S2] 备份导出接口泄露全部敏感数据（含密码哈希、WiFi密码）

**位置**: `src/main.py:2548-2610` (`backup_export_table`)
**问题**:
- `name=members` 导出时包含所有成员的**密码哈希值**
- `name=wifi_config` 导出时返回**明文WiFi密码和AP密码**（第2585-2590行，未做任何脱敏）
- `name=settings` 导出时返回 `password_salt`
**风险**: 超级管理员账号被盗或Token泄露后，攻击者可一次性获取所有敏感数据。
**改进方案**:
1. `members` 表导出时剥离 `password` 字段
2. `wifi_config` 导出时对密码字段做星号脱敏（与GET接口一致）
3. 或要求二次密码验证后才允许完整导出

### [严重-S3] 备份导入可覆盖任意数据表（无数据校验）

**位置**: `src/main.py:2612-2710` (`backup_import_table`)
**问题**:
- 导入的 JSONL 数据**未做任何字段校验**，可以注入任意字段（如给成员添加 `role: super_admin`）
- `mode=overwrite` 直接用 `'w'` 模式覆盖整个数据文件，无确认机制
- 导入 `settings` 和 `wifi_config` 时可覆盖 `password_salt`，导致所有密码失效
**风险**: 攻击者（获取超管Token后）可完全控制系统数据。
**改进方案**:
1. 对导入数据进行严格的 schema 校验
2. 导入 members 时禁止导入 `role=super_admin` 的记录
3. 导入前创建自动备份快照
4. 敏感表（settings/wifi_config）导入需二次确认

### [高危-H1] HTTP 明文传输（无 TLS/SSL）

**位置**: `src/boot.py:194`, `src/main.py:3023`（`app.run(port=80)`）
**问题**: 所有通信通过 HTTP 明文传输，包括登录密码、Token、WiFi密码等。
**风险**: 同一网络下的攻击者可通过嗅探获取所有数据。
**现实评估**: ESP32-S2 资源有限，原生 TLS 支持困难。这是架构层面的已知限制。
**改进方案**:
1. 在文档中明确声明此安全限制
2. 建议用户在可信局域网内使用
3. 如条件允许，可在前置路由器/网关层面加 HTTPS 代理
4. 登录密码改为前端哈希后传输（仅防嗅探，不能替代 HTTPS）

### [高危-H2] Token 通过 GET URL 参数传输

**位置**: `src/static/app.js:799-804` (`fetchWithAuth`)
**问题**: GET 请求将 Token 附加到 URL 参数 `?token=xxx`，Token 会出现在：
- 服务器访问日志
- 浏览器历史记录
- 可能的 Referer 头
**改进方案**:
1. 所有请求统一使用 `Authorization: Bearer xxx` Header 传输 Token
2. 后端 `check_token` 已支持 Header 方式，只需修改前端 `fetchWithAuth`

### [高危-H3] 聊天室 `msg.user_name` 未转义（XSS）

**位置**: `src/static/app.js:4945`
**问题**: `renderSingleMessage` 中 `${msg.user_name}` 直接插入 HTML，未经 `escapeHtml()` 处理。虽然 `msg.content` 已正确转义（第4948行），但用户名未转义。
**风险**: 如果攻击者将恶意脚本注入为用户名（通过API修改成员名称），可对所有聊天室用户执行 XSS 攻击。
**改进方案**:
```javascript
// 修改第4945行
<span class="chat-message-user ${isGuest ? 'guest' : ''}">${escapeHtml(msg.user_name)}</span>
```

### [高危-H4] 登录接口无暴力破解防护（无速率限制）

**位置**: `src/main.py:1859-1899` (`login_route`)
**问题**: 登录接口无任何频率限制，攻击者可无限次尝试密码。虽然有登录日志记录，但不会阻断请求。
**改进方案**:
1. 实现基于 IP 的简单速率限制（内存中维护计数器）
2. 连续失败 N 次后临时锁定该 IP（如 5 次失败锁定 5 分钟）
3. 考虑在 ESP32 资源限制下使用简单的字典计数即可

### [高危-H5] 密码哈希算法安全性不足

**位置**: `src/main.py:120-129` (`hash_password`)
**问题**:
- 使用 SHA256 单次哈希，无迭代（非 PBKDF2/bcrypt/scrypt）
- 所有用户共享同一个 salt（`password_salt`），而非每个用户独立 salt
- 共享 salt 意味着相同密码产生相同哈希，容易被彩虹表攻击
**现实评估**: ESP32 资源有限，bcrypt 可能不可行。
**改进方案**:
1. 改为 per-user salt（在每个成员记录中存储独立 salt）
2. 实现多次迭代哈希（如 SHA256 迭代 1000 次），在 ESP32 上可行
3. 迁移时兼容旧哈希格式

### [中危-M1] 旧版明文密码兼容逻辑

**位置**: `src/main.py:131-139` (`verify_password`)
**问题**: 当存储的密码长度不是 64 位时，直接进行明文比较。这意味着如果数据库中存在旧版明文密码，系统会以明文方式验证。
**风险**: 如果存在旧数据迁移残留的明文密码，一旦数据库泄露直接暴露。
**改进方案**:
1. 添加一次性迁移脚本，将所有旧版明文密码转为哈希
2. 迁移完成后移除明文比较逻辑
3. 或在首次明文验证成功后自动将其升级为哈希存储

### [中危-M2] 成员数据中残留 Token 字段

**位置**: `src/data/members.jsonl` 第4-10行
**问题**: 部分成员记录中包含旧的 `token` 字段（如 `"token": "1:826021958:b5af7ebc669972afc18679c8ab3e1ebd"`）。虽然当前系统使用运行时随机密钥签名 Token（重启即失效），但这些残留 Token 暴露了：
- Token 的格式结构（`user_id:expire_time:signature`）
- 旧版 Token 签名模式
**改进方案**:
1. 清理数据文件中残留的 `token` 字段
2. 登录成功后不将 Token 写入成员记录

### [中危-M3] 数据库并发写入竞态条件

**位置**: `src/main.py:598-658` (`JsonlDB.update`, `JsonlDB.delete`)
**问题**: 更新/删除操作采用"读取-写入临时文件-原子替换"模式，但在多个并发请求同时修改同一表时，可能出现：
- 两个请求同时读取原文件，各自生成 `.tmp` 文件
- 后完成的操作覆盖先完成的结果，导致数据丢失
**现实评估**: MicroPython 的 asyncio 是单线程协程模型，除非在 `await` 点发生切换，否则不会真正并发。但文件 I/O 操作可能在某些场景下触发切换。
**改进方案**:
1. 实现简单的文件锁机制（使用锁文件或全局 Flag）
2. 或使用操作队列串行化写入请求

### [中危-M4] `send_file` 无路径校验（潜在路径遍历）

**位置**: `src/lib/microdot.py:220-236` (`send_file`)
**问题**: `send_file` 函数接收文件名参数并直接打开，虽然当前代码中所有调用都使用硬编码路径，但函数本身未校验路径中是否包含 `..` 等目录遍历字符。
**当前风险**: 低（因路由都是硬编码的），但如果未来添加动态路由则风险升高。
**改进方案**:
在 `send_file` 中添加路径规范化和白名单校验。

### [中危-M5] 错误响应中包含内部信息

**位置**: `src/main.py:2610`, `src/main.py:2710`
**问题**: 某些错误响应直接包含 Python 异常信息 `str(e)`，可能泄露内部实现细节。
```python
return Response(f'{{"error": "导出失败: {str(e)}"}}', 500, ...)
```
**改进方案**: 错误响应使用通用消息，详细错误只记录到日志。

### [中危-M6] `settings/fields` GET 接口无鉴权

**位置**: `src/main.py:2159-2182` (`settings_fields`)
**问题**: GET 方法获取自定义字段配置时无需登录，任何人都可以查看系统的自定义字段配置。虽然这不是高敏感信息，但不符合最小权限原则。
**改进方案**: GET 方法也要求登录验证。

### [低危-L1] Token 签名截断为 32 字符

**位置**: `src/main.py:347` (`generate_token`)
**问题**: SHA256 产生 64 字符哈希，但签名截断为前 32 字符（128 位），降低了碰撞难度。
**改进方案**: 使用完整的 64 字符签名，或至少使用 48 字符。

### [低危-L2] `record_login_log` 中手机号脱敏不充分

**位置**: `src/main.py:944`
**问题**: `phone[:3] + '****' + phone[-4:]` 对于长度小于 7 的异常输入直接使用原值。虽然正常手机号都是 11 位，但防御性编程应处理边界情况。

### [低危-L3] 没有 HTTP 安全响应头

**位置**: `src/lib/microdot.py`
**问题**: 响应中没有设置以下安全头：
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Cache-Control: no-store`（针对敏感API）
**改进方案**: 在 microdot 框架层面或 `api_route` 装饰器中统一添加安全响应头。

### [低危-L4] 前端 Token 存储在 localStorage

**位置**: `src/static/app.js:741`
**问题**: Token 存储在 `localStorage` 中，容易被 XSS 攻击读取。但在 ESP32 环境下无法使用 HttpOnly Cookie（需要 HTTPS），这是已知限制。

---

## 二、Bug 和逻辑缺陷

### [Bug-B1] `delete` 操作在未找到记录时仍删除原文件

**位置**: `src/main.py:634-658` (`JsonlDB.delete`)
**问题**: 
```python
os.remove(self.filepath)       # 第652行：无条件删除原文件
os.rename(tmp_path, self.filepath)  # 第653行：用tmp替换
return found                   # 第654行：然后才返回found
```
无论是否找到目标记录，都会执行文件替换。如果目标 ID 不存在，结果是重写了整个文件（内容不变但产生了不必要的 I/O），且空行被清除。
**改进方案**: 参照 `update` 方法的逻辑，仅在 `found=True` 时执行替换，否则删除临时文件。

### [Bug-B2] 任务审批逻辑中状态判断存在顺序问题

**位置**: `src/main.py:1446-1462` (`approve_task`)
**问题**: `task_updater` 闭包在 `db_tasks.update` 调用时执行，如果任务状态为 `completed`，闭包内不做任何修改，但后续代码（第1453行）检查 `task_status == 'completed'` 返回成功。问题在于：如果 `task_status` 变量在 `task_updater` 未被调用时（例如 ID 不存在），`task_status` 保持为 `None`，后续的状态判断 `task_status not in ['submitted', 'claimed']` 也会成立，返回 400 而非 404。
**现实影响**: 当 `task_found=False`时先返回404，所以这个路径实际不会被触及。但代码逻辑冗余，建议简化。

### [Bug-B3] `unclaim_task` 缺少身份验证（任何登录用户可撤销他人任务）

**位置**: `src/main.py:1377-1397` (`unclaim_task`)
**问题**: 只检查了 `@require_login`，但未验证请求者是否是任务的领取者。任何登录用户都可以通过提交任意 `task_id` 撤销他人已领取的任务。
**改进方案**: 在 `task_updater` 中增加身份校验，仅允许任务领取者本人或管理员撤销。

### [Bug-B4] `submit_task` 缺少身份验证（任何登录用户可提交他人任务）

**位置**: `src/main.py:1399-1418` (`submit_task`)
**问题**: 同 B3，只要登录即可提交任意任务ID，未验证是否为任务领取者。
**改进方案**: 验证提交者身份与任务 `assignee_id` 匹配。

### [Bug-B5] 财务记录的 `amount` 字段未做类型校验

**位置**: `src/main.py:2099-2117` (`add_finance`)
**问题**: `amount` 字段从请求 JSON 中获取后直接参与数学运算，但未验证其是否为数字类型或正数。如果传入字符串或负数，可能导致余额计算错误。
**改进方案**: 添加 `amount` 的数字类型验证和正数检查。

### [Bug-B6] 诗歌创建时未记录 `author_id`

**位置**: `src/main.py:1145-1161` (`create_poem`)
**问题**: `create_poem` 只要求 `@require_login`，但不从 Token 中提取 `user_id` 设置为 `author_id`。`author_id` 完全依赖前端传入，可以被伪造。后续的编辑/删除权限检查 (`poem.get('author_id') != user_id`) 就可能被绕过。
**改进方案**: 后端从 Token 中获取 `user_id` 并强制设置为 `author_id`，忽略前端传入值。

### [Bug-B7] 任务审批时按 `assignee` 名称匹配发放积分（非 ID）

**位置**: `src/main.py:1465-1477` (`approve_task`)
**问题**: 积分发放通过 `assignee_name` 匹配成员名称，如果有同名成员，积分会发给第一个匹配到的人。应使用 `assignee_id` 进行精确匹配。
**改进方案**: 优先使用 `assignee_id` 匹配，name 仅作备用。

---

## 三、性能和健壮性问题

### [P1] `get_settings()` 每次API调用都读取文件

**位置**: `src/main.py:967-999`
**问题**: 每个 API 请求通过 `api_route` 装饰器调用 `get_operator_role` -> 读取 `members.jsonl`，再通过维护模式检查调用 `get_settings()` -> 读取 `config.json`。高频请求下 Flash 读取次数过多。
**改进方案**: 将 settings 缓存到内存中，配置修改时更新缓存。

### [P2] `get_operator_role` 每次请求都全量扫描 members 文件

**位置**: `src/main.py:810-839`
**问题**: 每个需要鉴权的请求都遍历整个 `members.jsonl` 文件查找用户角色。
**改进方案**: 维护一个轻量级的 `{user_id: role}` 内存缓存，成员变更时更新。

### [P3] `update_member_route` 中 `db_members.get_all()` 被多次调用

**位置**: `src/main.py:1621-1734`
**问题**: 同一个请求中，`get_all()` 被调用多次（第1632行查目标、第1674行查手机号唯一性、第1717行查积分），每次都全量读取文件。
**改进方案**: 单次读取后复用数据，或使用 `get_by_id` 替代部分全量扫描。

### [P4] 聊天室消息清理使用 `pop(0)` 导致 O(n) 复杂度

**位置**: `src/main.py:2752`
**问题**: Python 列表的 `pop(0)` 是 O(n) 操作，当消息量大时性能差。
**改进方案**: 使用 `collections.deque`（如 MicroPython 支持），或采用环形缓冲区策略。

---

## 四、改进实施计划

按优先级分阶段实施：

### 第一阶段：紧急安全修复

| 编号 | 修改项 | 涉及文件 | 复杂度 |
|---|---|---|---|
| S1 | 将 config.json 加入 .gitignore，创建 template | `.gitignore`, `src/data/config.json.template` | 低 |
| S2 | 备份导出接口脱敏（members密码、WiFi密码、salt） | `src/main.py` 第2548-2610行 | 低 |
| H3 | 聊天室 user_name XSS 转义修复 | `src/static/app.js` 第4945行 | 低 |
| B1 | 修复 JsonlDB.delete 不必要的文件重写 | `src/main.py` 第634-658行 | 低 |
| B3/B4 | 任务撤销/提交增加身份验证 | `src/main.py` 第1377-1418行 | 低 |
| B6 | 诗歌创建强制后端设置 author_id | `src/main.py` 第1145-1161行 | 低 |

### 第二阶段：重要安全加固

| 编号 | 修改项 | 涉及文件 | 复杂度 |
|---|---|---|---|
| S3 | 备份导入增加数据校验 | `src/main.py` 第2612-2710行 | 中 |
| H2 | 前端统一使用 Header 传输 Token | `src/static/app.js` fetchWithAuth 函数 | 低 |
| H4 | 登录接口添加简单速率限制 | `src/main.py` login_route | 中 |
| M1 | 旧版明文密码自动迁移 | `src/main.py` verify_password | 中 |
| M2 | 清理 members.jsonl 中残留的 Token | `src/data/members.jsonl` | 低 |
| M5 | 错误响应移除内部异常详情 | `src/main.py` 多处 | 低 |
| M6 | settings/fields GET 增加登录验证 | `src/main.py` 第2159行 | 低 |
| B5 | 财务金额类型和正数校验 | `src/main.py` add_finance | 低 |
| B7 | 任务积分发放改用 assignee_id | `src/main.py` approve_task | 低 |

### 第三阶段：安全增强与性能优化

| 编号 | 修改项 | 涉及文件 | 复杂度 |
|---|---|---|---|
| H5 | 密码哈希改为 per-user salt + 多次迭代 | `src/main.py` hash_password, members数据迁移 | 高 |
| L1 | Token 签名使用完整 64 字符 | `src/main.py` generate_token/verify_token | 低 |
| L3 | 添加 HTTP 安全响应头 | `src/lib/microdot.py` 或 `src/main.py` | 低 |
| M3 | 数据库写入串行化（文件锁） | `src/main.py` JsonlDB | 中 |
| M4 | send_file 路径校验 | `src/lib/microdot.py` | 低 |
| P1/P2 | 设置和角色内存缓存 | `src/main.py` | 中 |
| P3 | 减少 get_all() 冗余调用 | `src/main.py` update_member_route | 低 |

---

## 五、验证方案

完成修复后，通过以下方式验证：

1. **安全验证**:
   - 用非管理员账号尝试访问备份导出接口，确认被拒绝
   - 验证备份导出的 members 数据不含 password 字段
   - 在聊天室中发送含 `<script>` 标签的用户名，确认被转义
   - 连续发送 10+ 次错误登录请求，确认速率限制生效
   - 尝试用 A 用户的 Token 撤销 B 用户的任务，确认被拒绝

2. **功能回归**:
   - 正常登录/登出流程
   - 诗歌CRUD、成员CRUD、活动CRUD、财务CRUD、任务流程
   - 聊天室消息收发
   - 数据备份导出/导入
   - WiFi配置修改
   - 系统设置修改

3. **ESP32 资源验证**:
   - 检查修改后的内存占用（`gc.mem_free()`）
   - 确认 API 响应时间无明显退化
