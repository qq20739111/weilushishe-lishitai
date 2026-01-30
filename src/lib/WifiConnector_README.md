# WifiConnector v1.3.0

ESP32 MicroPython WiFi连接管理类 - 增强版

## 版本概述

WifiConnector v1.3.0 是一个强大的WiFi连接管理库，专为ESP32 MicroPython环境设计。v1.3.0版本在v1.2.0的基础上进行了重大升级，新增了完整的静态IP配置管理功能，包括IP验证、动态切换DHCP/静态IP、便捷访问器等。

## 🆕 v1.3.0 新增功能

### 1. 完善的静态IP管理
- **configure_static_ip()**: 独立配置静态IP（可预设或动态配置）
- **clear_static_ip_config()**: 清除静态IP配置
- **connect_with_static_ip()**: 使用静态IP连接的便捷方法
- **IP地址验证**: 自动验证IP地址、子网掩码、网关格式
- **网关自动推断**: 根据IP地址自动推断默认网关

### 2. DHCP/静态IP动态切换
- **switch_to_static_ip()**: 在已连接状态下切换到静态IP
- **switch_to_dhcp()**: 从静态IP切换回DHCP模式
- **is_static_ip_enabled()**: 检查是否启用静态IP
- **is_dhcp_enabled()**: 检查是否使用DHCP
- **get_ip_mode()**: 获取当前IP模式（'static'或'dhcp'）

### 3. 静态IP便捷访问器
- **get_static_ip_config()**: 获取完整静态IP配置
- **get_configured_static_ip()**: 获取配置的静态IP
- **get_configured_gateway()**: 获取配置的网关
- **get_configured_dns()**: 获取配置的DNS
- **get_configured_subnet()**: 获取配置的子网掩码

### 4. 增强的配置持久化
- 静态IP配置自动保存和加载
- 支持备用DNS服务器配置

## 🔧 主要改进

### 网络信息管理
```python
# v1.0.0 - 每次都需要手动获取
config = wifi.sta.ifconfig()
ip = config[0]

# v1.1.0 - 智能缓存，自动同步
ip = wifi.get_ip_address()  # 从缓存获取，必要时自动更新
```

### 连接监控
```python
# v1.1.0 新功能 - 一键式监控
result = wifi.monitor_connection()
print(f"连接状态: {result['status']}")
print(f"是否重连: {result['reconnect_attempted']}")
```

### 配置持久化
```python
# v1.1.0 新功能 - 配置保存和加载
wifi.save_config('my_wifi.json', include_password=False)
wifi.load_config('my_wifi.json')
```

## 📋 功能特性

### 核心功能
- ✅ WiFi网络扫描和连接
- ✅ 自动重连机制
- ✅ 静态IP配置
- ✅ WiFi热点创建和管理
- ✅ 连接状态监测

### v1.1.0 增强功能
- 🆕 智能网络信息同步
- 🆕 连接监控和自动维护
- 🆕 配置文件持久化
- 🆕 高级诊断和状态报告
- 🆕 便捷的属性访问器
- 🆕 网络搜索功能

### v1.2.0 热点增强
- 🆕 完整的AP热点管理
- 🆕 热点IP配置和客户端管理
- 🆕 热点配置持久化

### v1.3.0 静态IP增强
- 🆕 完善的静态IP配置管理
- 🆕 DHCP/静态IP动态切换
- 🆕 IP地址格式验证
- 🆕 静态IP便捷访问器

### 可靠性特性
- 🔧 增强的错误处理
- 🔧 参数验证和类型检查
- 🔧 资源管理和清理
- 🔧 调试日志系统

## 🚀 快速开始

### 基本连接示例
```python
from WifiConnector import WifiConnector

# 创建WiFi连接器
wifi = WifiConnector(debug=True)

# 连接到WiFi
if wifi.connect("YourWiFi", "YourPassword"):
    print(f"连接成功! IP: {wifi.get_ip_address()}")
    
    # v1.1.0 新功能：监控连接
    result = wifi.monitor_connection()
    print(f"监控状态: {result['status']}")
    
else:
    print(f"连接失败: {wifi.get_last_error()}")

# 清理资源
wifi.cleanup()
```

### 配置持久化示例
```python
# 保存当前配置
wifi.save_config('wifi_settings.json', include_password=False)

# 下次启动时加载配置
wifi.load_config('wifi_settings.json')
if wifi.reconnect():
    print("使用保存的配置重连成功!")
```

### 连接监控示例
```python
# 在主循环中监控连接
while True:
    result = wifi.monitor_connection()
    
    if result['status'] == 'reconnected':
        print("检测到断线并已自动重连")
    elif result['status'] == 'disconnected':
        print("连接断开，重连失败")
    
    time.sleep(30)  # 每30秒检查一次
```

## 📚 API 文档

### 类初始化
```python
WifiConnector(debug=False)
```

### 网络扫描
```python
networks = wifi.scan_networks(timeout=10)
network = wifi.find_network("TargetSSID")  # v1.1.0新增
```

### 连接管理
```python
wifi.connect(ssid, password=None, timeout=15, static_ip=None)
wifi.disconnect(keep_credentials=True)  # v1.1.0改进
wifi.reconnect(max_attempts=3)
wifi.forget_network()  # v1.1.0改进
```

### 状态查询
```python
wifi.is_connected()
status = wifi.get_connection_status()  # v1.1.0增强
info = wifi.get_network_info()  # v1.1.0增强
```

### 便捷访问器 (v1.1.0新增)
```python
ip = wifi.get_ip_address()
mac = wifi.get_mac_address()
gateway = wifi.get_gateway_ip()
ssid = wifi.get_ssid()
```

### 连接监控 (v1.1.0新增)
```python
result = wifi.monitor_connection()
sync_status = wifi.get_sync_status()
wifi.refresh_network_info(force=True)
```

### 配置管理 (v1.1.0新增)
```python
wifi.set_timeouts(scan_timeout=15, connect_timeout=20)
wifi.set_sync_intervals(sync_interval=300, force_sync_interval=1800)
wifi.save_config(filename, include_password=False)
wifi.load_config(filename)
```

### 静态IP管理 (v1.3.0新增)
```python
# 方式1：预先配置静态IP，然后连接
wifi.configure_static_ip(
    ip='192.168.1.100',
    subnet='255.255.255.0',
    gateway='192.168.1.1',
    dns='8.8.8.8'
)
wifi.connect('MyWiFi', 'password')

# 方式2：使用便捷方法一步完成
wifi.connect_with_static_ip(
    'MyWiFi', 'password',
    ip='192.168.1.100',
    gateway='192.168.1.1'
)

# 方式3：已连接后动态切换到静态IP
wifi.connect('MyWiFi', 'password')
wifi.switch_to_static_ip('192.168.1.100', gateway='192.168.1.1')

# 切换回DHCP
wifi.switch_to_dhcp()

# 检查IP模式
print(wifi.get_ip_mode())           # 'static' 或 'dhcp'
print(wifi.is_static_ip_enabled())  # True/False

# 获取静态IP配置
config = wifi.get_static_ip_config()

# 便捷访问器
wifi.get_configured_static_ip()
wifi.get_configured_gateway()
wifi.get_configured_dns()
```

### 热点管理 (v1.2.0增强)
```python
# 创建热点（增强版）
wifi.create_hotspot(
    ssid="ESP32_AP",
    password="12345678",
    channel=6,
    max_clients=4,
    authmode=wifi.AP_AUTHMODE_WPA2_PSK,
    ip_config={'ip': '192.168.4.1', 'subnet': '255.255.255.0'}
)

# 配置热点IP
wifi.configure_hotspot_ip(ip='192.168.4.1', subnet='255.255.255.0')

# 检查热点状态
is_active = wifi.is_hotspot_active()

# 获取热点完整信息
info = wifi.get_hotspot_info()

# 获取已连接的客户端
clients = wifi.get_hotspot_clients()

# 便捷访问器
ssid = wifi.get_hotspot_ssid()
ip = wifi.get_hotspot_ip()
mac = wifi.get_hotspot_mac()

# 停止热点
wifi.stop_hotspot()
```

### 热点配置持久化 (v1.2.0新增)
```python
# 保存热点配置
wifi.save_hotspot_config('hotspot.json', include_password=False)

# 加载热点配置
wifi.load_hotspot_config('hotspot.json')

# 使用已加载的配置启动热点
wifi.start_hotspot_from_config()
```

### 诊断功能
```python
diag = wifi.get_diagnostics()  # v1.1.0增强
error = wifi.get_last_error()
```

### 资源管理
```python
wifi.cleanup()  # v1.1.0改进
```

## 🔧 配置参数

### 超时设置
- `scan_timeout`: 扫描超时（默认10秒）
- `connect_timeout`: 连接超时（默认15秒）

### 同步间隔 (v1.1.0新增)
- `sync_interval`: 常规同步间隔（默认300秒）
- `force_sync_interval`: 强制同步间隔（默认1800秒）

### 连接参数
- `max_retries`: 最大重试次数（默认3次）

## 📝 使用建议

### 最佳实践

1. **启用调试模式**: 开发时启用调试以获得详细日志
```python
wifi = WifiConnector(debug=True)
```

2. **使用连接监控**: 在主循环中定期监控连接状态
```python
# 每分钟监控一次
result = wifi.monitor_connection()
```

3. **配置持久化**: 保存WiFi配置以减少重复配置
```python
wifi.save_config('wifi_config.json')
```

4. **适当的超时设置**: 根据网络环境调整超时参数
```python
wifi.set_timeouts(scan_timeout=15, connect_timeout=25)
```

5. **资源清理**: 程序结束时清理资源
```python
try:
    # 主程序逻辑
    pass
finally:
    wifi.cleanup()
```

### 性能优化

1. **使用便捷访问器**: 利用缓存机制提高性能
```python
# 推荐：使用缓存的访问器
ip = wifi.get_ip_address()

# 避免：直接调用底层接口
# ip = wifi.sta.ifconfig()[0]
```

2. **合理的同步间隔**: 根据应用需求调整同步频率
```python
# 对于相对静态的环境
wifi.set_sync_intervals(sync_interval=600, force_sync_interval=3600)
```

## 🐛 故障排除

### 常见问题

1. **连接失败**
   - 检查SSID和密码是否正确
   - 确认网络在扫描范围内
   - 查看`wifi.get_last_error()`获取详细错误信息

2. **连接不稳定**
   - 启用连接监控功能
   - 检查信号强度
   - 调整重连参数

3. **IP地址获取失败**
   - 手动刷新网络信息：`wifi.refresh_network_info(force=True)`
   - 检查DHCP服务器状态

### 错误代码

- `STAT_WRONG_PASSWORD`: 密码错误
- `STAT_NO_AP_FOUND`: 未找到接入点
- `STAT_CONNECT_FAIL`: 连接失败
- `STAT_GOT_IP`: 已获取IP地址

## 📊 版本对比

| 功能 | v1.0.0 | v1.1.0 | v1.2.0 | v1.3.0 |
|------|--------|--------|--------|--------|
| 基本连接 | ✅ | ✅ | ✅ | ✅ |
| 网络扫描 | ✅ | ✅ + 搜索 | ✅ | ✅ |
| 自动重连 | ✅ | ✅ + 监控 | ✅ | ✅ |
| 热点创建 | ✅ | ✅ | 🆕 增强 | ✅ |
| 热点IP配置 | ❌ | ❌ | 🆕 支持 | ✅ |
| 热点客户端管理 | ❌ | ❌ | 🆕 支持 | ✅ |
| 静态IP | ✅ 基础 | ✅ | ✅ | 🆕 完整管理 |
| 静态IP配置方法 | ❌ | ❌ | ❌ | 🆕 支持 |
| DHCP/静态切换 | ❌ | ❌ | ❌ | 🆕 支持 |
| IP地址验证 | ❌ | ❌ | ❌ | 🆕 支持 |
| 网络信息 | 手动 | 🆕 自动 | ✅ | ✅ |
| 配置持久化 | ❌ | 🆕 支持 | ✅ | ✅ 增强 |
| 诊断功能 | 基础 | 🆕 高级 | ✅ | ✅ 增强 |

## 📄 许可证

本项目使用 MIT 许可证。

## 🤝 贡献

欢迎提交Issue和Pull Request来改进此项目。

## 📞 支持

如果您在使用过程中遇到问题，请查看：
1. 本README文档
2. 示例代码 (`wifi_connector_example.py`)
3. 源代码注释

---

**版本**: v1.3.0  
**适用平台**: ESP32 MicroPython  
**更新日期**: 2026年1月25日
