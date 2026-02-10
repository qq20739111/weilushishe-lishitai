# 围炉诗社·理事台 - 持久性运行稳定性分析报告

> 分析范围：全系统源码（boot.py、main.py、11个lib模块、数据层、Web框架）
> 分析目标：识别影响 ESP32 系统 7x24 长期运行的潜在风险，给出改进建议

---

## 一、系统架构总览

| 项目 | 说明 |
|------|------|
| 硬件 | ESP32-S2 WEMOS S2 mini (240MHz, 320KB SRAM, 2MB PSRAM, 2MB Flash) |
| 运行时 | MicroPython v1.25.0 |
| Web框架 | 自定义 microdot (244行, uasyncio) |
| 数据库 | JSONL 流式引擎 (JsonlDB) |
| 缓存 | CacheManager (TTL + FIFO + 低内存保护) |
| 看门狗 | 硬件 WDT (300秒超时, 30秒喂狗周期) |
| 网络 | WifiConnector (STA/AP双模, 自动故障转移) |

**启动流程**: `boot.py` -> 初始化WDT -> WiFi连接(5次重试) -> NTP时间同步 -> AP故障转移 -> LED状态指示 -> `main.py` 导入 -> 启动定时喂狗器 -> `app.run(port=80)` 阻塞运行

---

## 二、各维度稳定性评估

### 2.1 看门狗机制 — 评分: 9/10

**现状**：三层喂狗保护，设计优秀。

- `Watchdog.py`: 硬件 WDT 单例，超时 300 秒，一旦启用不可停止
- `boot.py`: 在 WiFi 连接循环中每次尝试前喂狗（L62, L87, L139, L166, L196）
- `main.py L55-63`: Timer(1) 每 30 秒周期喂狗，超时 300 秒 = 1/10 安全裕度
- `main.py L136`: 每次 API 请求处理时喂狗

**风险点**：
1. **喂狗失败静默处理**（Watchdog.py L90-91）: `except: pass` — 若硬件 WDT 出现异常，无任何日志可诊断
2. **看门狗触发重启无记录**: 重启后无法区分是正常重启还是看门狗超时重启，缺少重启原因持久化

**建议**：
- 喂狗失败时至少记录一次 error 日志（设置标志位避免刷屏）
- 在 boot.py 启动时检查 `machine.reset_cause()`，将重启原因写入日志文件，便于事后诊断

---

### 2.2 顶层异常处理 — 评分: 7/10

**现状**：存在关键保护缺口。

**boot.py 入口（L164-200）**：
```python
if __name__ == '__main__':
    connect_wifi()
    watchdog.feed()
    try:
        import main
        if hasattr(main, 'app'):
            # ... LED 设置 ...
            main.app.run(port=80)   # <-- 阻塞运行
    except Exception as e:
        error(f"启动主程序失败: {e}", "Boot")
        # 异常后 → 直接退出，系统进入空闲 → 等300秒看门狗重启
```

**main.py 入口（L2536-2551）**：
```python
if __name__ == '__main__':
    try:
        app.run(port=80, debug=log.is_debug)
    except KeyboardInterrupt:
        info("收到中断信号...", "System")
    except Exception as e:
        error(f"Web服务启动失败: {e}", "System")
    finally:
        stop_watchdog_timer()
        status_led.stop()
```

**问题**：
1. **boot.py 的 `app.run()` 异常后无恢复**：只记录日志，不主动重启。虽然看门狗最终会触发重启（300秒后），但期间系统完全不可用
2. **boot.py 调用路径不走 main.py 的 `__main__` 分支**：`import main` 后直接调用 `main.app.run()`，所以 main.py L2536-2551 的异常处理和 finally 清理逻辑**实际不会执行**
3. **`app.run()` 内部的 `asyncio.run(main())` 异常**：microdot.py L222-225 仅捕获 `KeyboardInterrupt`，其他异常会向上传播

**建议**：
- boot.py 的 `app.run()` 调用应包裹在循环重试或 `machine.reset()` 自动重启逻辑中
- 异常后主动调用 `machine.reset()` 而非被动等待看门狗超时

---

### 2.3 WiFi 稳定性 — 评分: 7/10

**现状**：启动阶段连接机制完善，但运行期间缺少主动监控。

**启动阶段**（boot.py L59-140）：
- 30 秒超时 + 5 次重试
- 致命错误检测（密码错误、AP 未找到）立即终止重试
- 自动切换 AP 热点模式
- NTP 时间同步（3 次重试，失败不阻塞）

**运行期间**：
- **无 WiFi 连接状态监控线程/定时器** — 这是最大的稳定性缺口
- WiFi 断开后，系统不会主动发现和重连，只有在用户发起 HTTP 请求时才会暴露问题
- 没有使用 `ticks_ms`/`ticks_diff` 做单调时间监控（全系统无使用）

**WifiConnector.py 能力**：
- 已有 `reconnect()` 方法（L423-435）支持重连
- 已有 `is_connected()` 方法检测连接状态
- 已有 `_reset_wifi_module()` 重置 WiFi 模块

**建议**：
- 添加 WiFi 心跳监控定时器（建议使用 Timer(2)，每 60 秒检测连接状态）
- 断线时触发自动重连，重连失败则切换 AP 模式
- 在 `api_route` 装饰器中增加连接状态快速检查

---

### 2.4 内存管理 — 评分: 8/10

**现状**：gc.collect() 调用充分（全系统 36 处），有低内存保护机制。

**保护机制**：
- `LOW_MEMORY_THRESHOLD = 51200`（50KB）: 低于此值触发 `cache.flush_all()` 紧急释放
- microdot.py: 请求读取前 gc.collect()（L49）、请求处理完释放 body/json（L193-195）、响应后再次 gc.collect()（L212）
- CacheManager: dict 类型支持 max_size FIFO 淘汰
- JsonlDB: 流式读取 + 偏移量分页，避免全量加载

**风险点**：
1. **偏移量列表内存压力**（JsonlDB.py L112-142）：`fetch_page()` 中 `offsets` 列表存储文件中所有行的位置。若 poems.jsonl 增长到数千条，offsets 列表可能消耗可观内存（1000 条 ~ 8KB，10000 条 ~ 80KB）
2. **`get_all()` 全量加载**（JsonlDB.py L271-282）：members 等小数据集使用 get_all()，目前 10 条无问题，但缺少数据量保护
3. **list 类型缓存无 max_size 限制**（CacheManager.py L36-37）：`chat:messages` 注册为 list 类型，虽然有 `_chat_cleanup()` 外部限制，但 CacheManager 本身不限制 list 增长
4. **PSRAM 未被利用/监控**：系统有 2MB PSRAM，但代码中未检查 PSRAM 可用量（`gc.mem_free()` 是否包含 PSRAM 取决于 MicroPython 编译选项）
5. **fetch_page() 和 get_all() 返回前未调用 gc.collect()**：大量 JSON 解析后可能产生内存碎片

**建议**：
- JsonlDB.fetch_page() 返回前增加 gc.collect()
- get_all() 添加可选的 limit 参数作为安全上限
- CacheManager 为 list 类型也实现 max_size 限制
- 在系统状态接口中增加 PSRAM 用量监控（`esp32.psram_heap_stat()` 如果可用）

---

### 2.5 数据持久化与增长 — 评分: 7/10

**当前数据规模**：

| 文件 | 大小 | 记录数 | 年增长预估 |
|------|------|--------|-----------|
| poems.jsonl | 110 KB | 219 | ~300 KB/年 |
| activities.jsonl | 22 KB | 8 | ~100 KB/年 |
| login_logs.jsonl | 6 KB | 47 | 有清理机制(保留7天) |
| members.jsonl | 3 KB | 10 | 微量 |
| finance.jsonl | 0.2 KB | 1 | ~10 KB/年 |
| 静态资源(HTML/CSS/JS) | ~390 KB | - | 基本不变 |
| **总 Flash 占用** | **~560 KB** | - | 2MB 中剩余 ~1.4 MB |

**风险点**：
1. **poems.jsonl 无限增长**：作为最大的数据文件，无归档/清理机制。按当前增速，~3-4年可能面临 Flash 空间压力
2. **config.json 无备份**（Settings.py L71-81）：直接覆写，若写入过程中断电，文件可能损坏，导致系统无法启动
3. **临时文件(.tmp)无定期清理**：JsonlDB update/delete 操作使用 `.tmp` 临时文件，若异常未被捕获，.tmp 文件永久残留
4. **原子替换的窗口期**：`os.remove(原文件)` 和 `os.rename(tmp, 原文件)` 之间（JsonlDB.py L225-226），若断电则数据丢失
5. **财务记录重写频率**：每次添加财务记录可能触发 balance_after 重算，需要完整重写文件

**建议**：
- config.json 保存前先写入 .bak 备份，启动时检测并恢复
- boot.py 启动时扫描并清理 data/ 下超过 1 小时的 .tmp 文件
- 考虑 poems.jsonl 的年度归档策略（当记录超过一定数量时提示管理员）
- Flash 使用率超过 80% 时在管理后台显示告警

---

### 2.6 时间依赖问题 — 评分: 6/10

**现状**：系统广泛使用 `time.time()` 作为时间基准，但 NTP 同步会导致时间跳变。

**受影响的模块**：
- **CacheManager.py**: TTL 过期检查基于 `time.time()` (L61, L79)
- **Auth.py**: Token 有效期基于 `time.time()` (L62, L92-93)
- **WifiConnector.py**: 连接超时计算基于 `time.time()` (L148, L160)
- **聊天室**: 游客过期时间基于 `time.time()` (main.py L2389, L2436)

**风险场景**：
1. NTP 同步成功后，RTC 被校准为北京时间（boot.py L42-46），`time.time()` 可能突然跳变数小时
2. 如果 NTP 同步发生在缓存 TTL 设置之后，所有已设置的 TTL 时间戳会失效（提前过期或延迟过期）
3. Token 有效期可能因时间跳变而缩短或延长

**实际影响评估**：
- 当前系统在 boot.py 中先同步 NTP 再启动 main.py，所以**正常启动流程中问题不大**
- 但如果运行期间发生二次 NTP 同步（目前代码未实现，但扩展时需注意），会影响所有时间相关逻辑

**建议**：
- 对于需要精确间隔的场景（如缓存 TTL），考虑使用 `time.ticks_ms()` 单调时间源替代 `time.time()`
- Token 有效期建议保持使用 `time.time()`（因为需要跨重启有效），但应在 NTP 同步后才开始签发 Token
- 在 Auth.verify_token() 中增加时间合理性检查（如过期时间不超过未来 365 天）

---

### 2.7 异常处理覆盖度 — 评分: 7/10

**统计**：main.py 中共 43 处 try-except，覆盖面广。

**问题模式 — 静默异常**：

以下位置使用 `except: pass` 或 `except Exception: pass`，异常被完全吞掉：

| 文件 | 行号 | 上下文 | 风险 |
|------|------|--------|------|
| main.py | L483 | 周统计计算 | 统计数据错误无法诊断 |
| main.py | L498 | 周统计计算 | 同上 |
| main.py | L1393, L1401, L1417, L1419 | 财务相关操作 | 财务数据错误不可见 |
| main.py | L1442 | 财务统计 | 同上 |
| main.py | L1473, L1529, L1533 | 数据导入/备份 | 数据丢失风险 |
| main.py | L1794, L1814 | 系统设置 | 配置错误难诊断 |
| main.py | L1924 | 系统信息 | 监控数据不准 |
| main.py | L2082, L2531 | 数据导入/缓存统计 | 难以诊断 |
| JsonlDB.py | L170-171 | 搜索中 JSON 解析 | 损坏记录无法发现 |
| Watchdog.py | L90-91 | 喂狗失败 | 看门狗故障不可见 |
| microdot.py | L82-83 | JSON 解析 | 请求体错误不可见 |

**建议**：
- 将关键路径的 `except: pass` 改为 `except Exception as e: debug(f"...: {e}", "模块")`
- 至少保证财务、数据导入、系统设置等关键操作有日志

---

### 2.8 Web 服务器 (microdot) — 评分: 8/10

**现状**：简洁有效，内存管理良好。

**优点**：
- 请求大小限制 600KB（L44），防止内存溢出
- 分块读取大请求（L50-74），4KB chunk size
- 仅对 <=16KB 的 JSON 自动解析（L78）
- 安全响应头注入（X-Content-Type-Options, X-Frame-Options）
- API 响应禁止缓存（Cache-Control: no-store）

**风险点**：
1. **无请求读取超时**：`reader.readline()` 和 `reader.read()` 无超时控制，慢速客户端可能长时间占用连接
2. **无并发连接限制**：uasyncio 允许多个连接同时处理，高并发时内存可能耗尽
3. **静态文件无缓存控制**：HTML/CSS/JS 没有 ETag 或版本号，更新后客户端可能使用旧版本
4. **`asyncio.sleep(3600)` 主循环**（L219-220）：1 小时心跳间隔，虽然不影响请求处理，但主循环内无法插入定期维护任务

**建议**：
- 考虑为 reader 操作添加超时（uasyncio 的 `wait_for` + timeout）
- 静态资源响应添加简单的缓存控制头（如 `Cache-Control: max-age=3600`）
- 将 `asyncio.sleep(3600)` 缩短为较小间隔（如 60 秒），并在循环中插入定期维护逻辑（WiFi 检查、内存监控等）

---

### 2.9 聊天室内存管理 — 评分: 8/10

**现状**：设计合理，有大小限制和清理机制。

**保护机制**：
- 消息缓存大小限制：默认 128KB（可配置）
- `_chat_cleanup()` FIFO 清理超限消息
- 单条消息最大 1024 字符
- 游客过期时间 1 小时
- 消息计数器 O(1) 跟踪用户消息数

**风险点**：
1. **`messages.pop(0)` 效率问题**（main.py L2245）：Python list 的 pop(0) 是 O(n) 操作，消息量大时清理可能较慢
2. **游客过期清理时机被动**：仅在 `_allocate_guest_name()` 时清理（L2282-2285），不发送消息时过期游客不会被清理
3. **聊天消息不持久化**：系统重启后所有聊天记录丢失（这可能是设计意图）

**建议**：
- 如果消息量增长到数百条时出现性能问题，考虑用 collections.deque 替代 list（若 MicroPython 支持）
- 在定期维护任务中清理过期游客

---

### 2.10 LED 与定时器管理 — 评分: 9/10

**现状**：设计良好，资源管理到位。

- BreathLED 使用正弦查找表优化 CPU
- 60 秒后自动关闭 LED 节省资源
- Timer(0) 用于 LED，Timer(1) 用于看门狗，互不冲突
- cleanup() 和 __del__() 双重资源清理保障

**风险点**：
- **Timer ID 硬编码分散**：LED 用 Timer(0)，看门狗用 Timer(1)，未来如需更多定时器可能冲突
- 建议：集中定义 Timer ID 常量

---

### 2.11 日志系统 — 评分: 5/10

**现状**：仅 print() 输出到 UART，无文件持久化。

- Logger.py 支持 DEBUG/INFO/WARN/ERROR 四级
- 生产模式 (debug_mode=false) 不输出 DEBUG
- 登录日志有 JSONL 持久化（login_logs.jsonl，保留 7 天）

**风险点**：
1. **系统事件无持久化**：WiFi 断连、看门狗重启、异常错误等关键事件断电后丢失
2. **配置加载失败无告警**（Logger.py L54-56）：debug_mode 加载失败时默认 false，不输出任何提示
3. **无结构化日志**：所有日志通过 print() 输出，无时间戳前缀（依赖终端显示）

**建议**：
- 添加简单的系统事件日志（events.jsonl），记录启动、重启原因、WiFi 状态变化、严重错误等关键事件
- 限制 events.jsonl 文件大小（如保留最近 50 条）
- Logger 配置加载失败时至少 print() 一条提示

---

### 2.12 配置安全性 — 评分: 6/10

**现状**：

- WiFi 密码明文存储在 config.json
- password_salt 明文存储
- Token 签名密钥每次重启随机生成（Auth.py L15-16）— 安全但重启后所有 Token 失效

**建议**：
- 这些在嵌入式场景中是常见做法，风险可控
- 重点关注 config.json 的备份和完整性保护

---

## 三、稳定性评分总表

| 维度 | 评分 | 主要风险 |
|------|------|---------|
| 看门狗机制 | 9/10 | 喂狗失败无日志，重启原因不可追溯 |
| 顶层异常处理 | 7/10 | boot.py 异常后无自动恢复，被动等待 WDT |
| WiFi 稳定性 | 7/10 | 运行期间无主动断线监控和自动重连 |
| 内存管理 | 8/10 | offsets 列表内存压力，PSRAM 未利用 |
| 数据持久化 | 7/10 | config.json 无备份，.tmp 无清理，数据无限增长 |
| 时间依赖 | 6/10 | NTP 跳变影响 TTL/Token，未使用单调时间 |
| 异常处理 | 7/10 | 15+ 处静默异常，关键操作错误不可见 |
| Web 服务器 | 8/10 | 无请求超时，无并发限制 |
| 聊天室 | 8/10 | pop(0) 效率，游客清理被动 |
| LED/定时器 | 9/10 | Timer ID 分散管理 |
| 日志系统 | 5/10 | 无持久化，关键事件断电丢失 |
| 配置安全 | 6/10 | 明文存储，无备份 |
| **综合评分** | **7.3/10** | **适合长期运行，核心保护到位** |

---

## 四、改进建议优先级排序

### P0 - 高优先级（显著提升稳定性）

1. **boot.py 顶层异常自动恢复**
   - 文件：`src/boot.py` L198 附近
   - `app.run()` 异常后调用 `machine.reset()` 自动重启，而非被动等待 300 秒 WDT
   
2. **WiFi 运行期断线监控**
   - 文件：`src/boot.py` 或 `src/main.py`
   - 添加 Timer(2) 定时器，每 60 秒检查 WiFi 连接状态
   - 断线时触发自动重连，连续失败则切换 AP

3. **config.json 备份与恢复**
   - 文件：`src/lib/Settings.py`
   - 保存前写 .bak，启动时检测主文件损坏则从 .bak 恢复

### P1 - 中优先级（提升可诊断性）

4. **启动时记录重启原因**
   - 文件：`src/boot.py`
   - 使用 `machine.reset_cause()` 记录到日志

5. **临时文件启动清理**
   - 文件：`src/boot.py` 或 `src/main.py`
   - 启动时扫描 data/*.tmp，清理超过 1 小时的残留文件

6. **关键路径静默异常改为日志**
   - 文件：`src/main.py` (约 15 处)
   - 将财务、数据导入、系统设置中的 `except: pass` 改为带日志的异常处理

7. **microdot 主循环插入定期维护**
   - 文件：`src/lib/microdot.py` L219-220
   - 缩短 sleep 间隔，回调执行 WiFi 检查、内存监控等

### P2 - 低优先级（长期优化）

8. **CacheManager TTL 使用单调时间**
   - 用 `time.ticks_ms()` 替代 `time.time()` 计算缓存过期

9. **JsonlDB.fetch_page() 返回前 gc.collect()**
   - 减少大量 JSON 解析后的内存碎片

10. **list 缓存 max_size 限制**
    - CacheManager 为 list 类型也实现容量保护

11. **系统事件日志持久化**
    - 创建 events.jsonl，记录关键系统事件

12. **Flash 使用率告警**
    - 在系统信息接口中增加 Flash 使用率告警阈值

13. **静态资源缓存控制**
    - 为 HTML/CSS/JS 响应添加 Cache-Control 或版本号

---

## 五、Flash 容量规划

```
当前使用:     ~560 KB (28%)
年增长预估:   ~400 KB (20%)
安全可用:     ~1.6 MB (80% of 2MB)
预计可持续:   ~2.5 年无需清理
```

建议在 Flash 使用率超过 70% 时提醒管理员进行数据归档。

---

## 六、结论

系统整体设计稳健，核心保护机制（看门狗三层防护、内存低水位保护、缓存 TTL/FIFO、数据原子操作）已就位，**适合 24/7 长期运行**。

**最需要关注的三个改进点**：
1. boot.py 异常后自动重启（避免 300 秒不可用窗口）
2. WiFi 运行期主动监控（避免断线后系统沉默不可达）
3. config.json 备份机制（避免配置损坏导致无法启动）

完成 P0 级改进后，系统稳定性评分预计可提升至 **8.5/10**，满足诗社日常运营的长期无人值守需求。
