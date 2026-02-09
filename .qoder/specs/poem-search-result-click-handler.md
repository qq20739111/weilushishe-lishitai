# 搜索结果点击诗词 -> 打开渲染详情页（而非编辑框）

## 问题
搜索列表中点击诗词结果，当前调用 `openPoemModal(p)` 打开编辑表单，应改为打开只读渲染详情视图。

## 方案
参照活动模块已有的 `modal-activity-view` + `openActivityDetailView()` 模式，为诗词新建独立的详情模态框。

## 涉及文件

| 文件 | 改动类型 |
|------|---------|
| `src/static/index.html` | 在 `modal-poem`(677行) 之后插入新模态框 `modal-poem-view` |
| `src/static/app.js` | 新增 `openPoemDetailView(poem)` 和 `editPoemFromView()`；修改 `openPoemFromSearch()` |
| `src/static/style.css` | 新增 `.poem-detail-meta` 元信息卡片样式 |

## 实施步骤

### 1. HTML - 新增诗词详情模态框 (`index.html` 第677行之后)

参照 `modal-activity-view`(793-805行) 结构：

```html
<div id="modal-poem-view" class="modal hidden">
    <div class="modal-content" style="max-width:700px;">
        <span class="close" onclick="toggleModal('modal-poem-view')"></span>
        <!-- 标题 + 类型徽章 -->
        <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-top:35px; margin-bottom:20px;">
            <h3 id="view-poem-title" style="margin:0; flex:1; padding-right:12px;"></h3>
            <span id="view-poem-type" style="flex-shrink:0;"></span>
        </div>
        <!-- 元信息 + 正文 -->
        <div id="view-poem-container"></div>
        <!-- 操作按钮 -->
        <div id="view-poem-actions" style="margin-top:20px; padding-top:15px; border-top:1px solid #eee; display:flex; justify-content:flex-end; gap:10px;"></div>
    </div>
</div>
```

### 2. JS - 新增 `openPoemDetailView(poem)` (app.js 第1373行之后)

功能：
- 填充标题 (`escapeHtml`)
- 类型徽章 (`getPoemTypeStyle`)
- 元信息卡片：作者 (`getSmartDisplayName`)、日期、草稿标识
- 正文：`renderMarkdown(poem.content)` + `poem-body markdown-content` CSS类
- 权限判定（复用 renderPoems 中的逻辑 1287-1288行）：
  - `isAuthor`: `currentUser && (p.author_id === currentUser.id || p.author === currentUser.name || p.author === currentUser.alias)`
  - `isPoemAdmin`: `currentUser && ['super_admin','admin'].includes(currentUser.role)`
  - `canManage`: `isPoemAdmin || p.isLocal || isAuthor`
- 有权限时显示"修订"按钮，调用 `editPoemFromView()`
- 调用 `toggleModal('modal-poem-view')`

### 3. JS - 新增 `editPoemFromView(poemId, isLocal)` (紧跟上述函数之后)

参照 `editActivityFromView()`(app.js:3216-3220)：
1. `toggleModal('modal-poem-view')` 关闭详情
2. 从 `_cachedPoems` 或 `_searchCache.poems` 查找诗词对象（用 `==` 兼容字符串/数字ID）
3. 调用 `openPoemModal(poem)` 进入编辑

### 4. JS - 修改 `openPoemFromSearch()` (app.js:3556-3558)

```javascript
// 修改前
if(p) openPoemModal(p);
// 修改后
if(p) openPoemDetailView(p);
```

### 5. CSS - 新增元信息样式 (`style.css`)

在 `.poem-meta` 相关样式之后添加：

```css
.poem-detail-meta {
    background: #f8f9fa;
    padding: 15px;
    border-radius: 8px;
    margin-bottom: 20px;
    font-size: 0.95rem;
}
```

移动端媒体查询中添加：
```css
#modal-poem-view .modal-content {
    max-width: 95% !important;
}
```

## 验证方式
1. 启动服务，打开搜索框输入关键词
2. 点击诗词搜索结果 -> 应弹出只读详情视图（Markdown渲染正文、作者、日期、类型徽章）
3. 以作者/管理员身份登录 -> 详情视图底部应显示"修订"按钮
4. 点击"修订" -> 关闭详情视图，打开编辑表单
5. 普通用户查看他人诗词 -> 不显示修订按钮
6. 移动端测试模态框宽度适配
