# app.js 拆分重构方案

## 一、现状分析

**文件**: `src/static/app.js` | **5380行** | **~201KB**
- 92+ 个函数，16 个功能模块全部耦合在一个文件中
- 全局变量 30+，模块间通过全局作用域隐式共享
- 无构建工具，通过 `<script>` 标签同步加载

**环境约束**:
- ESP32S2 + MicroPython + Microdot 框架
- 每个静态文件需在 `main.py` 中显式注册路由
- 不支持 ES modules (import/export)
- 所有函数通过全局作用域共享

---

## 二、拆分方案（推荐：10 个文件）

采用**功能模块化 + 依赖分层**策略，兼顾职责清晰和 HTTP 请求数。

### 文件清单与加载顺序

| 序号 | 文件名 | 预估行数 | 职责描述 |
|------|--------|---------|---------|
| 1 | `app.core.js` | ~350 | 全局常量、配置、通用工具函数 |
| 2 | `app.validation.js` | ~280 | 表单验证规则与验证函数 |
| 3 | `app.auth.js` | ~500 | 认证、权限、Token管理、个人资料 |
| 4 | `app.ui.js` | ~350 | 移动端菜单、模态框、页面导航(SPA路由)、IndexedDB草稿 |
| 5 | `app.poems.js` | ~500 | 诗歌管理（发布/编辑/草稿/详情） |
| 6 | `app.members.js` | ~550 | 成员工具函数 + 社员管理CRUD |
| 7 | `app.business.js` | ~900 | 活动管理 + 财务管理 + 事务与积分 |
| 8 | `app.home.js` | ~450 | 首页内容加载 + 全局搜索 |
| 9 | `app.admin.js` | ~800 | 系统设置、WiFi配置、数据备份、自定义字段、统计日志 |
| 10 | `app.chat.js` | ~700 | 聊天室完整功能 + 首页聊天预览 |
| - | `app.main.js` | ~50 | 页面初始化入口 (window.onload) |

> **总计 11 个文件**（含 main.js 入口），HTTP 请求从原来 3 个 JS 增加到 13 个（含 marked + purify）。

---

## 三、各文件详细内容

### 1. `app.core.js` — 核心基础设施层

**原始行号**: 20-141（常量部分）+ 散落各处的工具函数

**包含内容**:

```
常量/变量:
  - API_BASE                    (行23)
  - currentUser                 (行24)
  - _customFields               (行25)
  - _systemSettings             (行26)
  - _settingsLoaded             (行27)
  - VALIDATION_RULES            (行32-129)
  - TOKEN_EXPIRE_DAYS           (行132)
  - ROLE_LEVEL                  (行135-141)

工具函数 (从其他位置提取):
  - escapeHtml(str)             (行4948-4952)
  - formatDate(dateStr)         (行2889-2892)
  - toLocalISOString(dateObj)   (行1345-1354)
  - renderMarkdown(text)        (行4959-5002)
  - getPoemTypeStyle(type)      (行2872-2879)
  - getStatusStyle(status)      (行2881-2887)
  - getPointsName()             (行3880-3882)
  - formatBytes(bytes)          (行4165-4172)
  - formatUptime(seconds)       (行4175-4186)
  - formatMessageTime(ts)       (行4928-4943)
  - withButtonLoading(btn,...)  (行433-446)
  - formatRole(role)            (行1705-1714)
  - getRoleName(role)           (行869-878)
```

**被依赖方**: 所有其他文件

---

### 2. `app.validation.js` — 表单验证层

**原始行号**: 148-425

**包含内容**:
```
函数:
  - canAssignRole(targetRole)       (行148-172)
  - withToken(data)                 (行177-183)
  - checkPasswordStrength(pwd)      (行194-202)
  - validateField(name,val,rule,ctx)(行212-281)
  - validateForm(data, rules)       (行289-308)
  - validateCustomFields(fields,data)(行316-358)
  - showFieldError(input, msg)      (行365-382)
  - clearFieldError(input)          (行388-396)
  - clearFormErrors(selector)       (行402-412)
  - showCustomFieldErrors(errors)   (行418-425)
```

**依赖**: `VALIDATION_RULES`, `ROLE_LEVEL`, `currentUser` (来自 app.core.js)

---

### 3. `app.auth.js` — 认证与权限层

**原始行号**: 547-1047

**包含内容**:
```
Token管理:
  - isTokenExpired()                (行555-562)
  - getAuthToken()                  (行568-578)
  - handleTokenExpired()            (行583-589)
  - getAuthHeaders(extra)           (行802-809)
  - fetchWithAuth(url, opts)        (行818-845)

认证流程:
  - checkLogin()                    (行596-662)
  - updateNavForLoginState()        (行667-679)
  - showLoginPage()                 (行684-688)
  - showMaintenancePage()           (行693-697)
  - showMaintenanceLogin()          (行702-707)
  - checkSystemSettings()           (行713-732)
  - updateNavUser()                 (行738-745)
  - login()                         (行747-787)
  - logout()                        (行789-795)

个人资料:
  - openProfileModal()              (行848-867)
  - saveProfile()                   (行880-965)
  - submitProfilePassword()         (行967-1047)
```

**依赖**:
- `API_BASE`, `currentUser`, `TOKEN_EXPIRE_DAYS`, `ROLE_LEVEL`, `_systemSettings`, `withButtonLoading` (来自 app.core.js)
- `validateField`, `showFieldError`, `clearFieldError`, `clearFormErrors` (来自 app.validation.js)

---

### 4. `app.ui.js` — UI 工具与导航层

**原始行号**: 449-545 + 1050-1202

**包含内容**:
```
移动端控制:
  - toggleMobileMenu()              (行449-454)
  - closeMobileMenu()               (行456-461)

加载/空状态:
  - showLoading(containerId)        (行464-469)
  - showEmptyState(id,icon,txt,...) (行471-485)

IndexedDB草稿:
  - LocalDrafts 对象                 (行488-545)
    .init() / .getAll() / .save() / .delete()

页面导航:
  - _lastSection                    (行1052)
  - showSection(id)                 (行1059-1144)

模态框:
  - _currentOpenModal               (行1151)
  - toggleModal(id)                 (行1158-1173)
  - closeModal(id)                  (行1179-1188)
  - ESC键关闭事件绑定               (行1191-1195)
  - 背景点击关闭事件绑定             (行1198-1202)
```

**依赖**: `currentUser` (来自 app.core.js)

**注意**: `showSection()` 内部调用各模块的 fetch 函数（如 `fetchPoems`, `fetchActivities` 等），这些是**运行时延迟绑定**——调用时这些函数已在全局作用域中定义，不构成加载时依赖。

---

### 5. `app.poems.js` — 诗歌管理模块

**原始行号**: 1204-1644

**包含内容**:
```
状态变量:
  - _cachedPoems, _poemPage, _poemHasMore   (行1207-1209)
  - _showingAllPoems, _poemSearchTerm        (行1210-1211)
  - editingPoemId, editingPoemIsLocal        (行1212-1213)

函数:
  - fetchPoems(isLoadMore)          (行1220-1268)
  - renderPoems()                   (行1270-1344)
  - openPoemModal(poem)             (行1356-1398)
  - openPoemDetailView(poem)        (行1400-1447)
  - editPoemFromView(poemId)        (行1449-1456)
  - saveDraft()                     (行1458-1482)
  - publishPoem()                   (行1484-1533)
  - submitPoemUpdate()              (行1535-1572)
  - withdrawPoem(id)                (行1574-1625)
  - deletePoemWrapper(id,isLocal,e) (行1627-1644)
```

**依赖**:
- `API_BASE`, `currentUser`, `escapeHtml`, `renderMarkdown`, `getPoemTypeStyle`, `toLocalISOString`, `withButtonLoading` (来自 app.core.js)
- `withToken` (来自 app.validation.js)
- `fetchWithAuth`, `getAuthToken` (来自 app.auth.js)
- `LocalDrafts`, `toggleModal`, `closeModal`, `showLoading`, `showEmptyState` (来自 app.ui.js)

---

### 6. `app.members.js` — 成员工具与社员管理模块

**原始行号**: 1646-2156

**包含内容**:
```
成员缓存与工具:
  - _cachedMembers                  (行1649)
  - ensureMembersCached()           (行1655-1666)
  - getDisplayNameById(id)          (行1673-1677)
  - getSmartDisplayName(id, name)   (行1685-1698)
  - editMemberClick(id)             (行1700-1703)
  - canManageMember(...)            (行1722-1735)
  - getAssignableRoles(role)        (行1741-1760)

社员管理CRUD:
  - _memberDisplayList, _memberPage, _memberHasMore  (行1765-1767)
  - editingMemberId, editingMemberOriginalRole       (行1878-1879)
  - fetchMembers(isLoadMore)        (行1775-1811)
  - renderMembers()                 (行1813-1876)
  - openMemberModal(member)         (行1881-1968)
  - submitMember()                  (行1970-2114)
  - deleteMember(id, event)         (行2120-2156)
```

**依赖**:
- `API_BASE`, `currentUser`, `ROLE_LEVEL`, `_customFields`, `formatRole`, `withButtonLoading` (来自 app.core.js)
- `canAssignRole`, `validateForm`, `validateCustomFields`, `showFieldError`, `clearFormErrors`, `withToken` (来自 app.validation.js)
- `fetchWithAuth`, `getAuthToken` (来自 app.auth.js)
- `toggleModal`, `closeModal`, `showLoading`, `showEmptyState` (来自 app.ui.js)

**被依赖方**: poems.js, business.js, home.js, admin.js（通过 `getSmartDisplayName`, `ensureMembersCached`）

---

### 7. `app.business.js` — 活动/财务/事务模块

**原始行号**: 2158-3066 (财务) + 2267-2793 (事务) + 2795-3139 (活动)

> 注：原始代码中财务和事务的行号有重叠区域，实际提取时按函数边界精确切分。

**包含内容**:
```
财务管理:
  - _cachedFinance, _financePage, _financeHasMore  (行2158-2160)
  - editingFinanceId                               (行2161)
  - fetchFinance(isLoadMore)        (行2168-2230)
  - renderFinance()                 (行2232-2262)
  - openFinanceModal(record)        (行2974-2999)
  - submitFinance()                 (行3001-3048)
  - deleteFinance(id)               (行3050-3066)

事务与积分:
  - _cachedTasks, _taskPage, _taskHasMore          (行2267-2269)
  - _editingTaskId                                 (行2422)
  - fetchTasks(isLoadMore)          (行2275-2323)
  - renderTasks()                   (行2325-2409)
  - getTaskStatusInfo(status)       (行2411-2419)
  - openTaskModal(task)             (行2424-2463)
  - submitTask()                    (行2465-2545)
  - claimTask(taskId)               (行2547-2580)
  - unclaimTask(taskId)             (行2582-2615)
  - submitTaskComplete(taskId)      (行2617-2650)
  - approveTask(taskId)             (行2652-2698)
  - forceApproveTask(taskId)        (行2700-2739)
  - rejectTask(taskId)              (行2741-2774)
  - deleteTask(taskId)              (行2776-2793)

活动管理:
  - _cachedActivities, _activityPage, _activityHasMore  (行2798-2800)
  - editingActivityId                                   (行2801)
  - _homeActivities                                     (行3068)
  - fetchActivities(isLoadMore)     (行2807-2835)
  - renderActivities()              (行2837-2870)
  - openActivityModal(activity)     (行2894-2913)
  - submitActivity()                (行2915-2958)
  - deleteActivity(id)              (行2960-2972)
  - openActivityDetailView(act)     (行3070-3128)
  - editActivityFromView(actId)     (行3130-3134)
  - deleteActivityInView(actId)     (行3136-3139)
```

**依赖**:
- `API_BASE`, `currentUser`, `escapeHtml`, `formatDate`, `getPointsName`, `getPoemTypeStyle`, `getStatusStyle`, `withButtonLoading` (来自 app.core.js)
- `withToken`, `validateForm` (来自 app.validation.js)
- `fetchWithAuth`, `getAuthToken` (来自 app.auth.js)
- `toggleModal`, `closeModal`, `showLoading`, `showEmptyState` (来自 app.ui.js)
- `getSmartDisplayName`, `ensureMembersCached` (来自 app.members.js)

---

### 8. `app.home.js` — 首页内容与全局搜索

**原始行号**: 3141-3587

**包含内容**:
```
首页内容:
  - _heatmapYearInited              (行3145)
  - _homeLatestPoems                (行3398)
  - loadWeeklyHeatmap(year)         (行3147-3160)
  - renderWeeklyHeatmap(data)       (行3162-3207)
  - loadSystemInfo()                (行3209-3395)
  - loadLatestPoems()               (行3400-3430)
  - openHomePoemDetail(poemId)      (行3432-3435)
  - loadPointsRanking()             (行3438-3476)

全局搜索:
  - _globalSearchTerm, _searchCache, _debounceTimer, _currentSearchReq  (行3479-3482)
  - openPoemFromSearch(poemId)      (行3484-3487)
  - openActivityFromSearch(actId)   (行3489-3491)
  - handleGlobalSearch()            (行3494-3573)
  - clearGlobalSearch()             (行3576-3587)
```

**依赖**:
- `API_BASE`, `currentUser`, `_systemSettings`, `escapeHtml`, `getPointsName`, `formatDate`, `getPoemTypeStyle` (来自 app.core.js)
- `fetchWithAuth` (来自 app.auth.js)
- `showSection`, `showLoading`, `showEmptyState` (来自 app.ui.js)
- `ensureMembersCached`, `getSmartDisplayName` (来自 app.members.js)
- `openPoemDetailView`, `openActivityDetailView`, `_cachedPoems` (来自 app.poems.js / app.business.js)

---

### 9. `app.admin.js` — 系统管理模块

**原始行号**: 3615-4682

**包含内容**:
```
系统设置与自定义字段:
  - fetchCustomFields()             (行3618-3623)
  - fetchSystemSettings()           (行3626-3656)
  - loadSystemSettingsUI()          (行3658-3669)
  - saveSystemName()                (行3671-3694)
  - savePointsName()                (行3696-3723)
  - savePasswordSalt()              (行3725-3761)
  - saveTokenExpireDays()           (行3763-3788)
  - loadSiteSettings()              (行3791-3812)
  - saveSiteSettings()              (行3815-3877)
  - addCustomFieldInput()           (行3884-3904)
  - deleteCustomField(id)           (行3906-3910)
  - saveCustomFields()              (行3912-3928)
  - renderAdminSettings()           (行3930-3951)
  - renderCustomFieldsList()        (行3954-3981)
  - editCustomField(id)             (行3984-4012)
  - saveCustomFieldEdit(id)         (行4015-4054)
  - cancelCustomFieldEdit(id)       (行4057-4059)

数据统计与日志:
  - loadDataStats()                 (行4062-4076)
  - loadCacheStats()                (行4079-4163)
  - fetchLoginLogs()                (行4189-4224)

WiFi配置:
  - toggleStaticIpFields()          (行4227-4233)
  - loadWifiConfig()                (行4235-4279)
  - saveWifiConfig()                (行4281-4368)

数据备份:
  - BACKUP_TABLE_NAMES              (行4372-4383)
  - showBackupProgress(...)         (行4386-4393)
  - updateBackupProgress(...)       (行4395-4400)
  - hideBackupProgress()            (行4402-4404)
  - exportBackup()                  (行4406-4530)
  - importBackup()                  (行4532-4682)
```

**依赖**:
- `API_BASE`, `currentUser`, `_systemSettings`, `_settingsLoaded`, `_customFields`, `withButtonLoading`, `formatBytes`, `formatUptime` (来自 app.core.js)
- `fetchWithAuth`, `getAuthToken`, `withToken` (来自 app.auth.js)
- `showLoading` (来自 app.ui.js)

---

### 10. `app.chat.js` — 聊天室模块

**原始行号**: 4685-5380

**包含内容**:
```
常量:
  - CHAT_MAX_CHARS                  (行4701)
  - CHAT_POLL_INTERVAL              (行4702)
  - HOME_CHAT_INTERVAL              (行4703)

状态变量:
  - _chatUserId, _chatUserName, _chatIsGuest       (行4689-4691)
  - _chatLastMsgId, _chatPollingTimer, _chatJoined  (行4692-4694)
  - _chatInputBound, _chatSending                   (行4695-4696)
  - _homeChatTimer, _homeChatLastMsgId, _homeChatMessages (行4697-4699)

聊天室核心:
  - resetChatState()                (行4708-4718)
  - initChat()                      (行4723-4749)
  - joinChat()                      (行4754-4782)
  - leaveChat()                     (行4787-4804)
  - startChatPolling()              (行4809-4817)
  - stopChatPolling()               (行4822-4827)
  - loadChatMessages(incremental)   (行4832-4866)
  - renderChatMessages(messages)    (行4871-4882)
  - appendChatMessages(messages)    (行4887-4900)
  - renderSingleMessage(msg)        (行4905-4923)
  - loadChatUsers()                 (行5007-5023)
  - renderChatUsers(users)          (行5028-5047)
  - loadChatStatus()                (行5052-5073)
  - updateChatCharCount()           (行5078-5092)
  - updateChatSendBtn()             (行5097-5104)
  - sendChatMessage()               (行5109-5167)

首页聊天预览:
  - updateHomeChatPreview(messages)  (行5172-5203)
  - loadHomeChatPreview()            (行5208-5249)
  - startHomeChatPolling()           (行5254-5259)
  - stopHomeChatPolling()            (行5264-5269)
  - checkChatEnabledAndLoad()        (行5274-5307)
  - updateHomeChatSendBtn()          (行5312-5318)
  - sendHomeChatMessage()            (行5323-5380)
```

**依赖**:
- `API_BASE`, `currentUser`, `escapeHtml`, `renderMarkdown`, `formatMessageTime`, `_systemSettings` (来自 app.core.js)
- `fetchWithAuth`, `getAuthToken` (来自 app.auth.js)

---

### 11. `app.main.js` — 初始化入口

**原始行号**: 3589-3614

**包含内容**:
```javascript
// window.onload 初始化逻辑
// - 调用 checkLogin() 启动认证流程
// - 绑定全局搜索输入框的 input 事件（防抖500ms）
// - 合并原 index.html 行882-884 的页脚年份设置脚本
```

**依赖**: 所有前面的模块（运行时调用）

---

## 四、文件依赖关系图

```
加载顺序（从上到下）：

  [marked.umd.js]  [purify.min.js]    ← 第三方库
         │               │
         └───────┬────────┘
                 ▼
         ┌──────────────┐
     ①   │  app.core.js │   常量 + 工具函数
         └──────┬───────┘
                │
         ┌──────▼───────┐
     ②   │app.validation│   表单验证
         └──────┬───────┘
                │
         ┌──────▼───────┐
     ③   │  app.auth.js │   认证 + 权限
         └──────┬───────┘
                │
         ┌──────▼───────┐
     ④   │  app.ui.js   │   UI工具 + SPA路由
         └──────┬───────┘
                │
    ┌───────────┼───────────┐
    │           │           │
    ▼           ▼           │
┌────────┐ ┌─────────┐     │
│app.poems│ │app.members│    │  ⑤⑥ 业务数据
└────┬───┘ └────┬────┘     │
     │          │           │
     └────┬─────┘           │
          ▼                 │
    ┌──────────┐            │
⑦   │app.business│          │  活动+财务+事务
    └─────┬────┘            │
          │                 │
    ┌─────▼────┐     ┌─────▼────┐
⑧   │ app.home │     │app.admin │  ⑨
    └─────┬────┘     └─────┬────┘
          │                │
          │          ┌─────▼────┐
          │      ⑩   │ app.chat │
          │          └─────┬────┘
          │                │
          └────────┬───────┘
                   ▼
            ┌──────────┐
        ⑪   │ app.main │   初始化
            └──────────┘
```

---

## 五、需要修改的关联文件

### 5.1 `src/static/index.html`

**修改位置**: 行 879-884

**修改前**:
```html
<script src="/static/marked.umd.js"></script>
<script src="/static/purify.min.js"></script>
<script src="/static/app.js"></script>
<script>
    document.getElementById('footer-year').textContent = new Date().getFullYear();
</script>
```

**修改后**:
```html
<script src="/static/marked.umd.js"></script>
<script src="/static/purify.min.js"></script>
<script src="/static/app.core.js"></script>
<script src="/static/app.validation.js"></script>
<script src="/static/app.auth.js"></script>
<script src="/static/app.ui.js"></script>
<script src="/static/app.poems.js"></script>
<script src="/static/app.members.js"></script>
<script src="/static/app.business.js"></script>
<script src="/static/app.home.js"></script>
<script src="/static/app.admin.js"></script>
<script src="/static/app.chat.js"></script>
<script src="/static/app.main.js"></script>
```

> 内联的页脚年份脚本合并到 `app.main.js` 中。

### 5.2 `src/main.py`

**修改位置**: 行 455-462 附近

**替换原有路由**:
```python
# 原: @app.route('/static/app.js')
# 替换为以下路由

@app.route('/static/app.core.js')
def app_core_js(request): return send_file('static/app.core.js')
@app.route('/static/app.validation.js')
def app_validation_js(request): return send_file('static/app.validation.js')
@app.route('/static/app.auth.js')
def app_auth_js(request): return send_file('static/app.auth.js')
@app.route('/static/app.ui.js')
def app_ui_js(request): return send_file('static/app.ui.js')
@app.route('/static/app.poems.js')
def app_poems_js(request): return send_file('static/app.poems.js')
@app.route('/static/app.members.js')
def app_members_js(request): return send_file('static/app.members.js')
@app.route('/static/app.business.js')
def app_business_js(request): return send_file('static/app.business.js')
@app.route('/static/app.home.js')
def app_home_js(request): return send_file('static/app.home.js')
@app.route('/static/app.admin.js')
def app_admin_js(request): return send_file('static/app.admin.js')
@app.route('/static/app.chat.js')
def app_chat_js(request): return send_file('static/app.chat.js')
@app.route('/static/app.main.js')
def app_main_js(request): return send_file('static/app.main.js')
```

---

## 六、实施步骤

### 步骤 1：创建基础层文件
1. 创建 `app.core.js` — 提取全局常量和散落各处的工具函数
2. 创建 `app.validation.js` — 提取表单验证模块（行148-425）
3. 创建 `app.auth.js` — 提取认证模块（行547-1047）

### 步骤 2：创建 UI 层
4. 创建 `app.ui.js` — 提取 UI 工具和导航模块（行449-545 + 1050-1202）

### 步骤 3：创建业务数据层
5. 创建 `app.poems.js` — 提取诗歌管理（行1204-1644）
6. 创建 `app.members.js` — 提取成员工具+社员管理（行1646-2156）
7. 创建 `app.business.js` — 提取活动+财务+事务（行2158-3139）

### 步骤 4：创建功能层
8. 创建 `app.home.js` — 提取首页+搜索（行3141-3587）
9. 创建 `app.admin.js` — 提取系统管理（行3615-4682）
10. 创建 `app.chat.js` — 提取聊天室（行4685-5380）
11. 创建 `app.main.js` — 提取初始化逻辑（行3589-3614 + index.html 内联脚本）

### 步骤 5：更新引用
12. 修改 `index.html` — 更新 script 标签
13. 修改 `main.py` — 注册新路由，移除旧 app.js 路由

### 步骤 6：验证
14. 逐模块功能验证（见下方测试清单）
15. 确认无 JS 报错（浏览器控制台）

---

## 七、验证测试清单

| 测试项 | 验证内容 | 涉及文件 |
|--------|---------|---------|
| 页面加载 | 无 JS 控制台报错，首页正常渲染 | core, auth, ui, main |
| 登录/登出 | Token 存取、导航栏切换、权限控制 | auth |
| 个人资料 | 修改昵称、修改密码 | auth |
| 诗歌管理 | 发布、编辑、草稿保存/恢复、撤回、删除 | poems |
| 社员管理 | 新增、编辑、删除、角色分配 | members |
| 活动管理 | 新增、编辑、删除、详情查看 | business |
| 事务管理 | 新增、领取、提交、审批、退回 | business |
| 财务管理 | 新增、编辑、删除、统计数据 | business |
| 首页内容 | 系统信息、最新诗作、热力图、积分排行 | home |
| 全局搜索 | 搜索诗歌/活动/事务，防抖生效 | home |
| 系统设置 | 保存系统名称、积分名称、站点设置 | admin |
| 自定义字段 | 添加、编辑、删除字段 | admin |
| WiFi 配置 | 加载/保存 WiFi 参数 | admin |
| 数据备份 | 导出/导入数据，进度条显示 | admin |
| 聊天室 | 加入、发消息、轮询刷新、退出 | chat |
| 首页聊天预览 | 消息预览、快速发送 | chat |
| 移动端适配 | 菜单切换、模态框、布局 | ui |

---

## 八、风险与注意事项

1. **加载顺序严格**: script 标签顺序不可调换，否则函数调用会报 `undefined`
2. **全局命名冲突**: 拆分后所有函数仍在全局作用域，需确保无同名覆盖
3. **showSection 的延迟绑定**: 该函数内部调用 `fetchPoems()` 等，这些函数在后续文件中定义，需确保 `showSection` 仅在用户交互时（非加载时）调用
4. **HTTP 请求数增加**: 从 3 个 JS 文件增加到 13 个，ESP32 首次加载时间可能增加。HTTP/1.1 持久连接可缓解此问题
5. **ESP32 存储空间**: 11 个 JS 文件总大小与原 app.js 相当（~201KB），不会额外占用存储
6. **每个文件头部添加模块说明注释**: 标注该文件的职责和依赖关系，便于后续维护
