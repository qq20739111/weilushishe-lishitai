# 启动时清理数据库临时文件(.tmp)

## 需求
系统启动时扫描 `data/` 目录，查找并删除所有 `.tmp` 后缀的残留临时文件，防止因断电/崩溃导致的垃圾文件堆积。

## 修改文件

1. **`src/lib/JsonlDB.py`** - 添加模块级函数 `cleanup_temp_files()`
2. **`src/boot.py`** - 在启动流程中调用清理函数

## 实现细节

### 1. `src/lib/JsonlDB.py` - 文件末尾(第333行后)添加函数

```python
def cleanup_temp_files(data_dir='data'):
    """启动时清理残留的数据库临时文件"""
    cleaned = 0
    try:
        for f in os.listdir(data_dir):
            if f.endswith('.tmp'):
                path = data_dir + '/' + f
                try:
                    os.remove(path)
                    debug("清理临时文件: " + path, "DB")
                    cleaned += 1
                except Exception as e:
                    error("删除临时文件失败 " + path + ": " + str(e), "DB")
    except Exception as e:
        error("扫描临时文件失败: " + str(e), "DB")
    if cleaned:
        gc.collect()
    return cleaned
```

- 放在 `JsonlDB` 类外部，作为模块级工具函数
- 使用已有的 `debug`/`error` 日志函数（第7行已导入）
- 使用已有的 `gc`/`os` 模块（第5-6行已导入）
- 单文件删除失败不阻断循环，继续清理其他文件

### 2. `src/boot.py` - 第166行(`watchdog.feed()`)之后、第168行(`try: info(...)`)之前插入

```python
    # 清理残留的数据库临时文件
    try:
        from lib.JsonlDB import cleanup_temp_files
        n = cleanup_temp_files()
        if n:
            info("启动清理: 删除了 {} 个残留临时文件".format(n), "Boot")
    except Exception as e:
        warn("临时文件清理失败: {}".format(e), "Boot")
```

- 在 WiFi 连接完成后、`import main` 之前执行
- 此时 Logger 已可用（第9行已导入 `info`/`warn`）
- 外层 try-except 保护：清理失败不阻断系统启动

## 设计要点

- **调用时机**：启动阶段，无并发操作，安全删除
- **容错策略**：三层保护（单文件/函数级/调用方），失败仅记录日志
- **内存开销**：`os.listdir()` 返回文件名列表，data 目录文件 < 20 个，开销可忽略
- **函数归属**：放在 JsonlDB.py 中，因为临时文件由该模块的 update/delete 方法产生

## 验证方式

1. 在 `src/data/` 下手动创建测试临时文件（如 `test.jsonl.tmp`）
2. 重启系统，检查串口日志是否输出清理信息
3. 确认临时文件已被删除，正常 `.jsonl` 文件不受影响
