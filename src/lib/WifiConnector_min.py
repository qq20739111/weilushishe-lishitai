import network
import time
import ubinascii
import ujson as json
class WifiConnector:
    DEFAULT_SCAN_TIMEOUT = 10
    DEFAULT_CONNECT_TIMEOUT = 15
    DEFAULT_MAX_RETRIES = 3
    MIN_PASSWORD_LENGTH = 8
    DEFAULT_SYNC_INTERVAL = 300
    DEFAULT_FORCE_SYNC_INTERVAL = 1800
    AP_AUTHMODE_OPEN = 0
    AP_AUTHMODE_WEP = 1
    AP_AUTHMODE_WPA_PSK = 2
    AP_AUTHMODE_WPA2_PSK = 3
    AP_AUTHMODE_WPA_WPA2_PSK = 4
    DEFAULT_HOTSPOT_IP = '192.168.4.1'
    DEFAULT_HOTSPOT_SUBNET = '255.255.255.0'
    DEFAULT_HOTSPOT_CHANNEL = 11
    DEFAULT_HOTSPOT_MAX_CLIENTS = 4
    DEFAULT_SUBNET = '255.255.255.0'
    DEFAULT_DNS = '8.8.8.8'
    DEFAULT_DNS_SECONDARY = '8.8.4.4'
    def __init__(self, debug=False):
        self.debug = debug
        self.last_error = None
        self.sta = network.WLAN(network.STA_IF)
        self.ap = network.WLAN(network.AP_IF)
        self._network_config = {
            'ssid': None,
            'password': None,
            'ip_address': None,
            'subnet_mask': None,
            'gateway_ip': None,
            'dns_server': None,
            'mac_address': None,
            'gateway_mac': None
        }
        self._static_ip_config = {
            'enabled': False,
            'ip': None,
            'subnet': self.DEFAULT_SUBNET,
            'gateway': None,
            'dns': self.DEFAULT_DNS,
            'dns_secondary': self.DEFAULT_DNS_SECONDARY
        }
        self._hotspot_config = {
            'ssid': None,
            'password': None,
            'channel': self.DEFAULT_HOTSPOT_CHANNEL,
            'max_clients': self.DEFAULT_HOTSPOT_MAX_CLIENTS,
            'authmode': self.AP_AUTHMODE_WPA2_PSK,
            'ip_config': {
                'ip': self.DEFAULT_HOTSPOT_IP,
                'subnet': self.DEFAULT_HOTSPOT_SUBNET,
                'gateway': self.DEFAULT_HOTSPOT_IP,
                'dns': self.DEFAULT_HOTSPOT_IP
            }
        }
        self.scan_timeout = self.DEFAULT_SCAN_TIMEOUT
        self.connect_timeout = self.DEFAULT_CONNECT_TIMEOUT
        self.max_retries = self.DEFAULT_MAX_RETRIES
        self.sync_interval = self.DEFAULT_SYNC_INTERVAL
        self.force_sync_interval = self.DEFAULT_FORCE_SYNC_INTERVAL
        self.last_sync_time = 0
        self.connection_attempts = 0
        self._initialize_sta()
    def __del__(self):
        try:
            self.cleanup()
        except:
            pass
    def _initialize_sta(self):
        if not self.sta.active():
            self.sta.active(True)
            time.sleep(0.1)
    def _log(self, message, level="INFO"):
        if self.debug:
            print(f"[WiFi-{level}] {message}")
    def _set_error(self, error_msg):
        self.last_error = error_msg
        self._log(f"错误: {error_msg}", "ERROR")
    def _clear_error(self):
        self.last_error = None
    def _format_mac_address(self, mac_hex):
        if not mac_hex or not isinstance(mac_hex, str) or len(mac_hex) != 12:
            return mac_hex
        try:
            return ':'.join(mac_hex[i:i+2] for i in range(0, 12, 2))
        except Exception:
            return mac_hex
    def _validate_connection_params(self, ssid, password=None):
        if not isinstance(ssid, str):
            self._set_error(f"SSID必须是字符串类型，当前类型: {type(ssid).__name__}")
            return False
        if password is not None and not isinstance(password, str):
            self._set_error(f"密码必须是字符串类型，当前类型: {type(password).__name__}")
            return False
        if not ssid or not ssid.strip():
            self._set_error("SSID不能为空")
            return False
        if password is not None and password != "" and len(password) < 8:
            self._set_error("WiFi密码长度必须至少8位")
            return False
        return True
    def _get_signal_quality_description(self, rssi):
        quality_map = {
            -50: "优秀", -60: "良好", -70: "一般", -80: "较差"
        }
        for threshold, quality in quality_map.items():
            if rssi >= threshold:
                return quality
        return "很差"
    def _get_auth_mode_name(self, authmode):
        auth_modes = {
            0: "开放", 1: "WEP", 2: "WPA-PSK", 
            3: "WPA2-PSK", 4: "WPA/WPA2-PSK", 5: "WPA2-Enterprise"
        }
        return auth_modes.get(authmode, f"未知({authmode})")
    def _get_connection_status_description(self, status):
        status_map = {
            network.STAT_IDLE: "空闲状态",
            network.STAT_CONNECTING: "正在连接",
            network.STAT_WRONG_PASSWORD: "密码错误",
            network.STAT_NO_AP_FOUND: "未找到接入点",
            network.STAT_CONNECT_FAIL: "连接失败",
            network.STAT_GOT_IP: "已获取IP地址"
        }
        return status_map.get(status, f"未知状态({status})")
    def _sync_network_info(self):
        if not self.is_connected():
            return False
        try:
            config = self.sta.ifconfig()
            self._network_config.update({
                'ip_address': config[0],
                'subnet_mask': config[1],
                'gateway_ip': config[2],
                'dns_server': config[3]
            })
            try:
                mac_bytes = self.sta.config('mac')
                mac_hex = ubinascii.hexlify(mac_bytes).decode()
                self._network_config['mac_address'] = self._format_mac_address(mac_hex)
            except Exception as e:
                self._log(f"获取MAC地址失败: {e}", "WARN")
                self._network_config['mac_address'] = None
            self.last_sync_time = time.time()
            self._log("网络信息同步完成")
            return True
        except Exception as e:
            self._log(f"同步网络信息失败: {e}", "ERROR")
            return False
    def _should_sync_network_info(self, force=False):
        if not self.is_connected():
            return False
        if force or self.last_sync_time == 0:
            return True
        current_time = time.time()
        time_since_last_sync = current_time - self.last_sync_time
        if time_since_last_sync > self.force_sync_interval:
            return True
        if time_since_last_sync > self.sync_interval:
            try:
                current_ip = self.sta.ifconfig()[0]
                cached_ip = self._network_config.get('ip_address')
                if current_ip != cached_ip:
                    self._log(f"检测到IP变化: {cached_ip} -> {current_ip}")
                    return True
            except Exception:
                return True
        return False
    def _auto_sync_network_info(self, force=False):
        if self._should_sync_network_info(force):
            return self._sync_network_info()
        return False
    def _reset_wifi_module(self):
        try:
            self._log("重置WiFi模块...")
            if self.sta.active():
                self.sta.active(False)
            if self.ap.active():
                self.ap.active(False)
            time.sleep(1)
            self.sta.active(True)
            time.sleep(0.5)
            self._log("WiFi模块重置完成")
        except Exception as e:
            self._log(f"WiFi模块重置失败: {e}", "ERROR")
    def _validate_ip_address(self, ip):
        if not ip or not isinstance(ip, str):
            return False
        try:
            parts = ip.split('.')
            if len(parts) != 4:
                return False
            for part in parts:
                num = int(part)
                if num < 0 or num > 255:
                    return False
            return True
        except (ValueError, AttributeError):
            return False
    def _validate_subnet_mask(self, subnet):
        valid_masks = [
            '255.255.255.255', '255.255.255.254', '255.255.255.252',
            '255.255.255.248', '255.255.255.240', '255.255.255.224',
            '255.255.255.192', '255.255.255.128', '255.255.255.0',
            '255.255.254.0', '255.255.252.0', '255.255.248.0',
            '255.255.240.0', '255.255.224.0', '255.255.192.0',
            '255.255.128.0', '255.255.0.0', '255.254.0.0',
            '255.252.0.0', '255.248.0.0', '255.240.0.0',
            '255.224.0.0', '255.192.0.0', '255.128.0.0', '255.0.0.0'
        ]
        return subnet in valid_masks
    def _infer_gateway(self, ip):
        if not ip:
            return None
        try:
            parts = ip.split('.')
            if len(parts) == 4:
                return f"{parts[0]}.{parts[1]}.{parts[2]}.1"
        except Exception:
            pass
        return None
    def _configure_static_ip(self, static_config):
        try:
            ip = static_config.get('ip')
            subnet = static_config.get('subnet', self.DEFAULT_SUBNET)
            gateway = static_config.get('gateway') or self._infer_gateway(ip)
            dns = static_config.get('dns', self.DEFAULT_DNS)
            if not self._validate_ip_address(ip):
                self._set_error(f"无效的IP地址格式: {ip}")
                return False
            if not gateway:
                self._set_error("静态IP配置不完整，需要gateway")
                return False
            if not self._validate_ip_address(gateway):
                self._set_error(f"无效的网关地址格式: {gateway}")
                return False
            if not self._validate_subnet_mask(subnet):
                self._log(f"非标准子网掩码: {subnet}，继续使用", "WARN")
            if not self._validate_ip_address(dns):
                self._log(f"无效的DNS地址: {dns}，使用默认DNS", "WARN")
                dns = self.DEFAULT_DNS
            self.sta.ifconfig((ip, subnet, gateway, dns))
            time.sleep(0.1)
            actual_config = self.sta.ifconfig()
            self._network_config.update({
                'ip_address': actual_config[0],
                'subnet_mask': actual_config[1],
                'gateway_ip': actual_config[2],
                'dns_server': actual_config[3]
            })
            self._static_ip_config.update({
                'enabled': True,
                'ip': ip,
                'subnet': subnet,
                'gateway': gateway,
                'dns': dns
            })
            self._log(f"静态IP配置成功: {actual_config[0]}")
            return True
        except Exception as e:
            self._set_error(f"静态IP配置失败: {e}")
            return False
    def _reset_static_ip_config(self):
        self._static_ip_config = {
            'enabled': False,
            'ip': None,
            'subnet': self.DEFAULT_SUBNET,
            'gateway': None,
            'dns': self.DEFAULT_DNS,
            'dns_secondary': self.DEFAULT_DNS_SECONDARY
        }
    def scan_networks(self, timeout=None):
        timeout = timeout or self.scan_timeout
        try:
            self._log("开始扫描WiFi网络...")
            self._initialize_sta()
            networks = self.sta.scan()
            if not networks:
                self._set_error("未发现任何WiFi网络")
                return []
            formatted_networks = []
            for net in networks:
                ssid = net[0].decode('utf-8') if isinstance(net[0], bytes) else str(net[0])
                bssid = ubinascii.hexlify(net[1]).decode() if len(net) > 1 else 'unknown'
                channel = net[2] if len(net) > 2 else 0
                rssi = net[3] if len(net) > 3 else 0
                authmode = net[4] if len(net) > 4 else 0
                network_info = {
                    'ssid': ssid,
                    'bssid': bssid,
                    'channel': channel,
                    'rssi': rssi,
                    'authmode': authmode,
                    'auth_name': self._get_auth_mode_name(authmode),
                    'signal_strength': self._get_signal_quality_description(rssi)
                }
                formatted_networks.append(network_info)
            formatted_networks.sort(key=lambda x: x['rssi'], reverse=True)
            self._log(f"发现 {len(formatted_networks)} 个网络")
            self._clear_error()
            return formatted_networks
        except Exception as e:
            self._set_error(f"扫描网络失败: {e}")
            return []
    def find_network(self, ssid):
        networks = self.scan_networks()
        for network in networks:
            if network['ssid'] == ssid:
                return network
        return None
    def connect(self, ssid, password=None, timeout=None, static_ip=None):
        timeout = timeout or self.connect_timeout
        self.connection_attempts += 1
        try:
            self._log(f"尝试连接到 '{ssid}' (第{self.connection_attempts}次)")
            if not self._validate_connection_params(ssid, password):
                return False
            if self.sta.isconnected():
                self.disconnect()
                time.sleep(1)
            if self.connection_attempts > 1:
                self._reset_wifi_module()
            self._initialize_sta()
            if static_ip:
                if not self._configure_static_ip(static_ip):
                    self._log("静态IP配置失败，将使用DHCP", "WARN")
                    self._static_ip_config['enabled'] = False
            else:
                self._static_ip_config['enabled'] = False
            self._log(f"开始连接到网络: {ssid}")
            if password:
                self.sta.connect(ssid, password)
            else:
                self.sta.connect(ssid)
            start_time = time.time()
            last_status = None
            while not self.sta.isconnected() and (time.time() - start_time) < timeout:
                current_status = self.sta.status()
                if current_status != last_status:
                    status_msg = self._get_connection_status_description(current_status)
                    self._log(f"连接状态: {status_msg}")
                    last_status = current_status
                    error_states = [
                        network.STAT_WRONG_PASSWORD,
                        network.STAT_NO_AP_FOUND,
                        network.STAT_CONNECT_FAIL
                    ]
                    if current_status in error_states:
                        error_msg = self._get_connection_status_description(current_status)
                        self._set_error(f"连接失败: {error_msg} (网络: {ssid})")
                        return False
                time.sleep(0.5)
            if self.sta.isconnected():
                self.reset_connection_counter()
                self._network_config['ssid'] = ssid
                self._network_config['password'] = password
                self._sync_network_info()
                self._log(f"连接成功! IP: {self._network_config['ip_address']}")
                self._clear_error()
                return True
            else:
                final_status = self.sta.status()
                status_msg = self._get_connection_status_description(final_status)
                self._set_error(f"连接超时: {status_msg} (网络: {ssid})")
                return False
        except Exception as e:
            error_msg = f"连接失败: {e}"
            if "Internal Error" in str(e):
                error_msg += " (WiFi模块内部错误，建议重启)"
            self._set_error(error_msg)
            return False
    def disconnect(self, keep_credentials=True):
        try:
            if self.sta.isconnected():
                self.sta.disconnect()
                start_time = time.time()
                while self.sta.isconnected() and (time.time() - start_time) < 5:
                    time.sleep(0.1)
                self._log("已断开WiFi连接")
            if not keep_credentials:
                self._network_config['ssid'] = None
                self._network_config['password'] = None
                self._reset_static_ip_config()
            network_state_keys = [
                'ip_address', 'subnet_mask', 'gateway_ip', 
                'dns_server', 'mac_address', 'gateway_mac'
            ]
            for key in network_state_keys:
                self._network_config[key] = None
            self.last_sync_time = 0
            self._clear_error()
            return True
        except Exception as e:
            self._set_error(f"断开连接失败: {e}")
            return False
    def forget_network(self):
        try:
            if self.sta.isconnected():
                self.disconnect(keep_credentials=False)
            else:
                self._network_config['ssid'] = None
                self._network_config['password'] = None
                self._reset_static_ip_config()
            self._log("已清除网络凭据")
            self._clear_error()
            return True
        except Exception as e:
            self._set_error(f"清除凭据失败: {e}")
            return False
    def reconnect(self, max_attempts=None):
        max_attempts = max_attempts or self.max_retries
        ssid = self._network_config.get('ssid')
        password = self._network_config.get('password')
        if not ssid:
            self._set_error("没有保存的网络信息")
            return False
        self._log("开始自动重连...")
        self._initialize_sta()
        for attempt in range(max_attempts):
            self._log(f"重连尝试 {attempt + 1}/{max_attempts}")
            try:
                static_ip = self.get_static_ip_config() if self.is_static_ip_enabled() else None
                if self.connect(ssid, password, timeout=self.connect_timeout, static_ip=static_ip):
                    self._log("重连成功")
                    return True
            except Exception as e:
                self._log(f"重连尝试失败: {e}", "WARN")
            if attempt < max_attempts - 1:
                time.sleep(2)
        self._set_error(f"重连失败，已尝试 {max_attempts} 次")
        return False
    def is_connected(self):
        return self.sta.isconnected()
    def get_connection_status(self):
        status = {
            'connected': self.is_connected(),
            'ssid': self._network_config.get('ssid'),
            'has_credentials': bool(self._network_config.get('ssid')),
            'connection_attempts': self.connection_attempts,
            'last_error': self.last_error
        }
        if self.is_connected():
            self._auto_sync_network_info()
            status.update({
                'ip_address': self._network_config.get('ip_address'),
                'subnet_mask': self._network_config.get('subnet_mask'),
                'gateway_ip': self._network_config.get('gateway_ip'),
                'dns_server': self._network_config.get('dns_server'),
                'mac_address': self._network_config.get('mac_address')
            })
        return status
    def get_network_info(self):
        if not self.is_connected():
            return {'connected': False, 'error': '未连接'}
        self._auto_sync_network_info()
        info = {
            'connected': True,
            'ssid': self._network_config.get('ssid'),
            'ip_address': self._network_config.get('ip_address'),
            'subnet_mask': self._network_config.get('subnet_mask'),
            'gateway_ip': self._network_config.get('gateway_ip'),
            'dns_server': self._network_config.get('dns_server'),
            'mac_address': self._network_config.get('mac_address'),
            'status_code': self.sta.status()
        }
        try:
            network_info = self.find_network(self._network_config.get('ssid'))
            if network_info:
                info['rssi'] = network_info['rssi']
                info['signal_quality'] = network_info['signal_strength']
        except Exception:
            pass
        return info
    def get_ip_address(self):
        if self.is_connected():
            self._auto_sync_network_info()
            return self._network_config.get('ip_address')
        return None
    def get_mac_address(self):
        if self.is_connected():
            if not self._network_config.get('mac_address'):
                self._sync_network_info()
            return self._network_config.get('mac_address')
        return None
    def get_gateway_ip(self):
        if self.is_connected():
            self._auto_sync_network_info()
            return self._network_config.get('gateway_ip')
        return None
    def get_ssid(self):
        return self._network_config.get('ssid')
    def get_last_error(self):
        return self.last_error
    def configure_static_ip(self, ip, subnet=None, gateway=None, dns=None, dns_secondary=None):
        subnet = subnet or self.DEFAULT_SUBNET
        gateway = gateway or self._infer_gateway(ip)
        dns = dns or self.DEFAULT_DNS
        dns_secondary = dns_secondary or self.DEFAULT_DNS_SECONDARY
        if not self._validate_ip_address(ip):
            self._set_error(f"无效的IP地址格式: {ip}")
            return False
        if not gateway:
            self._set_error("无法推断网关地址，请手动指定gateway参数")
            return False
        if not self._validate_ip_address(gateway):
            self._set_error(f"无效的网关地址格式: {gateway}")
            return False
        if not self._validate_subnet_mask(subnet):
            self._log(f"非标准子网掩码: {subnet}", "WARN")
        if not self._validate_ip_address(dns):
            self._log(f"无效的DNS地址: {dns}，使用默认DNS", "WARN")
            dns = self.DEFAULT_DNS
        self._static_ip_config.update({
            'enabled': True,
            'ip': ip,
            'subnet': subnet,
            'gateway': gateway,
            'dns': dns,
            'dns_secondary': dns_secondary
        })
        self._log(f"静态IP配置已保存: {ip}")
        self._clear_error()
        return True
    def clear_static_ip_config(self):
        try:
            self._reset_static_ip_config()
            self._log("静态IP配置已清除")
            self._clear_error()
            return True
        except Exception as e:
            self._set_error(f"清除静态IP配置失败: {e}")
            return False
    def is_static_ip_enabled(self):
        return self._static_ip_config.get('enabled', False)
    def is_dhcp_enabled(self):
        return not self.is_static_ip_enabled()
    def get_static_ip_config(self):
        if self._static_ip_config.get('enabled'):
            return {
                'ip': self._static_ip_config.get('ip'),
                'subnet': self._static_ip_config.get('subnet'),
                'gateway': self._static_ip_config.get('gateway'),
                'dns': self._static_ip_config.get('dns'),
                'dns_secondary': self._static_ip_config.get('dns_secondary')
            }
        return None
    def get_ip_mode(self):
        return 'static' if self.is_static_ip_enabled() else 'dhcp'
    def switch_to_static_ip(self, ip, subnet=None, gateway=None, dns=None):
        if not self.is_connected():
            self._set_error("未连接到WiFi，无法切换IP模式")
            return False
        subnet = subnet or self.DEFAULT_SUBNET
        gateway = gateway or self._infer_gateway(ip)
        dns = dns or self.DEFAULT_DNS
        static_config = {
            'ip': ip,
            'subnet': subnet,
            'gateway': gateway,
            'dns': dns
        }
        result = self._configure_static_ip(static_config)
        if result:
            self._log(f"已切换到静态IP: {ip}")
        return result
    def switch_to_dhcp(self):
        if not self.is_connected():
            self._reset_static_ip_config()
            self._log("已切换到DHCP模式")
            return True
        ssid = self._network_config.get('ssid')
        password = self._network_config.get('password')
        if not ssid:
            self._set_error("无法获取当前网络信息")
            return False
        self._reset_static_ip_config()
        self._log("切换到DHCP，正在重新连接...")
        self.disconnect(keep_credentials=True)
        time.sleep(1)
        result = self.connect(ssid, password)
        if result:
            self._log("已切换到DHCP模式")
        else:
            self._set_error("切换到DHCP失败，重连失败")
        return result
    def connect_with_static_ip(self, ssid, password=None, ip=None, subnet=None, 
                                gateway=None, dns=None, timeout=None):
        if not ip:
            self._set_error("使用静态IP连接必须提供ip参数")
            return False
        static_config = {
            'ip': ip,
            'subnet': subnet or self.DEFAULT_SUBNET,
            'gateway': gateway or self._infer_gateway(ip),
            'dns': dns or self.DEFAULT_DNS
        }
        return self.connect(ssid, password, timeout=timeout, static_ip=static_config)
    def get_configured_static_ip(self):
        return self._static_ip_config.get('ip')
    def get_configured_gateway(self):
        return self._static_ip_config.get('gateway')
    def get_configured_dns(self):
        return self._static_ip_config.get('dns')
    def get_configured_subnet(self):
        return self._static_ip_config.get('subnet')
    def create_hotspot(self, ssid, password=None, channel=None, max_clients=None, 
                       authmode=None, ip_config=None):
        try:
            channel = channel or self._hotspot_config.get('channel', self.DEFAULT_HOTSPOT_CHANNEL)
            max_clients = max_clients or self._hotspot_config.get('max_clients', self.DEFAULT_HOTSPOT_MAX_CLIENTS)
            if not isinstance(ssid, str):
                self._set_error(f"热点SSID必须是字符串类型，当前类型: {type(ssid).__name__}")
                return False
            if not ssid or not ssid.strip():
                self._set_error("热点SSID不能为空")
                return False
            if password is not None:
                if not isinstance(password, str):
                    self._set_error(f"热点密码必须是字符串类型，当前类型: {type(password).__name__}")
                    return False
                if password != "" and len(password) < self.MIN_PASSWORD_LENGTH:
                    self._set_error(f"热点密码长度必须至少{self.MIN_PASSWORD_LENGTH}位")
                    return False
            if not (1 <= channel <= 13):
                self._set_error(f"信道必须在1-13之间，当前值: {channel}")
                return False
            if not (1 <= max_clients <= 10):
                self._set_error(f"最大客户端数必须在1-10之间，当前值: {max_clients}")
                return False
            self.ap.active(True)
            time.sleep(0.1)
            effective_ip_config = ip_config or self._hotspot_config.get('ip_config')
            if effective_ip_config:
                self._configure_hotspot_ip(effective_ip_config)
            if authmode is not None:
                auth_mode_code = authmode
            elif password:
                auth_mode_code = self.AP_AUTHMODE_WPA2_PSK
            else:
                auth_mode_code = self.AP_AUTHMODE_OPEN
            if password and auth_mode_code != self.AP_AUTHMODE_OPEN:
                self.ap.config(
                    essid=ssid, 
                    password=password, 
                    channel=channel, 
                    max_clients=max_clients,
                    authmode=auth_mode_code
                )
            else:
                self.ap.config(
                    essid=ssid, 
                    channel=channel, 
                    max_clients=max_clients,
                    authmode=self.AP_AUTHMODE_OPEN
                )
            self._hotspot_config.update({
                'ssid': ssid,
                'password': password,
                'channel': channel,
                'max_clients': max_clients,
                'authmode': auth_mode_code
            })
            if ip_config:
                self._hotspot_config['ip_config'] = ip_config
            config = self.ap.ifconfig()
            auth_mode_name = self._get_auth_mode_name(auth_mode_code)
            self._log(f"热点已创建: {ssid} ({auth_mode_name}), AP IP: {config[0]}")
            self._clear_error()
            return True
        except Exception as e:
            self._set_error(f"创建热点失败: {e}")
            return False
    def _configure_hotspot_ip(self, ip_config):
        try:
            ip = ip_config.get('ip', self.DEFAULT_HOTSPOT_IP)
            subnet = ip_config.get('subnet', self.DEFAULT_HOTSPOT_SUBNET)
            gateway = ip_config.get('gateway', ip)
            dns = ip_config.get('dns', ip)
            self.ap.ifconfig((ip, subnet, gateway, dns))
            time.sleep(0.1)
            self._log(f"热点IP配置成功: {ip}")
        except Exception as e:
            self._log(f"热点IP配置失败: {e}", "ERROR")
    def configure_hotspot_ip(self, ip='192.168.4.1', subnet='255.255.255.0', 
                             gateway=None, dns=None):
        try:
            gateway = gateway or ip
            dns = dns or ip
            ip_config = {
                'ip': ip,
                'subnet': subnet,
                'gateway': gateway,
                'dns': dns
            }
            self._hotspot_config['ip_config'] = ip_config
            if self.ap.active():
                self._configure_hotspot_ip(ip_config)
            self._log(f"热点IP配置已设置: {ip}")
            self._clear_error()
            return True
        except Exception as e:
            self._set_error(f"配置热点IP失败: {e}")
            return False
    def stop_hotspot(self):
        try:
            if self.ap.active():
                self.ap.active(False)
                self._log("热点已停止")
            self._clear_error()
            return True
        except Exception as e:
            self._set_error(f"停止热点失败: {e}")
            return False
    def is_hotspot_active(self):
        return self.ap.active()
    def get_hotspot_info(self):
        if not self.ap.active():
            return {'active': False}
        try:
            config = self.ap.ifconfig()
            mac_address = None
            try:
                mac_bytes = self.ap.config('mac')
                mac_hex = ubinascii.hexlify(mac_bytes).decode()
                mac_address = self._format_mac_address(mac_hex)
            except Exception:
                pass
            ssid = None
            try:
                ssid = self.ap.config('essid')
            except Exception:
                ssid = self._hotspot_config.get('ssid')
            authmode = self._hotspot_config.get('authmode', self.AP_AUTHMODE_WPA2_PSK)
            try:
                authmode = self.ap.config('authmode')
            except Exception:
                pass
            client_count = 0
            try:
                stations = self.ap.status('stations')
                client_count = len(stations) if stations else 0
            except Exception:
                pass
            return {
                'active': True,
                'ssid': ssid,
                'channel': self._hotspot_config.get('channel', self.DEFAULT_HOTSPOT_CHANNEL),
                'authmode': authmode,
                'authmode_name': self._get_auth_mode_name(authmode),
                'max_clients': self._hotspot_config.get('max_clients', self.DEFAULT_HOTSPOT_MAX_CLIENTS),
                'ip_address': config[0],
                'subnet_mask': config[1],
                'gateway_ip': config[2],
                'dns_server': config[3],
                'mac_address': mac_address,
                'client_count': client_count
            }
        except Exception as e:
            return {'active': True, 'error': f'获取信息失败: {e}'}
    def get_hotspot_clients(self):
        if not self.ap.active():
            return []
        try:
            stations = self.ap.status('stations')
            if not stations:
                return []
            clients = []
            for station in stations:
                mac_hex = ubinascii.hexlify(station[0]).decode()
                clients.append({
                    'mac': self._format_mac_address(mac_hex)
                })
            self._log(f"当前连接的客户端数: {len(clients)}")
            return clients
        except Exception as e:
            self._log(f"获取客户端列表失败: {e}", "WARN")
            return []
    def get_hotspot_ssid(self):
        if self.ap.active():
            try:
                return self.ap.config('essid')
            except Exception:
                pass
        return self._hotspot_config.get('ssid')
    def get_hotspot_ip(self):
        if self.ap.active():
            try:
                return self.ap.ifconfig()[0]
            except Exception:
                pass
        return self._hotspot_config.get('ip_config', {}).get('ip')
    def get_hotspot_mac(self):
        try:
            if self.ap.active():
                mac_bytes = self.ap.config('mac')
                mac_hex = ubinascii.hexlify(mac_bytes).decode()
                return self._format_mac_address(mac_hex)
        except Exception:
            pass
        return None
    def save_hotspot_config(self, filename='hotspot_config.json', include_password=False):
        try:
            config = {
                'ssid': self._hotspot_config.get('ssid'),
                'password': self._hotspot_config.get('password') if include_password else None,
                'channel': self._hotspot_config.get('channel', self.DEFAULT_HOTSPOT_CHANNEL),
                'max_clients': self._hotspot_config.get('max_clients', self.DEFAULT_HOTSPOT_MAX_CLIENTS),
                'authmode': self._hotspot_config.get('authmode', self.AP_AUTHMODE_WPA2_PSK),
                'ip_config': self._hotspot_config.get('ip_config')
            }
            with open(filename, 'w') as f:
                json.dump(config, f)
            self._log(f"热点配置已保存到 {filename}")
            if include_password:
                self._log("警告: 密码已保存到文件中", "WARN")
            self._clear_error()
            return True
        except Exception as e:
            self._set_error(f"保存热点配置失败: {e}")
            return False
    def load_hotspot_config(self, filename='hotspot_config.json'):
        try:
            with open(filename, 'r') as f:
                config = json.load(f)
            if config.get('ssid'):
                self._hotspot_config['ssid'] = config['ssid']
            if config.get('password'):
                self._hotspot_config['password'] = config['password']
            if 'channel' in config:
                self._hotspot_config['channel'] = config['channel']
            if 'max_clients' in config:
                self._hotspot_config['max_clients'] = config['max_clients']
            if 'authmode' in config:
                self._hotspot_config['authmode'] = config['authmode']
            if 'ip_config' in config and config['ip_config']:
                self._hotspot_config['ip_config'] = config['ip_config']
            self._log(f"热点配置已从 {filename} 加载")
            self._clear_error()
            return True
        except Exception as e:
            self._set_error(f"加载热点配置失败: {e}")
            return False
    def start_hotspot_from_config(self):
        ssid = self._hotspot_config.get('ssid')
        if not ssid:
            self._set_error("没有已保存的热点配置，请先加载配置或设置SSID")
            return False
        return self.create_hotspot(
            ssid=ssid,
            password=self._hotspot_config.get('password'),
            channel=self._hotspot_config.get('channel'),
            max_clients=self._hotspot_config.get('max_clients'),
            authmode=self._hotspot_config.get('authmode'),
            ip_config=self._hotspot_config.get('ip_config')
        )
    def monitor_connection(self):
        result = {
            'connected': self.is_connected(),
            'sync_performed': False,
            'reconnect_attempted': False,
            'status': 'ok'
        }
        if not self.is_connected():
            if self._network_config.get('ssid') and self._network_config.get('password'):
                self._log("检测到连接断开，尝试自动重连...")
                if self.reconnect(max_attempts=1):
                    result['reconnect_attempted'] = True
                    result['connected'] = True
                    result['status'] = 'reconnected'
                else:
                    result['status'] = 'disconnected'
            else:
                result['status'] = 'disconnected'
        else:
            if self._auto_sync_network_info():
                result['sync_performed'] = True
                result['status'] = 'synced'
        return result
    def get_sync_status(self):
        current_time = time.time()
        return {
            'last_sync_time': self.last_sync_time,
            'last_sync_ago': current_time - self.last_sync_time if self.last_sync_time > 0 else -1,
            'sync_interval': self.sync_interval,
            'force_sync_interval': self.force_sync_interval,
            'next_check_in': max(0, self.sync_interval - (current_time - self.last_sync_time)) if self.last_sync_time > 0 else 0
        }
    def set_timeouts(self, scan_timeout=None, connect_timeout=None):
        if scan_timeout is not None:
            self.scan_timeout = max(5, scan_timeout)
            self._log(f"扫描超时设置为: {self.scan_timeout}秒")
        if connect_timeout is not None:
            self.connect_timeout = max(10, connect_timeout)
            self._log(f"连接超时设置为: {self.connect_timeout}秒")
    def set_sync_intervals(self, sync_interval=None, force_sync_interval=None):
        if sync_interval is not None:
            self.sync_interval = max(60, sync_interval)
            self._log(f"同步间隔设置为: {self.sync_interval}秒")
        if force_sync_interval is not None:
            self.force_sync_interval = max(300, force_sync_interval)
            self._log(f"强制同步间隔设置为: {self.force_sync_interval}秒")
    def reset_connection_counter(self):
        self.connection_attempts = 0
        self._log("连接计数器已重置")
    def refresh_network_info(self, force=False):
        if not self.is_connected():
            network_keys = ['ip_address', 'subnet_mask', 'gateway_ip', 'dns_server', 'mac_address']
            for key in network_keys:
                self._network_config[key] = None
            self.last_sync_time = 0
            return False
        return self._auto_sync_network_info(force=force)
    def save_config(self, filename='wifi_config.json', include_password=False):
        try:
            static_ip_to_save = None
            if self._static_ip_config.get('enabled'):
                static_ip_to_save = {
                    'ip': self._static_ip_config.get('ip'),
                    'subnet': self._static_ip_config.get('subnet'),
                    'gateway': self._static_ip_config.get('gateway'),
                    'dns': self._static_ip_config.get('dns'),
                    'dns_secondary': self._static_ip_config.get('dns_secondary')
                }
            config = {
                'ssid': self._network_config.get('ssid'),
                'password': self._network_config.get('password') if include_password else None,
                'static_ip': static_ip_to_save,
                'static_ip_enabled': self._static_ip_config.get('enabled', False),
                'sync_interval': self.sync_interval,
                'force_sync_interval': self.force_sync_interval,
                'scan_timeout': self.scan_timeout,
                'connect_timeout': self.connect_timeout,
                'max_retries': self.max_retries
            }
            with open(filename, 'w') as f:
                json.dump(config, f)
            self._log(f"配置已保存到 {filename}")
            if include_password:
                self._log("警告: 密码已保存到文件中", "WARN")
            return True
        except Exception as e:
            self._set_error(f"保存配置失败: {e}")
            return False
    def load_config(self, filename='wifi_config.json'):
        try:
            with open(filename, 'r') as f:
                config = json.load(f)
            if config.get('ssid'):
                self._network_config['ssid'] = config['ssid']
            if config.get('password'):
                self._network_config['password'] = config['password']
            if 'static_ip' in config and config['static_ip']:
                static_ip = config['static_ip']
                self._static_ip_config.update({
                    'enabled': config.get('static_ip_enabled', True),
                    'ip': static_ip.get('ip'),
                    'subnet': static_ip.get('subnet', self.DEFAULT_SUBNET),
                    'gateway': static_ip.get('gateway'),
                    'dns': static_ip.get('dns', self.DEFAULT_DNS),
                    'dns_secondary': static_ip.get('dns_secondary', self.DEFAULT_DNS_SECONDARY)
                })
            elif 'static_ip_enabled' in config:
                self._static_ip_config['enabled'] = config['static_ip_enabled']
            if 'sync_interval' in config:
                self.sync_interval = max(60, config['sync_interval'])
            if 'force_sync_interval' in config:
                self.force_sync_interval = max(300, config['force_sync_interval'])
            if 'scan_timeout' in config:
                self.scan_timeout = max(5, config['scan_timeout'])
            if 'connect_timeout' in config:
                self.connect_timeout = max(10, config['connect_timeout'])
            if 'max_retries' in config:
                self.max_retries = max(1, config['max_retries'])
            self._log(f"配置已从 {filename} 加载")
            return True
        except Exception as e:
            self._set_error(f"加载配置失败: {e}")
            return False
    def get_diagnostics(self):
        diag = {
            'sta_active': self.sta.active(),
            'ap_active': self.ap.active(),
            'connected': self.is_connected(),
            'ssid': self._network_config.get('ssid'),
            'has_credentials': bool(self._network_config.get('ssid')),
            'ip_mode': self.get_ip_mode(),
            'static_ip_enabled': self.is_static_ip_enabled(),
            'static_ip_config': self.get_static_ip_config(),
            'connection_attempts': self.connection_attempts,
            'last_error': self.last_error,
            'last_sync_time': self.last_sync_time,
            'sync_interval': self.sync_interval,
            'force_sync_interval': self.force_sync_interval
        }
        if self.is_connected():
            diag.update(self.get_network_info())
        try:
            import esp32
            diag['esp32_hall_sensor'] = esp32.hall_sensor()
            diag['esp32_temperature'] = esp32.raw_temperature()
        except ImportError:
            pass
        except Exception:
            pass
        return diag
    def cleanup(self):
        try:
            if self.sta and self.sta.active():
                self.disconnect(keep_credentials=False)
                self.sta.active(False)
            if self.ap and self.ap.active():
                self.ap.active(False)
            self._log("WiFi资源已清理")
        except Exception as e:
            self._log(f"清理资源时出错: {e}", "ERROR")