# Markdown 渲染效果优化 + XSS 安全加固方案

## 修改文件清单

| 文件 | 修改类型 |
|------|---------|
| `src/static/purify.min.js` | **新增** - DOMPurify 库 |
| `src/static/index.html` (L797) | 添加 DOMPurify 脚本引用 |
| `src/static/app.js` (L4660-4681) | 修改 `renderMarkdown()` 集成 HTML 净化 |
| `src/static/style.css` (L2008-2154) | 增强 `.markdown-content` 基础样式 |
| `src/static/style.css` (L599-620) | 增强诗歌专属样式 |
| `src/static/style.css` (L828+) | 响应式媒体查询中补充 Markdown 适配 |

---

## 第一部分：XSS 安全加固

### 问题
`renderMarkdown()` 将 marked.js 生成的 HTML 直接通过 `innerHTML` 插入 DOM，未做任何净化。用户可在诗歌/事务/活动内容中注入 `<script>` 或 `<img onerror="...">` 等恶意代码。

### 方案：引入 DOMPurify
- 下载 `purify.min.js`（v3.2.4，约 20KB）到 `src/static/`
- 在 `index.html` 的 `marked.umd.js` 与 `app.js` 之间引入
- 修改 `renderMarkdown()` 函数，在返回前用 DOMPurify 净化

### 具体改动

**index.html** - 在 L797 `<script src="/static/marked.umd.js">` 之后添加：
```html
<script src="/static/purify.min.js"></script>
```

**app.js** - 修改 `renderMarkdown()` (L4660-4681)：
```javascript
function renderMarkdown(text) {
    if (!text) return '';
    
    marked.setOptions({
        gfm: true,
        breaks: true,
        pedantic: false,
        async: false
    });
    
    try {
        let html = marked.parse(text);
        html = html.replace(/<p>\s*<br\s*\/?>\s*<\/p>/gi, '<p class="empty-line">&nbsp;</p>');
        
        // XSS 防护：白名单净化
        if (typeof DOMPurify !== 'undefined') {
            html = DOMPurify.sanitize(html, {
                ALLOWED_TAGS: [
                    'h1','h2','h3','h4','h5','h6',
                    'p','br','hr','blockquote',
                    'ul','ol','li',
                    'strong','em','del','code','pre',
                    'a','img',
                    'table','thead','tbody','tr','th','td',
                    'input','span','div'
                ],
                ALLOWED_ATTR: [
                    'href','src','alt','title','class',
                    'type','checked','disabled'
                ],
                ALLOW_DATA_ATTR: false,
                ALLOW_UNKNOWN_PROTOCOLS: false
            });
        }
        
        return html;
    } catch (e) {
        console.error('Markdown parse error:', e);
        return escapeHtml(text);
    }
}
```

---

## 第二部分：CSS 渲染效果优化

### 分析：当前样式不足之处

1. **中文排版未优化**：缺少适合中文的字间距 (`letter-spacing`)，正文行高可进一步优化
2. **标题层级感弱**：h1-h6 仅有字号差异，缺少视觉分隔（如底部边线）
3. **引用块样式单薄**：仅左边框+斜体，缺少背景衬托
4. **诗歌场景不够雅致**：诗歌与普通内容使用近似样式，未体现文学气质
5. **表格移动端溢出**：宽表格无横向滚动容器
6. **场景无差异化**：事务、活动、诗歌全用同一套样式
7. **列表间距偏紧**：嵌套列表可读性差

### 2.1 增强基础 `.markdown-content` 样式 (style.css L2008-2154)

替换现有 `.markdown-content` 相关样式为以下内容：

```css
/* ==================== Markdown 内容样式 ==================== */
.markdown-content {
    line-height: 1.9;
    word-break: break-word;
    color: var(--text);
    letter-spacing: 0.02em;
}

/* --- 标题 --- */
.markdown-content h1,
.markdown-content h2,
.markdown-content h3,
.markdown-content h4,
.markdown-content h5,
.markdown-content h6 {
    margin: 1em 0 0.5em;
    font-weight: 600;
    line-height: 1.4;
    color: var(--primary);
}

.markdown-content h1 {
    font-size: 1.5em;
    padding-bottom: 0.3em;
    border-bottom: 2px solid var(--accent);
}
.markdown-content h2 {
    font-size: 1.3em;
    padding-bottom: 0.25em;
    border-bottom: 1px solid var(--border);
}
.markdown-content h3 { font-size: 1.15em; }
.markdown-content h4 { font-size: 1.05em; }

/* --- 段落 --- */
.markdown-content p {
    margin: 0.8em 0;
}
.markdown-content p.empty-line {
    margin: 0;
    line-height: 1.2;
}

/* --- 引用块 --- */
.markdown-content blockquote {
    border-left: 4px solid var(--accent);
    padding: 0.6em 1em;
    margin: 1em 0;
    background: rgba(0, 128, 128, 0.04);
    border-radius: 0 6px 6px 0;
    color: var(--text-muted);
}
.markdown-content blockquote p {
    margin: 0.4em 0;
}

/* --- 行内代码 --- */
.markdown-content code {
    background: #f0f2f5;
    padding: 2px 6px;
    border-radius: 4px;
    font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
    font-size: 0.88em;
    color: #c0392b;
}

/* --- 代码块 --- */
.markdown-content pre {
    background: #f6f8fa;
    padding: 14px 16px;
    border-radius: 8px;
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
    margin: 1em 0;
    border: 1px solid #e8eaed;
}
.markdown-content pre code {
    background: none;
    padding: 0;
    color: inherit;
    font-size: 0.9em;
    line-height: 1.6;
}

/* --- 水平线 --- */
.markdown-content hr {
    border: none;
    height: 1px;
    background: linear-gradient(to right, transparent, var(--border), transparent);
    margin: 1.5em 0;
}

/* --- 链接 --- */
.markdown-content a {
    color: var(--accent);
    text-decoration: none;
    border-bottom: 1px solid transparent;
    transition: border-color 0.2s;
}
.markdown-content a:hover {
    border-bottom-color: var(--accent);
}

/* --- 图片 --- */
.markdown-content img {
    max-width: 100%;
    height: auto;
    border-radius: 8px;
    margin: 0.8em 0;
    box-shadow: 0 2px 8px rgba(0,0,0,0.08);
}

/* --- 表格 --- */
.markdown-content table {
    width: 100%;
    border-collapse: collapse;
    margin: 1em 0;
    font-size: 0.95em;
    display: block;
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
}
.markdown-content th,
.markdown-content td {
    border: 1px solid var(--border);
    padding: 8px 12px;
    text-align: left;
    white-space: nowrap;
}
.markdown-content th {
    background: #f0f2f5;
    font-weight: 600;
    color: var(--primary);
}
.markdown-content tr:nth-child(even) {
    background: #fafbfc;
}

/* --- 列表 --- */
.markdown-content ul,
.markdown-content ol {
    padding-left: 1.8em;
    margin: 0.6em 0;
}
.markdown-content li {
    margin: 0.4em 0;
    line-height: 1.7;
}
.markdown-content li > ul,
.markdown-content li > ol {
    margin: 0.2em 0;
}

/* --- 文本修饰 --- */
.markdown-content del {
    text-decoration: line-through;
    color: #999;
}
.markdown-content strong {
    font-weight: 600;
    color: var(--text);
}
.markdown-content em {
    font-style: italic;
}

/* --- 任务列表复选框 --- */
.markdown-content input[type="checkbox"] {
    -webkit-appearance: none;
    -moz-appearance: none;
    appearance: none;
    width: 16px;
    height: 16px;
    min-width: 16px;
    padding: 0;
    margin: 0 6px 0 0;
    border: 1.5px solid var(--text-muted);
    border-radius: 3px;
    vertical-align: middle;
    cursor: default;
    background: #fff;
    display: inline-block;
    position: relative;
}
.markdown-content input[type="checkbox"]:checked {
    background: var(--accent);
    border-color: var(--accent);
}
.markdown-content input[type="checkbox"]:checked::after {
    content: '';
    position: absolute;
    left: 4px;
    top: 1px;
    width: 5px;
    height: 9px;
    border: solid #fff;
    border-width: 0 2px 2px 0;
    transform: rotate(45deg);
}
```

### 2.2 诗歌专属样式增强 (style.css L599-620)

在现有 `.poem-body` 样式后扩展：

```css
.poem-body.markdown-content {
    white-space: normal;
    font-family: "STKaiti", "KaiTi", "楷体", Georgia, serif;
    font-size: 1.12rem;
    line-height: 2.1;
    letter-spacing: 0.06em;
    color: #1a1a2e;
    padding: 0.5em 0;
}

/* 诗歌段落 - 诗行间留白 */
.poem-body.markdown-content p {
    margin: 0.6em 0;
}

/* 诗歌标题不需要边线 */
.poem-body.markdown-content h1,
.poem-body.markdown-content h2,
.poem-body.markdown-content h3 {
    font-family: "STKaiti", "KaiTi", "楷体", Georgia, serif;
    border: none;
    padding-bottom: 0;
    color: var(--text);
}

/* 诗歌引用 - 金色边框，古朴风格 */
.poem-body.markdown-content blockquote {
    border-left-color: #c9a96e;
    background: rgba(201, 169, 110, 0.06);
    font-style: normal;
}
```

### 2.3 事务描述场景样式（新增，追加到 Markdown 样式区域之后）

```css
/* --- 事务描述 --- */
.task-item .markdown-content {
    font-size: 0.95rem;
    line-height: 1.75;
    color: #555;
}
.task-item .markdown-content p {
    margin: 0.5em 0;
}
.task-item .markdown-content ul,
.task-item .markdown-content ol {
    background: #f8f9fa;
    padding: 0.6em 0.8em 0.6em 2.2em;
    border-radius: 6px;
}
```

### 2.4 活动详情场景样式（新增）

```css
/* --- 活动详情 --- */
#view-act-container .markdown-content {
    line-height: 1.85;
}
#view-act-container .markdown-content img {
    display: block;
    margin: 1.2em auto;
    box-shadow: 0 4px 16px rgba(0,0,0,0.1);
}
#view-act-container .markdown-content strong {
    color: var(--accent);
}
```

### 2.5 首页推荐诗歌样式（新增）

```css
/* --- 首页推荐诗歌 --- */
#daily-poem .markdown-content {
    font-family: "STKaiti", "KaiTi", "楷体", Georgia, serif;
    line-height: 2.0;
    letter-spacing: 0.05em;
    font-size: 1.05rem;
}
```

### 2.6 移动端响应式补充 (style.css L828 `@media` 块内)

在现有移动端 `@media (max-width: 767px)` 块末尾追加：

```css
/* Markdown 移动端适配 */
.markdown-content {
    font-size: 0.95rem;
    line-height: 1.8;
}
.markdown-content h1 { font-size: 1.3em; }
.markdown-content h2 { font-size: 1.15em; }
.markdown-content pre {
    font-size: 0.85em;
    padding: 10px;
}
.markdown-content th,
.markdown-content td {
    padding: 6px 8px;
    font-size: 0.88em;
}

.poem-body.markdown-content {
    font-size: 1.05rem;
    line-height: 1.9;
    letter-spacing: 0.04em;
}
```

---

## 验证方案

### 安全验证
1. 在藏诗阁提交包含 `<script>alert(1)</script>` 的诗歌内容，确认脚本被过滤
2. 提交包含 `<img src=x onerror="alert(1)">` 的事务描述，确认 `onerror` 被移除
3. 提交包含 `[link](javascript:alert(1))` 的活动描述，确认协议被拦截
4. 验证正常 Markdown 语法（加粗、列表、表格、代码块、引用、链接）渲染正常

### 样式验证
1. 在藏诗阁发布一首多段诗歌，确认楷书字体、行距、字间距效果
2. 发布一个包含列表+代码块+表格的事务描述，确认各元素样式
3. 发布一个包含引用+加粗+图片链接的活动详情，确认效果
4. 在移动端（< 768px）查看以上内容，确认响应式表现
5. 检查表格在窄屏下可横向滚动
