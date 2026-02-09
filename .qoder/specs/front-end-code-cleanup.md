# 前端废弃/无效代码清理计划

## 目标
清理 `src/static/app.js` 和 `src/static/index.html` 中完全未被使用的函数定义及相关废弃代码。

## 涉及文件
- `src/static/app.js` (5168 行)
- `src/static/index.html` (801 行)

## 排查结果

经过全面分析所有函数定义、HTML 内联事件处理器、JS 内部调用和动态生成 HTML 中的引用，确认以下 **6 个函数** 完全未被使用：

### 需删除的函数

| # | 函数名 | 位置 (app.js) | 说明 |
|---|--------|--------------|------|
| 1 | `showAllPoems()` | ~行 1260-1263 | 已弃用包装函数，仅调用 `loadMorePoems()`。需同步修改 index.html 中的 onclick |
| 2 | `completeTask()` | ~行 2693-2729 | 旧版任务完成函数，已被新的任务审批流程替代，无任何调用 |
| 3 | `checkMaintenanceMode()` | ~行 702-705 | 标注"保留旧函数名以兼容"，但从未被调用 |
| 4 | `getAuthQuery()` | ~行 789-797 | 构建带 Token 的 URL 查询参数，从未被调用（项目统一用 `fetchWithAuth` 或 Header 方式鉴权） |
| 5 | `getDisplayNameByName()` | ~行 1623-1627 | 按姓名获取显示名称，已被 `getSmartDisplayName()` 替代，从未被调用 |
| 6 | `triggerImportBackup()` | ~行 4328-4330 | 触发备份导入文件选择，HTML 中已直接用 `document.getElementById('backup-file-input').click()` 实现 |

### 保留的函数
- `leaveChat()` (行 4586) - 用户确认保留，作为未来功能预留

## 执行步骤

### 步骤 1: 修改 index.html
- 将 `index.html` 第 568 行 `onclick="showAllPoems()"` 改为 `onclick="loadMorePoems()"`

### 步骤 2: 删除 app.js 中的 6 个废弃函数
按从文件底部到顶部的顺序删除（避免行号偏移影响）：
1. 删除 `triggerImportBackup()` (~行 4328-4330, 含空行)
2. 删除 `completeTask()` (~行 2693-2729, 含注释和空行)
3. 删除 `showAllPoems()` (~行 1260-1263, 含注释和空行)
4. 删除 `getDisplayNameByName()` (~行 1622-1627, 含注释和空行)
5. 删除 `getAuthQuery()` (~行 785-797, 含 JSDoc 注释和空行)
6. 删除 `checkMaintenanceMode()` (~行 701-705, 含注释和空行)

## 验证
1. 全局搜索已删除的函数名，确认无残留引用
2. 在浏览器中打开页面，检查控制台无报错
3. 验证"查看更多作品"按钮功能正常（调用 `loadMorePoems()`）
