import machine
import network
import time
import json
import ntptime
from lib.WifiConnector import WifiConnector
from lib.SystemStatus import status_led
from lib.Logger import log, debug, info, warn, error
from lib.Watchdog import watchdog

machine.freq(240_000_000)  # 设置为240 MHz
info(f"当前CPU频率: {machine.freq()/1_000_000} MHz", "Boot")

# 初始化看门狗
watchdog.init()

# 初始化全局 WifiConnector (debug参数与日志模块联动)
wifi = WifiConnector(debug=log.is_debug)

def load_config():
    """加载配置文件"""
    try:
        with open('data/config.json', 'r') as f:
            return json.load(f)
    except Exception as e:
        error(f"配置加载失败: {e}", "Boot")
        return None

NTP_MAX_RETRIES = 3  # NTP同步最大重试次数

def sync_ntp_time():
    """
    同步NTP网络时间并校准为北京时间(UTC+8)
    失败不阻塞启动流程
    """
    ntptime.host = 'ntp.aliyun.com'
    for attempt in range(NTP_MAX_RETRIES):
        try:
            ntptime.settime()  # 设置RTC为UTC时间
            # 校准为北京时间 (UTC+8)
            utc_secs = time.time()
            cst_secs = utc_secs + 8 * 3600
            tm = time.localtime(cst_secs)
            # RTC datetime格式: (年, 月, 日, 星期, 时, 分, 秒, 亚秒)
            machine.RTC().datetime((tm[0], tm[1], tm[2], tm[6], tm[3], tm[4], tm[5], 0))
            t = time.localtime()
            info(f"NTP时间同步成功: {t[0]:04d}-{t[1]:02d}-{t[2]:02d} {t[3]:02d}:{t[4]:02d}:{t[5]:02d}", "NTP")
            return True
        except Exception as e:
            if attempt < NTP_MAX_RETRIES - 1:
                debug(f"NTP同步失败({attempt+1}/{NTP_MAX_RETRIES}): {e}，重试中...", "NTP")
                time.sleep(1)
            else:
                warn(f"NTP时间同步失败，系统时间可能不准确: {e}", "NTP")
    return False

def connect_wifi():
    # Indicate connecting status
    status_led.start_connecting()
    watchdog.feed()  # 喂狗

    config = load_config()
    if not config:
        warn("配置文件未找到，跳过WiFi连接", "Boot")
        return

    ssid = config.get('wifi_ssid')
    password = config.get('wifi_password')

    if ssid == "YOUR_WIFI_SSID":
        info("WiFi未配置，启动AP模式...", "Boot")
        start_ap(config)
        return
    
    # Use WifiConnector to connect
    # Optimize: Set longer timeout and retry logic
    wifi.connect_timeout = 30  # Increase connection timeout to 30s
    wifi.max_retries = 5       # Increase max retries
    
    info(f"正在连接 {ssid} (超时: {wifi.connect_timeout}秒, 重试: {wifi.max_retries}次)...", "WiFi")
    
    connected = False
    for attempt in range(wifi.max_retries):
        watchdog.feed()  # 每次尝试前喂狗
        
        if attempt > 0:
            debug(f"重试连接 ({attempt+1}/{wifi.max_retries})...", "WiFi")
            time.sleep(1)

        if wifi.connect(ssid, password):
            info(f"WiFi已连接! IP: {wifi.get_ip_address()}", "WiFi")
            connected = True
            
            # 同步NTP网络时间
            sync_ntp_time()
            
            # 配置静态IP（如果启用）
            if config.get('sta_use_static_ip') and config.get('sta_ip'):
                try:
                    sta_ip = config.get('sta_ip')
                    sta_subnet = config.get('sta_subnet', '255.255.255.0')
                    sta_gateway = config.get('sta_gateway', sta_ip.rsplit('.', 1)[0] + '.1')
                    sta_dns = config.get('sta_dns', '8.8.8.8')
                    
                    wlan = network.WLAN(network.STA_IF)
                    wlan.ifconfig((sta_ip, sta_subnet, sta_gateway, sta_dns))
                    info(f"静态IP已配置: {sta_ip}", "WiFi")
                except Exception as e:
                    warn(f"静态IP配置失败: {e}", "WiFi")
            
            break
        else:
            debug(f"WiFi连接尝试 {attempt+1} 失败: {wifi.last_error}", "WiFi")
            
            # 检查是否为致命错误（密码错误或找不到AP），无需继续重试
            last_err = wifi.last_error or ''
            if '密码错误' in last_err or '未找到' in last_err:
                warn(f"致命错误: {wifi.last_error}，停止重试", "WiFi")
                break

    if not connected:
        warn("所有WiFi连接尝试均失败", "WiFi")
        info("切换到AP模式...", "WiFi")
        
        # 切换AP前，先停止STA接口，确保AP能正常启动
        try:
            wlan_sta = network.WLAN(network.STA_IF)
            if wlan_sta.active():
                wlan_sta.active(False)
                time.sleep(0.5)
                debug("STA接口已关闭", "WiFi")
        except Exception as e:
            debug(f"关闭STA失败: {e}", "WiFi")
        
        watchdog.feed()  # 切换AP前再喂一次狗
        start_ap(config)

def start_ap(config):
    watchdog.feed()  # 喂狗

    ap_ssid = config.get('ap_ssid', 'PoetrySociety_AP')
    ap_password = config.get('ap_password', 'admin1234')
    ap_ip = config.get('ap_ip', '192.168.1.68')
    
    # Custom IP configuration for AP (从配置读取)
    ap_ip_config = {
        'ip': ap_ip,
        'subnet': '255.255.255.0',
        'gateway': ap_ip,
        'dns': '8.8.8.8'
    }

    info(f"正在启动热点: {ap_ssid} IP: {ap_ip_config['ip']}...", "AP")
    if wifi.create_hotspot(ap_ssid, ap_password, ip_config=ap_ip_config):
        hotspot_info = wifi.get_hotspot_info()
        info(f"热点启动成功! IP: {hotspot_info.get('ip_address')}", "AP")
    else:
        error(f"热点启动失败: {wifi.last_error}", "AP")

if __name__ == '__main__':
    connect_wifi()
    watchdog.feed()  # WiFi连接后喂狗
    
    try:
        info("正在启动主应用程序...", "Boot")
        import main
        # Manually trigger the start if main.py didn't run automatically (which happens on import)
        if hasattr(main, 'app'):
            # 检测最终网络状态，设置对应的LED指示
            sta = network.WLAN(network.STA_IF)
            ap = network.WLAN(network.AP_IF)
            sta_connected = sta.active() and sta.isconnected()
            ap_active = ap.active()
            
            debug(f"网络状态: STA连接={sta_connected}, AP激活={ap_active}", "Boot")
            
            # 根据网络模式设置LED状态
            if sta_connected and ap_active:
                # AP+WiFi双模式
                status_led.start_dual_mode()
            elif sta_connected:
                # 仅WiFi模式
                status_led.start_running()
            elif ap_active:
                # 仅AP模式
                status_led.start_ap_mode()
            else:
                # 无网络（异常情况）
                debug("警告: 无网络连接", "Boot")
            
            main.print_system_status()
            watchdog.feed()  # 启动Web服务前喂狗
            main.start_watchdog_timer()  # 启动定时喂狗器
            main.app.run(port=80)
    except Exception as e:
        error(f"启动主程序失败: {e}", "Boot")
