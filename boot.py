import machine
import network
import time
import json
from lib.WifiConnector import WifiConnector
from lib.SystemStatus import status_led

machine.freq(240_000_000)  # 设置为240 MHz
print(f"当前CPU频率: {machine.freq()/1_000_000} MHz")

# Initialize global WifiConnector
wifi = WifiConnector(debug=True)

def load_config():
    try:
        with open('data/config.json', 'r') as f:
            return json.load(f)
    except Exception as e:
        print("Error loading config:", e)
        return None

def connect_wifi():
    # Indicate connecting status
    status_led.start_connecting()

    config = load_config()
    if not config:
        print("Config not found, skipping WiFi connection.")
        return

    ssid = config.get('wifi_ssid')
    password = config.get('wifi_password')

    if ssid == "YOUR_WIFI_SSID":
        print("WiFi not configured. Starting in AP mode...")
        start_ap(config)
        return
    
    # Use WifiConnector to connect
    # Optimize: Set longer timeout and retry logic
    wifi.connect_timeout = 30  # Increase connection timeout to 30s
    wifi.max_retries = 5       # Increase max retries
    
    print(f"Connecting to {ssid} (Timeout: {wifi.connect_timeout}s, Retries: {wifi.max_retries})...")
    
    connected = False
    for attempt in range(wifi.max_retries):
        if attempt > 0:
            print(f"Retrying connection ({attempt+1}/{wifi.max_retries})...")
            # Rapid toggle to show activity if desired, or just wait
            time.sleep(1)

        if wifi.connect(ssid, password):
            print(f"WiFi Connected! IP: {wifi.get_ip_address()}")
            connected = True
            break
        else:
            print(f"WiFi connection attempt {attempt+1} failed: {wifi.last_error}")

    if not connected:
        print("All WiFi connection attempts failed.")
        print("Switching to AP mode...")
        start_ap(config)

def start_ap(config):
    # Indicate AP status
    status_led.start_ap_mode()

    ap_ssid = config.get('ap_ssid', 'PoetrySociety_AP')
    ap_password = config.get('ap_password', 'admin1234')
    
    # Custom IP configuration for AP
    # Format: dict with ip, subnet, gateway, dns
    ap_ip_config = {
        'ip': '192.168.18.1',
        'subnet': '255.255.255.0',
        'gateway': '192.168.18.1',
        'dns': '8.8.8.8'
    }

    print(f"Starting Access Point: {ap_ssid} with IP {ap_ip_config['ip']}...")
    if wifi.create_hotspot(ap_ssid, ap_password, ip_config=ap_ip_config):
        info = wifi.get_hotspot_info()
        print(f"AP Started successfully. IP: {info.get('ip_address')}")
    else:
        print(f"Failed to start AP: {wifi.last_error}")

if __name__ == '__main__':
    connect_wifi()
    
    # Debug: Check files and manually start main if needed
    import os
    print("[Boot] List of files in root:", os.listdir())
    try:
        print("[Boot] List of files in static:", os.listdir('static'))
    except:
        print("[Boot] static folder not found or empty")

    print("\n" + "="*50)
    print("⚡️ 为了方便开发调试，增加 5秒 等待时间...")
    print("⚡️ 如果需要上传文件，请现在按 Ctrl+C 中断运行！")
    print("="*50 + "\n")
    time.sleep(5)
    
    try:
        print("[Boot] Attempting to start main application...")
        import main
        # Manually trigger the start if main.py didn't run automatically (which happens on import)
        if hasattr(main, 'app'):
            # Intelligent LED Status Update (Single LED Logic)
            if network.WLAN(network.AP_IF).active():
                 print("[Boot] AP Mode detected. Setting LED to AP Mode (Medium Breath).")
                 status_led.start_ap_mode()
            else:
                 print("[Boot] Station Mode detected. Setting LED to Running Mode (Slow Breath).")
                 status_led.start_running()
            
            main.print_system_status()
            main.app.run(port=80) or main.app.run(port=80)
    except Exception as e:
        print(f"[Boot] Error starting main: {e}")
