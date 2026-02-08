# 清理前端 CSS 无效代码

## 目标文件
- `src/static/style.css`

## 分析方法
对 `style.css` 中定义的所有 CSS 选择器，与 `index.html` 和 `app.js`（含动态生成的 HTML）中实际使用的 class/id 进行交叉比对，找出完全不匹配任何 DOM 元素的选择器。

## 确认需要删除的无效 CSS 代码（共 8 组）

### 1. `.dashboard-grid` / `.dash-item` 系列（旧仪表盘布局）
- **行号**: 246-260（基础样式），1014-1023（移动端覆盖），1112-1114（平板端覆盖）
- **原因**: HTML 和 JS 中无任何元素使用 `dashboard-grid` 或 `dash-item` 类名。已被 `.system-status-grid` + `.stats-grid` 取代。
- **删除内容**:
  ```css
  /* 基础 */
  .dashboard-grid { ... }          /* L246-250 */
  .dash-item { ... }               /* L251-258 */
  .dash-item span { ... }          /* L259 */
  .dash-item strong { ... }        /* L260 */
  /* 移动端 @media (max-width: 767px) 内 */
  .dashboard-grid { ... }          /* L1014-1017 */
  .dash-item { ... }               /* L1018-1020 */
  .dash-item strong { ... }        /* L1021-1023 */
  /* 平板端 @media (max-width: 1279px) 内 */
  .dashboard-grid { ... }          /* L1112-1114 */
  ```

### 2. `.nav-user` 样式（旧导航用户显示）
- **行号**: 75-83（基础样式），923（移动端联合选择器中）
- **原因**: HTML 中只使用了 `nav-user-link`，无任何元素使用 `nav-user` 类名。
- **删除内容**:
  ```css
  /* 基础 - 整块删除 */
  .nav-user { ... }                /* L75-83 */
  /* 移动端 - 从联合选择器中移除 .nav-user, */
  .nav-user,                       /* L923 - 只删 .nav-user, 保留 .nav-user-link */
  ```

### 3. `.stats-card` 样式（旧统计卡片容器）
- **行号**: 751-756（基础样式），951（移动端覆盖）
- **原因**: HTML 和 JS 中无任何元素使用 `stats-card` 类名。注意：`.stat-item` 仍被 `.finance-details` 使用，不删除。
- **删除内容**:
  ```css
  .stats-card { ... }              /* L751-756 */
  /* 移动端 @media 内 */
  .stats-card { flex-wrap: wrap; } /* L951 */
  ```

### 4. `.field-item` 系列（旧字段列表项）
- **行号**: 1307-1325
- **原因**: HTML 和 JS 中无任何元素使用 `field-item` 类名。已被 `.custom-field-item` 取代。
- **删除内容**:
  ```css
  .field-item { ... }              /* L1307-1315 */
  .field-item span { ... }         /* L1317-1320 */
  .field-item button { ... }       /* L1322-1325 */
  ```

### 5. `.section` / `.section.active` / `@keyframes fadeIn`（旧页面切换机制）
- **行号**: 166-174
- **原因**: HTML 中的 `<section>` 元素没有添加 `section` 类名（`.section` 是类选择器，不匹配 `<section>` 元素标签）。JS 的 `showSection()` 函数使用 `hidden` 类管理显隐，不依赖 `.section` 类。`fadeIn` 动画仅被 `.section.active` 引用，也随之失效。
- **删除内容**:
  ```css
  .section { display: none; }                          /* L166 */
  .section.active { display: block; animation: ... }   /* L167-170 */
  @keyframes fadeIn { ... }                            /* L171-174 */
  ```

### 6. `.poem-card::before`（旧图标残留）
- **行号**: 610
- **原因**: `.poem-card` 没有任何其他地方定义 `::before` 的 `content`，此规则 `display: none` 是移除一个不存在的旧图标，纯粹的死代码。注释也说明了 `/* Remove old icon */`。
- **删除内容**:
  ```css
  .poem-card::before { display: none; }  /* L610 */
  ```

### 7. `.main-app`（选择器类型错误）
- **行号**: 947-949（移动端 @media 内）
- **原因**: HTML 中 `main-app` 是 ID（`id="main-app"`），但 CSS 用了类选择器 `.main-app`，永远不会匹配。
- **删除内容**:
  ```css
  /* 移动端 @media (max-width: 767px) 内 */
  .main-app { margin-top: 20px; }  /* L947-949 */
  ```

## 不删除的注意事项

- `.stat-item` 系列（L757-760, L952-953）：虽然 `.stats-card` 已废弃，但 `.stat-item` 仍被 `.finance-details` 内元素使用，保留不动。
- `.nav-user-link`：仅删除联合选择器中的 `.nav-user,` 部分，保留 `.nav-user-link` 规则。
- 所有 CSS 变量、元素选择器、Markdown 样式等均确认在使用中。

## 预估节省
删除约 **60 行** CSS 代码。

## 验证方式
1. 修改完成后，对比 HTML 和 JS 确认没有误删在用选择器
2. 用 grep 搜索所有被删选择器的类名，确认无残留引用
3. 如条件允许，在浏览器中打开页面确认各功能模块（首页、藏诗阁、活动、财务、社员、系统管理、聊天室）的显示和交互正常
