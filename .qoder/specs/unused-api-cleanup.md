# 清理后端未被前端使用的 API 接口

## 排查结论

通过对比后端 `src/main.py` 中定义的全部 70 个路由端点与前端 `src/static/app.js` 中的所有 API 调用，发现以下 **4 个后端接口完全没有被前端使用**：

| # | 路由 | 方法 | 函数名 | 行号 | 说明 |
|---|------|------|--------|------|------|
| 1 | `/api/tasks/complete` | POST | `complete_task()` | 1451-1490 | 快速完成任务（一步到位）。前端使用 claim->submit->approve 分步流程 |
| 2 | `/api/backup/export` | GET | `backup_export()` | 2360-2412 | 全站数据一次性导出。前端使用分表 `export-table` 替代 |
| 3 | `/api/backup/import` | POST | `backup_import()` | 2414-2568 | 全站数据一次性导入。前端使用分表 `import-table` 替代 |
| 4 | `/api/backup/tables` | GET | `backup_list_tables()` | 2582-2586 | 获取可备份表列表。前端在 `BACKUP_TABLE_NAMES` 中硬编码了表名 |

## 影响分析

- `complete_task` 内部调用的 `record_points_change` 在其他路由中仍有使用（approve_task, update_member），删除该函数不影响其他功能。
- `backup_export` / `backup_import` 是被分表备份 API（`export-table` / `import-table`）完全替代的旧方案，且全量导出在 ESP32 内存受限环境下存在 OOM 风险。
- `BACKUP_TABLES` 字典被保留的 `export-table` 和 `import-table` 路由使用，**不可删除**。
- 这 4 个函数均为独立的路由处理函数，彼此之间和与其他代码之间没有被调用依赖。

## 修改计划

### 文件：`src/main.py`

1. **删除 `complete_task` 函数**（第 1451-1490 行）
   - 删除 `@api_route('/api/tasks/complete', ...)` 装饰器及整个函数体

2. **删除 `backup_export` 函数**（第 2360-2412 行）
   - 删除 `@api_route('/api/backup/export')` 装饰器及整个函数体

3. **删除 `backup_import` 函数**（第 2414-2568 行）
   - 删除 `@api_route('/api/backup/import', ...)` 装饰器及整个函数体

4. **删除 `backup_list_tables` 函数**（第 2582-2586 行）
   - 删除 `@api_route('/api/backup/tables')` 装饰器及整个函数体

### 保留不动

- `BACKUP_TABLES` 字典（第 2572-2580 行）— 被 `export-table` / `import-table` 路由使用
- `record_points_change` 函数 — 被 `approve_task` / `update_member_route` 使用

## 预计效果

- 移除约 250 行无效代码
- 减少 Flash 占用，优化 ESP32 资源利用
- 消除全量备份导出/导入的 OOM 风险入口

## 验证方式

1. 删除后对 `main.py` 做语法检查：`python3 -c "import ast; ast.parse(open('src/main.py').read())"`
2. 全局搜索确认无残留引用：grep 删除的函数名确认不存在其他调用
3. 前端功能不受影响（这些 API 本就未被调用）
