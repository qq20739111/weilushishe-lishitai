# 前后端接口一致性排查 - 财务编辑/删除功能补全

## 问题描述

后端已实现财务记录的编辑和删除接口，但前端完全缺失对应的 UI 和调用逻辑：
- `POST /api/finance/update` (main.py:1937) - 当前为 `ROLE_FINANCE` 权限，需改为 `ROLE_SUPER_ADMIN`
- `POST /api/finance/delete` (main.py:1961) - 当前为 `ROLE_FINANCE` 权限，需改为 `ROLE_SUPER_ADMIN`

**用户要求**: 编辑和删除财务记录仅限超级管理员操作。新增记账权限不变（`ROLE_FINANCE`：超管/管理员/财务）。

## 涉及文件

- `src/main.py` - 后端权限修改：finance/update 和 finance/delete 改为 `ROLE_SUPER_ADMIN`
- `src/static/app.js` - 添加编辑/删除 JS 逻辑，修改列表渲染和表单提交
- `src/static/index.html` - 表头增加"操作"列
- `src/static/style.css` - 财务操作按钮样式（如需要）

## 实现步骤

### 步骤0: main.py - 后端权限收紧为仅超级管理员

**位置**: main.py 第1937行和第1961行

将 `update_finance` 和 `delete_finance` 的权限从 `ROLE_FINANCE` 改为 `ROLE_SUPER_ADMIN`：
```python
# 原: @require_permission(ROLE_FINANCE)
@require_permission(ROLE_SUPER_ADMIN)
def update_finance(request):

# 原: @require_permission(ROLE_FINANCE)
@require_permission(ROLE_SUPER_ADMIN)
def delete_finance(request):
```

### 步骤1: app.js - 添加状态变量和缓存

在财务模块注释区域 (约 `async function fetchFinance()` 前方) 添加：
```javascript
let _cachedFinance = [];
let editingFinanceId = null;
```

### 步骤2: index.html - 财务表格表头添加操作列

**位置**: 第602-604行

将：
```html
<thead><tr><th>日期</th><th>摘要</th><th>金额</th><th>经办</th></tr></thead>
```
改为：
```html
<thead><tr><th>日期</th><th>摘要</th><th>金额</th><th>经办</th><th>操作</th></tr></thead>
```

### 步骤3: app.js - 修改 fetchFinance() 渲染逻辑

**位置**: 约第2107-2148行

关键改动：
1. 将 `records` 存入 `_cachedFinance` 缓存
2. 判断权限 `canRecord` 控制操作按钮显隐
3. 表格每行末尾添加操作列，包含编辑/删除按钮（遵循活动/成员模块模式）

渲染逻辑改为：
```javascript
_cachedFinance = records;  // 缓存数据

// 编辑/删除权限：仅超级管理员
const canEditFinance = currentUser && currentUser.role === 'super_admin';

tbody.innerHTML = records.map(r => `
<tr>
    <td>${r.date}</td>
    <td>${escapeHtml(r.summary)}<br><small>${escapeHtml(r.category)}</small></td>
    <td class="money ${r.type === 'income' ? 'plus' : 'minus'}">
        ${r.type === 'income' ? '+' : '-'}${r.amount}
    </td>
    <td>${escapeHtml(r.handler)}</td>
    <td>${canEditFinance ? `
        <button class="btn-edit-sm" onclick="openFinanceModal(${r.id})">编辑</button>
        <button class="btn-del-sm" onclick="deleteFinance(${r.id}, event)">删除</button>
    ` : ''}</td>
</tr>
`).join('');
```

### 步骤4: app.js - 添加 openFinanceModal() 函数

复用现有 `modal-finance` 弹窗，参照 `openActivityModal()` 模式：
```javascript
function openFinanceModal(id = null) {
    if (id) {
        // 编辑模式：从缓存查找记录填充表单
        const record = _cachedFinance.find(r => r.id === id);
        if (!record) return;
        editingFinanceId = id;
        document.querySelector('#modal-finance h3').innerText = '编辑财务记录';
        document.getElementById('f-type').value = record.type || 'income';
        document.getElementById('f-category').value = record.category || '会费';
        document.getElementById('f-amount').value = record.amount;
        document.getElementById('f-summary').value = record.summary || '';
        document.getElementById('f-handler').value = record.handler || '';
    } else {
        // 新建模式：清空表单
        editingFinanceId = null;
        document.querySelector('#modal-finance h3').innerText = '财务记账';
        document.getElementById('f-type').value = 'income';
        document.getElementById('f-category').value = '会费';
        document.getElementById('f-amount').value = '';
        document.getElementById('f-summary').value = '';
        document.getElementById('f-handler').value = '';
    }
    toggleModal('modal-finance');
}
```

同时修改 index.html 中"记一笔"按钮的 onclick 为 `openFinanceModal()`（当前是 `toggleModal('modal-finance')`）。

### 步骤5: app.js - 修改 submitFinance() 支持编辑模式

**位置**: 约第2938-2980行

关键改动：在 API 调用处区分新建和编辑（参照 `submitActivity()` 模式）：
```javascript
// 区分新建vs编辑
let url = `${API_BASE}/finance`;
if (editingFinanceId) {
    url = `${API_BASE}/finance/update`;
    data.id = editingFinanceId;
}

const response = await fetch(url, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(withToken(data))
});
```

编辑模式下保留原始日期（不覆盖为当天），新建时使用当天日期。

### 步骤6: app.js - 添加 deleteFinance() 函数

参照 `deleteActivity()` 模式，含确认弹窗和防重复提交：
```javascript
async function deleteFinance(id, event) {
    if (!confirm('确定删除此财务记录？此操作不可撤销。')) return;
    
    const btn = event?.target;
    const oldText = btn ? btn.innerText : '';
    const oldStyle = btn ? btn.style.cssText : '';
    if (btn) { btn.disabled = true; btn.innerText = '删除中...'; btn.style.background = '#999'; btn.style.color = '#fff'; btn.style.borderColor = '#999'; }
    
    try {
        const res = await fetch(`${API_BASE}/finance/delete`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(withToken({id}))
        });
        if (res.ok) {
            fetchFinance();
        } else {
            const err = await res.json().catch(() => ({}));
            alert('删除失败: ' + (err.error || '未知错误'));
        }
    } catch(e) {
        alert('网络错误，请重试');
    } finally {
        if (btn) { btn.style.cssText = oldStyle; btn.innerText = oldText; btn.disabled = false; }
    }
}
```

### 步骤7: style.css - 添加表格内操作按钮样式

添加紧凑的表格行内按钮样式（编辑/删除），与现有 `.btn-edit` / `.btn-remove` 保持一致风格但更紧凑：
```css
.btn-edit-sm, .btn-del-sm {
    padding: 3px 10px;
    font-size: 0.7rem;
    border-radius: 12px;
    cursor: pointer;
    border: 1px solid;
    background: transparent;
    transition: all 0.2s;
    margin: 2px;
}
.btn-edit-sm {
    color: var(--accent);
    border-color: var(--accent);
}
.btn-edit-sm:hover {
    background: var(--accent);
    color: white;
}
.btn-del-sm {
    color: #999;
    border-color: #ddd;
}
.btn-del-sm:hover {
    background: #e74c3c;
    color: white;
    border-color: #e74c3c;
}
```

## 验证方案

1. 以 `super_admin` 角色登录 -> 财务页面应显示编辑/删除按钮
2. 点击编辑 -> 弹窗显示原数据 -> 修改后提交 -> 列表刷新显示新数据
3. 点击删除 -> 确认弹窗 -> 确认后记录消失、统计数据更新
4. 以 `admin` / `finance` / `director` / `member` 角色登录 -> 财务页面不显示编辑/删除按钮
5. 以 `finance` / `admin` 角色登录 -> "记一笔"按钮仍可正常使用（新增权限不变）
6. 全文搜索 `finance` 相关 fetch 调用，确认前后端完全对应
