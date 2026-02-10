# 围炉诗社·理事台 - 冗余代码清理与重构方案

## 清理范围
- 只清理代码，不动 .jsonl 数据文件
- 删除死代码 + 重复逻辑提取 + CSS 去重 + 代码结构优化

## 涉及文件
1. `src/main.py`
2. `src/lib/Auth.py`
3. `src/static/app.js`
4. `src/static/style.css`
5. `src/static/index.html`

---

## 第一阶段: 删除死代码

### 1.1 删除后端 `check_login_get()` 函数
- **文件**: `src/main.py` 第 357-371 行
- **原因**: 定义但从未被调用，全局搜索仅在定义处出现
- **操作**: 整段删除（15 行）

### 1.2 删除后端 `check_login()` 函数，统一使用 `check_token()`
- **文件**: `src/main.py`
- **原因**: `check_login()` (main.py:341-355) 和 `check_token()` (Auth.py:111-126) 功能完全相同，返回值格式一致 `(bool, user_id, Response)`
- **操作**:
  1. 将 3 处 `check_login(request)` 调用替换为 `check_token(request)`:
     - main.py:983 `ok, _, err = check_login(request)` -> `ok, _, err = check_token(request)`
     - main.py:1200 `ok, user_id, err = check_login(request)` -> `ok, user_id, err = check_token(request)`
     - main.py:1382 `ok, token_user_id, err = check_login(request)` -> `ok, token_user_id, err = check_token(request)`
  2. 删除 `check_login()` 函数定义（main.py:341-355，15 行）

### 1.3 删除前端 `submitPoem()` 函数
- **文件**: `src/static/app.js` 第 3053-3105 行（含上方注释 `// Submissions`）
- **原因**: 定义但从未被调用，系统实际使用 `publishPoem()` 和 `submitPoemUpdate()`
- **操作**: 整段删除（约 53 行）

---

## 第二阶段: 后端 Token 提取逻辑去重

### 2.1 在 Auth.py 新增 `extract_token(request)` 工具函数
- **文件**: `src/lib/Auth.py`，在 `check_token()` 函数之前（约第 111 行前）插入
- **新增代码**:
```python
def extract_token(request):
    """从请求中提取Token（优先Header，回退到请求体）"""
    token = request.headers.get('authorization', '').replace('Bearer ', '')
    if not token and request.json:
        token = request.json.get('token', '')
    return token
```

### 2.2 重构 `check_token()` 使用 `extract_token()`
- **文件**: `src/lib/Auth.py` 第 117-120 行
- **改动**: 将 4 行 Token 提取代码替换为 `token = extract_token(request)`

### 2.3 重构 `get_operator_role()` 使用 `extract_token()`
- **文件**: `src/main.py` 第 263-268 行
- **改动**:
  - 删除 `data = request.json if request.json else {}`（第 263 行）
  - 将 3 行 Token 提取代码替换为 `token = extract_token(request)`
- **前提**: 在 main.py import 语句中增加 `extract_token`

### 2.4 重构 `require_login` 装饰器使用 `extract_token()`
- **文件**: `src/main.py` 第 299-303 行
- **改动**:
  - 删除 `data = request.json if request.json else {}`（第 300 行）
  - 将 3 行 Token 提取代码替换为 `token = extract_token(request)`

### 2.5 更新 main.py 的 import 语句
- **文件**: `src/main.py` 第 21-22 行
- **改动**: 在 `from lib.Auth import` 中增加 `extract_token`

---

## 第三阶段: 前端按钮状态管理去重

### 3.1 在 style.css 新增按钮禁用状态样式类
- **文件**: `src/static/style.css`
- **新增代码**（在按钮样式区域附近）:
```css
.btn-loading {
    background: #999 !important;
    color: #fff !important;
    border-color: #999 !important;
    cursor: not-allowed;
    opacity: 0.7;
}
```
- **原因**: 项目规范要求「JS 控制页面变化可结合 CSS 来控制外观变化」「尽量避免直接添加行内样式」，用 CSS class 替代 5 处重复的行内 style 设置

### 3.2 在 app.js 新增 `withButtonLoading()` 工具函数
- **文件**: `src/static/app.js`，插入到现有工具函数区域（约第 425 行附近）
- **新增代码**:
```javascript
async function withButtonLoading(btn, loadingText, action) {
    if (!btn) return await action();
    const oldText = btn.innerText;
    btn.disabled = true;
    btn.innerText = loadingText;
    btn.classList.add('btn-loading');
    try {
        return await action();
    } finally {
        btn.classList.remove('btn-loading');
        btn.innerText = oldText;
        btn.disabled = false;
    }
}
```

### 3.3 重构 5 个删除函数，使用 `withButtonLoading()`
每个函数删除约 12 行重复的 btn.style.* 代码，改用 `withButtonLoading()` 包裹：

1. **`deletePoemWrapper()`** - app.js:1610-1646
2. **`deleteMember()`** - app.js:2126-2183
3. **`deleteTask()`** - app.js:2811-2849
4. **`deleteActivity()`** - app.js:3020-3050
5. **`deleteFinance()`** - app.js:3183-3218

每个函数重构模式：
```javascript
// 改造前（每个函数重复 ~12 行）:
const btn = event?.target;
const oldText = btn ? btn.innerText : '';
const oldStyle = btn ? btn.style.cssText : '';
if (btn) { btn.disabled = true; btn.innerText = '删除中...'; btn.style.background = '#999'; ... }
try { ... } finally { if(btn) { btn.style.cssText = oldStyle; btn.innerText = oldText; btn.disabled = false; } }

// 改造后:
await withButtonLoading(event?.target, '删除中...', async () => { ... });
```

**净节省**: 删除 ~60 行行内样式代码，新增 ~12 行工具函数

---

## 第四阶段: 前端 loadMore 包装函数精简

### 4.1 删除 5 个 loadMore 包装函数，内联替换
每个函数仅一行代码调用对应的 fetch 函数：

| 包装函数 | 位置 | 替换为 |
|---------|------|--------|
| `loadMorePoems()` | app.js:1249-1251 | `fetchPoems(true)` |
| `loadMoreMembers()` | app.js:1815-1817 | `fetchMembers(true)` |
| `loadMoreFinance()` | app.js:2259-2261 | `fetchFinance(true)` |
| `loadMoreTasks()` | app.js:2356-2358 | `fetchTasks(true)` |
| `loadMoreActivities()` | app.js:2893-2895 | `fetchActivities(true)` |

### 4.2 修改 HTML onclick 绑定
- **文件**: `src/static/index.html`
  - 第 620 行: `onclick="loadMorePoems()"` -> `onclick="fetchPoems(true)"`
  - 第 630 行: `onclick="loadMoreActivities()"` -> `onclick="fetchActivities(true)"`
  - 第 659 行: `onclick="loadMoreFinance()"` -> `onclick="fetchFinance(true)"`
  - 第 669 行: `onclick="loadMoreTasks()"` -> `onclick="fetchTasks(true)"`
  - 第 679 行: `onclick="loadMoreMembers()"` -> `onclick="fetchMembers(true)"`

### 4.3 修改 JS 中的动态 onclick 赋值
- **文件**: `src/static/app.js` 第 1272 行
  - `loadMoreBtn.onclick = loadMorePoems;` -> `loadMoreBtn.onclick = () => fetchPoems(true);`

---

## 第五阶段: CSS 进度条样式去重

### 5.1 删除冗余的进度条子类样式
- **文件**: `src/static/style.css` 第 291-313 行

**分析**:
- `.status-bar-wifi` (第303行) 的渐变与 `.status-bar-fill` (第276行) 完全相同 -> 冗余
- `.status-bar-wifi.weak` (第307行) 与 `.status-bar-fill.warning` (第283行) 完全相同 -> 冗余
- `.status-bar-wifi.poor` (第311行) 与 `.status-bar-fill.danger` (第287行) 完全相同 -> 冗余
- `.status-bar-temp.warm` (第295行) 与 `.status-bar-fill.warning` (第283行) 完全相同 -> 冗余
- `.status-bar-temp.hot` (第299行) 与 `.status-bar-fill.danger` (第287行) 完全相同 -> 冗余
- `.status-bar-temp` (第291行) 有独特的蓝色渐变 -> 保留

**操作**:
1. 删除 `.status-bar-wifi` 定义（第303-304行）- 与 `.status-bar-fill` 完全相同
2. 将 `.status-bar-wifi.weak` 和 `.status-bar-temp.warm` 改为统一使用 `.warning`
3. 将 `.status-bar-wifi.poor` 和 `.status-bar-temp.hot` 改为统一使用 `.danger`
4. 同步修改 app.js 中动态添加 class 的代码，将 `warm/hot/weak/poor` 替换为 `warning/danger`
5. 同步修改 index.html 中 `status-bar-wifi` class 的使用

### 5.2 合并按钮样式公共部分
- **文件**: `src/static/style.css` 第 715-772 行

**分析**: `.member-actions .btn-edit` 和 `.btn-edit-sm` 共享相似的基础样式（transparent背景、var(--accent)颜色、圆角、hover效果），仅尺寸不同。`.member-actions .btn-remove` 和 `.btn-del-sm` 同理。

**操作**: 合并公共部分为联合选择器
```css
.member-actions .btn-edit, .btn-edit-sm {
    background: transparent; color: var(--accent); border: 1px solid var(--accent);
    cursor: pointer; transition: all 0.2s;
}
.member-actions .btn-edit:hover, .btn-edit-sm:hover {
    background: var(--accent); color: white;
}
/* 尺寸差异保留在各自选择器中 */
.member-actions .btn-edit { padding: 5px 14px; font-size: 0.75rem; border-radius: 15px; }
.btn-edit-sm { padding: 3px 10px; font-size: 0.7rem; border-radius: 12px; margin: 2px; }
```

同理处理删除按钮。

---

## 改动量汇总

| 阶段 | 操作 | 净减少行数 |
|------|------|-----------|
| 1.1 | 删除 `check_login_get()` | -15 行 |
| 1.2 | 删除 `check_login()`，替换调用 | -15 行 |
| 1.3 | 删除 `submitPoem()` | -53 行 |
| 2.x | Token 提取去重 | -4 行（+8 新函数, -12 重复） |
| 3.x | 按钮状态管理去重 | -48 行（+15 新函数+CSS, -63 重复行内样式） |
| 4.x | loadMore 函数精简 | -15 行 |
| 5.x | CSS 去重 | -18 行 |
| **合计** | | **约 -168 行** |

---

## 验证方案

### 每步完成后的快速验证
1. 用 `grep` 确认被删代码无残留引用
2. 用 `mcp__quest__get_problems` 检查修改文件的语法问题

### 全流程回归测试（所有阶段完成后）
部署到 ESP32 或在浏览器中测试:
- [ ] 登录/登出（正常登录、密码错误、Token 过期）
- [ ] 诗歌管理（新建、编辑、发布、草稿、删除、撤回）
- [ ] 成员管理（录入、编辑、删除、权限分配）
- [ ] 活动管理（新建、编辑、删除、详情查看）
- [ ] 事务管理（发布、领取、提交、审批、拒绝、删除）
- [ ] 财务管理（录入、编辑、删除、统计）
- [ ] 所有列表页"加载更多"按钮功能正常
- [ ] 系统管理页面 CPU/WiFi 进度条显示正常
- [ ] 删除操作按钮禁用效果正常（点击后变灰、操作完成后恢复）
- [ ] 移动端响应式布局无异常
