
"""
WiFi连接器使用示例程序 v1.3.0

此程序演示了WifiConnector v1.3.0类的主要功能：
1. WiFi网络扫描和搜索
2. WiFi连接和状态管理
3. 自动重连和连接监控
4. 静态IP配置和管理（v1.3.0新增）
5. DHCP/静态IP动态切换（v1.3.0新增）
6. WiFi热点创建和管理（v1.2.0增强）
7. 热点IP配置和客户端管理（v1.2.0新增）
8. 热点配置持久化（v1.2.0新增）
9. 配置保存和加载（持久化）
10. 网络信息同步和刷新
11. 高级诊断和监控功能

适用于ESP32 MicroPython环境
版本特性：v1.3.0增强了静态IP配置管理功能，支持DHCP/静态IP动态切换
"""

from WifiConnector import WifiConnector
import time

def print_separator(title=""):
    """打印分隔线"""
    line = "=" * 50
    if title:
        print(f"\n{line}")
        print(f"  {title}")
        print(line)
    else:
        print(line)

def test_network_scan(wifi):
    """测试网络扫描功能"""
    print_separator("WiFi网络扫描测试")
    
    print("开始扫描WiFi网络...")
    networks = wifi.scan_networks()
    
    if networks:
        print(f"发现 {len(networks)} 个网络:")
        for i, network in enumerate(networks[:5], 1):  # 只显示前5个
            print(f"{i}. SSID: {network['ssid']}")
            print(f"   信号强度: {network['rssi']}dBm ({network['signal_strength']})")
            print(f"   认证模式: {network['auth_name']}")
            print(f"   信道: {network['channel']}")
            print(f"   BSSID: {network['bssid']}")
            print()
    else:
        print("未发现任何网络")
        if wifi.get_last_error():
            print(f"错误: {wifi.get_last_error()}")

def test_network_search(wifi, target_ssid):
    """测试网络搜索功能 (v1.1.0新功能)"""
    print_separator("网络搜索测试")
    
    print(f"搜索指定网络: {target_ssid}")
    network = wifi.find_network(target_ssid)
    
    if network:
        print("找到目标网络:")
        print(f"  SSID: {network['ssid']}")
        print(f"  信号强度: {network['rssi']}dBm ({network['signal_strength']})")
        print(f"  认证模式: {network['auth_name']}")
        print(f"  信道: {network['channel']}")
    else:
        print("未找到目标网络")

def test_wifi_connection(wifi, ssid, password=None):
    """测试WiFi连接功能"""
    print_separator("WiFi连接测试")
    
    print(f"尝试连接到: {ssid}")
    
    # 连接到WiFi
    success = wifi.connect(ssid, password)
    
    if success:
        print("连接成功!")
        
        # 获取连接状态信息 (v1.1.0改进)
        status = wifi.get_connection_status()
        print("连接状态:")
        for key, value in status.items():
            if value is not None:
                print(f"  {key}: {value}")
        
        # 获取详细网络信息 (v1.1.0增强)
        info = wifi.get_network_info()
        if info.get('connected'):
            print("\n详细网络信息:")
            print(f"  IP地址: {info.get('ip_address')}")
            print(f"  子网掩码: {info.get('subnet_mask')}")
            print(f"  网关: {info.get('gateway_ip')}")
            print(f"  DNS: {info.get('dns_server')}")
            print(f"  MAC地址: {info.get('mac_address')}")
            
            if 'signal_quality' in info:
                print(f"  信号质量: {info['signal_quality']}")
        
        # 测试便捷访问器 (v1.1.0新增)
        print("\n便捷访问器测试:")
        print(f"  IP地址: {wifi.get_ip_address()}")
        print(f"  MAC地址: {wifi.get_mac_address()}")
        print(f"  网关IP: {wifi.get_gateway_ip()}")
        print(f"  当前SSID: {wifi.get_ssid()}")
        
    else:
        print("连接失败!")
        if wifi.get_last_error():
            print(f"错误: {wifi.get_last_error()}")

def test_static_ip_connection(wifi, ssid, password, static_config):
    """测试静态IP连接（v1.3.0增强）"""
    print_separator("静态IP连接测试 (v1.3.0增强)")
    
    print(f"尝试使用静态IP连接到: {ssid}")
    print(f"静态IP配置: {static_config}")
    
    success = wifi.connect(ssid, password, static_ip=static_config)
    
    if success:
        print("静态IP连接成功!")
        info = wifi.get_network_info()
        if info.get('connected'):
            print(f"当前IP: {info.get('ip_address')}")
            print(f"网关: {info.get('gateway_ip')}")
            print(f"IP模式: {wifi.get_ip_mode()}")
            print(f"静态IP启用: {wifi.is_static_ip_enabled()}")
    else:
        print("静态IP连接失败!")
        if wifi.get_last_error():
            print(f"错误: {wifi.get_last_error()}")

def test_static_ip_management(wifi, ssid, password):
    """测试静态IP管理功能 (v1.3.0新功能)"""
    print_separator("静态IP管理测试 (v1.3.0新功能)")
    
    # 测试IP地址验证
    print("1. 测试IP地址验证...")
    test_ips = ['192.168.1.100', '256.1.1.1', 'invalid', '10.0.0.50']
    for ip in test_ips:
        valid = wifi._validate_ip_address(ip)
        print(f"   {ip}: {'有效' if valid else '无效'}")
    
    # 测试预配置静态IP
    print("\n2. 测试预配置静态IP...")
    success = wifi.configure_static_ip(
        ip='192.168.1.150',
        subnet='255.255.255.0',
        gateway='192.168.1.1',
        dns='8.8.8.8'
    )
    if success:
        print("静态IP预配置成功")
        config = wifi.get_static_ip_config()
        print(f"配置详情: {config}")
    
    # 测试便捷访问器
    print("\n3. 测试静态IP便捷访问器...")
    print(f"   配置的IP: {wifi.get_configured_static_ip()}")
    print(f"   配置的网关: {wifi.get_configured_gateway()}")
    print(f"   配置的DNS: {wifi.get_configured_dns()}")
    print(f"   配置的子网: {wifi.get_configured_subnet()}")
    
    # 测试IP模式查询
    print("\n4. 测试IP模式查询...")
    print(f"   IP模式: {wifi.get_ip_mode()}")
    print(f"   静态IP启用: {wifi.is_static_ip_enabled()}")
    print(f"   DHCP启用: {wifi.is_dhcp_enabled()}")
    
    # 清除静态IP配置
    print("\n5. 清除静态IP配置...")
    wifi.clear_static_ip_config()
    print(f"   清除后IP模式: {wifi.get_ip_mode()}")

def test_static_ip_switch(wifi, ssid, password):
    """测试DHCP/静态IP动态切换 (v1.3.0新功能)"""
    print_separator("DHCP/静态IP动态切换测试 (v1.3.0新功能)")
    
    # 首先使用DHCP连接
    print("1. 使用DHCP连接...")
    if not wifi.is_connected():
        if not wifi.connect(ssid, password):
            print("DHCP连接失败，跳过切换测试")
            return
    
    print(f"   当前IP: {wifi.get_ip_address()}")
    print(f"   IP模式: {wifi.get_ip_mode()}")
    
    # 切换到静态IP
    print("\n2. 切换到静态IP...")
    success = wifi.switch_to_static_ip(
        ip='192.168.1.200',
        gateway='192.168.1.1'
    )
    if success:
        print("切换成功!")
        print(f"   新IP: {wifi.get_ip_address()}")
        print(f"   IP模式: {wifi.get_ip_mode()}")
    else:
        print("切换失败!")
        if wifi.get_last_error():
            print(f"   错误: {wifi.get_last_error()}")
    
    time.sleep(2)
    
    # 切换回DHCP
    print("\n3. 切换回DHCP...")
    success = wifi.switch_to_dhcp()
    if success:
        print("切换成功!")
        print(f"   新IP: {wifi.get_ip_address()}")
        print(f"   IP模式: {wifi.get_ip_mode()}")
    else:
        print("切换失败!")

def test_connect_with_static_ip(wifi, ssid, password):
    """测试使用静态IP连接的便捷方法 (v1.3.0新功能)"""
    print_separator("便捷静态IP连接测试 (v1.3.0新功能)")
    
    # 断开现有连接
    if wifi.is_connected():
        wifi.disconnect()
        time.sleep(1)
    
    print("使用connect_with_static_ip()方法连接...")
    success = wifi.connect_with_static_ip(
        ssid=ssid,
        password=password,
        ip='192.168.1.180',
        gateway='192.168.1.1',
        dns='8.8.8.8'
    )
    
    if success:
        print("连接成功!")
        print(f"  IP: {wifi.get_ip_address()}")
        print(f"  IP模式: {wifi.get_ip_mode()}")
        print(f"  静态IP配置: {wifi.get_static_ip_config()}")
    else:
        print("连接失败!")
        if wifi.get_last_error():
            print(f"  错误: {wifi.get_last_error()}")

def test_reconnection(wifi):
    """测试重连功能 (v1.1.0改进)"""
    print_separator("重连功能测试")
    
    if not wifi.get_ssid():
        print("没有之前的连接记录，跳过重连测试")
        return
    
    print("断开当前连接...")
    wifi.disconnect()
    time.sleep(2)
    
    print(f"连接状态: {'已连接' if wifi.is_connected() else '未连接'}")
    
    print("开始重连...")
    success = wifi.reconnect(max_attempts=2)
    
    if success:
        print("重连成功!")
        print(f"IP地址: {wifi.get_ip_address()}")
    else:
        print("重连失败!")
        if wifi.get_last_error():
            print(f"错误: {wifi.get_last_error()}")

def test_connection_monitoring(wifi):
    """测试连接监控功能 (v1.1.0新功能)"""
    print_separator("连接监控测试")
    
    print("模拟连接监控循环...")
    for i in range(5):
        print(f"监控周期 {i+1}/5:")
        
        # 执行连接监控
        result = wifi.monitor_connection()
        print(f"  连接状态: {'已连接' if result['connected'] else '未连接'}")
        print(f"  执行了同步: {result['sync_performed']}")
        print(f"  尝试了重连: {result['reconnect_attempted']}")
        print(f"  状态: {result['status']}")
        
        # 获取同步状态 (v1.1.0新功能)
        sync_status = wifi.get_sync_status()
        print(f"  上次同步: {sync_status['last_sync_ago']:.1f}秒前")
        print(f"  下次检查: {sync_status['next_check_in']:.1f}秒后")
        
        time.sleep(2)

def test_network_info_refresh(wifi):
    """测试网络信息刷新功能 (v1.1.0新功能)"""
    print_separator("网络信息刷新测试")
    
    if not wifi.is_connected():
        print("未连接，跳过刷新测试")
        return
    
    print("获取当前网络信息...")
    info_before = wifi.get_network_info()
    print(f"刷新前IP: {info_before.get('ip_address')}")
    
    print("手动刷新网络信息...")
    success = wifi.refresh_network_info(force=True)
    
    if success:
        print("刷新成功")
        info_after = wifi.get_network_info()
        print(f"刷新后IP: {info_after.get('ip_address')}")
    else:
        print("刷新失败")

def test_hotspot_creation(wifi):
    """测试热点创建功能 (v1.2.0增强)"""
    print_separator("WiFi热点测试 (v1.2.0增强)")
    
    hotspot_ssid = "ESP32_Hotspot_v1.2"
    hotspot_password = "12345678"  # 至少8位
    
    print(f"创建热点: {hotspot_ssid}")
    
    # 创建加密热点（v1.2.0增强：支持自定义IP和认证模式）
    ip_config = {
        'ip': '192.168.4.1',
        'subnet': '255.255.255.0',
        'gateway': '192.168.4.1',
        'dns': '192.168.4.1'
    }
    
    success = wifi.create_hotspot(
        ssid=hotspot_ssid, 
        password=hotspot_password, 
        channel=6, 
        max_clients=4,
        authmode=wifi.AP_AUTHMODE_WPA2_PSK,
        ip_config=ip_config
    )
    
    if success:
        print("热点创建成功!")
        
        # 获取热点完整信息 (v1.2.0增强)
        hotspot_info = wifi.get_hotspot_info()
        if hotspot_info.get('active'):
            print("\n热点详细信息:")
            print(f"  SSID: {hotspot_info.get('ssid')}")
            print(f"  IP地址: {hotspot_info.get('ip_address')}")
            print(f"  子网掩码: {hotspot_info.get('subnet_mask')}")
            print(f"  网关: {hotspot_info.get('gateway_ip')}")
            print(f"  信道: {hotspot_info.get('channel')}")
            print(f"  认证模式: {hotspot_info.get('authmode_name')}")
            print(f"  MAC地址: {hotspot_info.get('mac_address')}")
            print(f"  最大客户端数: {hotspot_info.get('max_clients')}")
            print(f"  当前客户端数: {hotspot_info.get('client_count')}")
        
        # 测试便捷访问器 (v1.2.0新增)
        print("\n便捷访问器测试:")
        print(f"  热点SSID: {wifi.get_hotspot_ssid()}")
        print(f"  热点IP: {wifi.get_hotspot_ip()}")
        print(f"  热点MAC: {wifi.get_hotspot_mac()}")
        print(f"  热点激活状态: {wifi.is_hotspot_active()}")
        
        # 等待一段时间
        print("\n等待5秒，检查热点状态...")
        time.sleep(5)
        
        # 获取已连接的客户端 (v1.2.0新增)
        clients = wifi.get_hotspot_clients()
        print(f"当前连接的客户端: {len(clients)} 个")
        for client in clients:
            print(f"  - MAC: {client.get('mac')}")
        
        # 停止热点
        print("\n停止热点...")
        wifi.stop_hotspot()
        print("热点已停止")
        
    else:
        print("热点创建失败!")
        if wifi.get_last_error():
            print(f"错误: {wifi.get_last_error()}")

def test_hotspot_ip_config(wifi):
    """测试热点IP配置功能 (v1.2.0新功能)"""
    print_separator("热点IP配置测试 (v1.2.0新功能)")
    
    print("配置自定义热点IP...")
    
    # 配置热点IP
    success = wifi.configure_hotspot_ip(
        ip='192.168.10.1',
        subnet='255.255.255.0',
        gateway='192.168.10.1',
        dns='192.168.10.1'
    )
    
    if success:
        print("热点IP配置成功")
        
        # 创建热点来验证配置
        print("\n使用自定义IP创建热点...")
        if wifi.create_hotspot("ESP32_CustomIP", "12345678", channel=1):
            info = wifi.get_hotspot_info()
            print(f"热点IP: {info.get('ip_address')}")
            print(f"子网掩码: {info.get('subnet_mask')}")
            print(f"网关: {info.get('gateway_ip')}")
            
            time.sleep(2)
            wifi.stop_hotspot()
            print("热点已停止")
    else:
        print("热点IP配置失败")
        if wifi.get_last_error():
            print(f"错误: {wifi.get_last_error()}")

def test_hotspot_config_persistence(wifi):
    """测试热点配置持久化功能 (v1.2.0新功能)"""
    print_separator("热点配置持久化测试 (v1.2.0新功能)")
    
    # 先创建一个热点
    print("创建热点以生成配置...")
    wifi.create_hotspot(
        ssid="ESP32_SavedAP",
        password="test12345678",
        channel=8,
        max_clients=5,
        ip_config={'ip': '192.168.5.1', 'subnet': '255.255.255.0'}
    )
    
    # 保存热点配置
    print("\n保存热点配置到文件...")
    success = wifi.save_hotspot_config('test_hotspot_config.json', include_password=False)
    
    if success:
        print("热点配置保存成功")
        
        # 停止热点
        wifi.stop_hotspot()
        print("热点已停止")
        
        # 加载配置
        print("\n从文件加载热点配置...")
        if wifi.load_hotspot_config('test_hotspot_config.json'):
            print("热点配置加载成功")
            
            # 使用加载的配置启动热点
            print("\n使用加载的配置启动热点...")
            if wifi.start_hotspot_from_config():
                print("热点从配置启动成功!")
                info = wifi.get_hotspot_info()
                print(f"  SSID: {info.get('ssid')}")
                print(f"  IP: {info.get('ip_address')}")
                print(f"  信道: {info.get('channel')}")
                
                time.sleep(2)
                wifi.stop_hotspot()
                print("热点已停止")
            else:
                print("热点启动失败")
        else:
            print("热点配置加载失败")
    else:
        print("热点配置保存失败")
        if wifi.get_last_error():
            print(f"错误: {wifi.get_last_error()}")

def test_config_persistence(wifi):
    """测试配置持久化功能 (v1.1.0新功能)"""
    print_separator("配置持久化测试")
    
    # 设置一些配置参数
    print("设置配置参数...")
    wifi.set_timeouts(scan_timeout=15, connect_timeout=20)
    wifi.set_sync_intervals(sync_interval=120, force_sync_interval=600)
    
    # 保存配置（不包含密码）
    print("保存配置到文件...")
    success = wifi.save_config('test_wifi_config.json', include_password=False)
    
    if success:
        print("配置保存成功")
        
        # 重置一些参数来测试加载
        wifi.set_timeouts(scan_timeout=10, connect_timeout=15)
        
        # 加载配置
        print("从文件加载配置...")
        load_success = wifi.load_config('test_wifi_config.json')
        
        if load_success:
            print("配置加载成功")
            print(f"扫描超时: {wifi.scan_timeout}秒")
            print(f"连接超时: {wifi.connect_timeout}秒")
            print(f"同步间隔: {wifi.sync_interval}秒")
        else:
            print("配置加载失败")
            if wifi.get_last_error():
                print(f"错误: {wifi.get_last_error()}")
    else:
        print("配置保存失败")
        if wifi.get_last_error():
            print(f"错误: {wifi.get_last_error()}")

def test_forget_network(wifi):
    """测试忘记网络功能 (v1.1.0改进)"""
    print_separator("忘记网络测试")
    
    print("当前网络信息:")
    print(f"  SSID: {wifi.get_ssid()}")
    print(f"  连接状态: {'已连接' if wifi.is_connected() else '未连接'}")
    
    print("忘记当前网络...")
    success = wifi.forget_network()
    
    if success:
        print("网络已忘记")
        print(f"  SSID: {wifi.get_ssid()}")
        print(f"  连接状态: {'已连接' if wifi.is_connected() else '未连接'}")
    else:
        print("忘记网络失败")
        if wifi.get_last_error():
            print(f"错误: {wifi.get_last_error()}")

def test_advanced_diagnostics(wifi):
    """测试高级诊断功能 (v1.1.0增强)"""
    print_separator("高级诊断测试")
    
    print("获取完整诊断信息...")
    diag = wifi.get_diagnostics()
    
    print("系统诊断:")
    for key, value in diag.items():
        if isinstance(value, dict):
            print(f"  {key}:")
            for sub_key, sub_value in value.items():
                print(f"    {sub_key}: {sub_value}")
        else:
            print(f"  {key}: {value}")
    
    print("\n连接状态:")
    status = wifi.get_connection_status()
    for key, value in status.items():
        print(f"  {key}: {value}")
    
    print("\n同步状态:")
    sync_status = wifi.get_sync_status()
    for key, value in sync_status.items():
        print(f"  {key}: {value}")

def format_mac_address(mac_hex):
    """格式化MAC地址，添加冒号分隔符"""
    if not mac_hex or len(mac_hex) != 12:
        return mac_hex
    return ':'.join(mac_hex[i:i+2] for i in range(0, 12, 2))

def test_config_save_load(wifi):
    """测试配置保存和加载"""
    print_separator("配置保存/加载测试")
    
    # 保存配置（不包含密码）
    print("保存配置到文件...")
    success = wifi.save_config('test_config.json', save_password=False)
    
    if success:
        print("配置保存成功")
    else:
        print("配置保存失败")
        if wifi.get_last_error():
            print(f"错误: {wifi.get_last_error()}")
        return
    
    # 清除当前凭据
    print("清除当前凭据...")
    wifi.forget_credentials()
    
    # 加载配置
    print("从文件加载配置...")
    success = wifi.load_config('test_config.json')
    
    if success:
        print("配置加载成功")
        status = wifi.get_status()
        print(f"加载的SSID: {status['ssid']}")
        print(f"是否有保存的密码: {status['has_saved_password']}")
    else:
        print("配置加载失败")
        if wifi.get_last_error():
            print(f"错误: {wifi.get_last_error()}")

def test_diagnostics(wifi):
    """测试诊断功能"""
    print_separator("系统诊断测试")
    
    print("获取诊断信息...")
    diag = wifi.get_diagnostics()
    
    print("诊断信息:")
    for key, value in diag.items():
        print(f"  {key}: {value}")
    
    print("\n状态信息:")
    status = wifi.get_status()
    for key, value in status.items():
        print(f"  {key}: {value}")

def main():
    """主程序"""
    print_separator("WiFiConnector v1.3.0 使用示例程序")
    print("此程序将演示WiFiConnector v1.3.0类的新功能和改进")
    print("请根据您的实际网络环境修改以下配置:")
    print()
    
    # 配置您的WiFi信息
    WIFI_SSID = "YourWiFiName"        # 请修改为您的WiFi名称
    WIFI_PASSWORD = "YourPassword"     # 请修改为您的WiFi密码
    
    print(f"目标WiFi: {WIFI_SSID}")
    print("注意: 请确保上述WiFi信息正确")
    
    # 创建WiFi连接器实例（启用调试模式）
    wifi = WifiConnector(debug=True)
    
    try:
        # 1. 测试网络扫描
        test_network_scan(wifi)
        
        # 2. 测试网络搜索 (v1.1.0新功能)
        test_network_search(wifi, WIFI_SSID)
        
        # 3. 测试WiFi连接
        test_wifi_connection(wifi, WIFI_SSID, WIFI_PASSWORD)
        
        # 如果连接成功，继续其他测试
        if wifi.is_connected():
            
            # 4. 测试网络信息刷新 (v1.1.0新功能)
            test_network_info_refresh(wifi)
            
            # 5. 测试连接监控 (v1.1.0新功能)
            test_connection_monitoring(wifi)
            
            # 6. 测试重连功能 (v1.1.0改进)
            test_reconnection(wifi)
            
            # 7. 测试静态IP管理 (v1.3.0新功能)
            test_static_ip_management(wifi, WIFI_SSID, WIFI_PASSWORD)
            
            # 8. 测试DHCP/静态IP切换 (v1.3.0新功能)
            # 注意：此测试会修改IP地址，请根据网络环境调整
            # test_static_ip_switch(wifi, WIFI_SSID, WIFI_PASSWORD)
            
            # 9. 测试便捷静态IP连接 (v1.3.0新功能)
            # test_connect_with_static_ip(wifi, WIFI_SSID, WIFI_PASSWORD)
            
            # 10. 测试配置持久化 (v1.1.0新功能)
            test_config_persistence(wifi)
            
            # 11. 测试忘记网络 (v1.1.0改进)
            test_forget_network(wifi)
        
        # 12. 测试热点创建 (v1.2.0增强)
        test_hotspot_creation(wifi)
        
        # 13. 测试热点IP配置 (v1.2.0新功能)
        test_hotspot_ip_config(wifi)
        
        # 14. 测试热点配置持久化 (v1.2.0新功能)
        test_hotspot_config_persistence(wifi)
        
        # 15. 测试高级诊断功能 (v1.1.0增强)
        test_advanced_diagnostics(wifi)
        
    except KeyboardInterrupt:
        print("\n程序被用户中断")
    except Exception as e:
        print(f"\n程序异常: {e}")
    finally:
        # 清理资源
        print_separator("程序结束清理")
        
        # 断开连接
        if wifi.is_connected():
            print("断开WiFi连接...")
            wifi.disconnect()
        
        # 停止热点
        print("确保热点已停止...")
        wifi.stop_hotspot()
        
        # 清理资源 (v1.1.0改进)
        print("清理WiFi资源...")
        wifi.cleanup()
        
        print("清理完成")

def quick_connection_demo():
    """快速连接演示 (展示v1.1.0新特性)"""
    print_separator("v1.1.0 快速连接演示")
    
    # 请修改为您的WiFi信息
    SSID = "YourWiFiName"
    PASSWORD = "YourPassword"
    
    print(f"连接到: {SSID}")
    
    wifi = WifiConnector(debug=True)
    
    # 设置连接参数 (v1.1.0新功能)
    wifi.set_timeouts(scan_timeout=12, connect_timeout=18)
    wifi.set_sync_intervals(sync_interval=180, force_sync_interval=900)
    
    if wifi.connect(SSID, PASSWORD):
        print("连接成功!")
        
        # 显示网络信息 (v1.1.0增强)
        info = wifi.get_network_info()
        print(f"IP地址: {info.get('ip_address', 'Unknown')}")
        print(f"MAC地址: {wifi.get_mac_address()}")
        
        # 保存配置 (v1.1.0新功能)
        wifi.save_config('quick_demo_config.json')
        
        # 监控连接几次 (v1.1.0新功能)
        print("监控连接状态...")
        for i in range(3):
            result = wifi.monitor_connection()
            print(f"监控 {i+1}: {result['status']}")
            time.sleep(2)
        
        # 手动刷新网络信息 (v1.1.0新功能)
        wifi.refresh_network_info(force=True)
        
        wifi.disconnect()
        print("已断开连接")
    else:
        print("连接失败!")
        error = wifi.get_last_error()
        if error:
            print(f"错误: {error}")
    
    # 清理资源
    wifi.cleanup()

def simple_connection_test():
    """简单的连接测试（用于快速验证）"""
    print_separator("简单连接测试")
    
    # 请修改为您的WiFi信息
    SSID = "YourWiFiName"
    PASSWORD = "YourPassword"
    
    print(f"连接到: {SSID}")
    
    wifi = WifiConnector(debug=True)
    
    if wifi.connect(SSID, PASSWORD):
        print("连接成功!")
        info = wifi.get_network_info()
        print(f"IP地址: {info.get('ip_address', 'Unknown')}")
        
        # 保持连接几秒钟
        print("保持连接5秒...")
        time.sleep(5)
        
        wifi.disconnect()
        print("已断开连接")
    else:
        print("连接失败!")
        error = wifi.get_last_error()
        if error:
            print(f"错误: {error}")

if __name__ == "__main__":
    # 运行完整的测试程序
    main()
    
    # 或者运行快速演示
    # quick_connection_demo()
    
    # 或者运行简单的连接测试
    # simple_connection_test()
