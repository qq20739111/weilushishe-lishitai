"""
SystemStatus.py - 管理系统LED状态指示
用于控制 ESP32-S2 板载 LED (GPIO 15) 显示系统运行状态

设计逻辑 (单灯模式 - GPIO 15):
- 正在连接: 快速呼吸 (Cycle=500ms) - 表示忙碌
- AP 热点模式: 中速呼吸 (Cycle=1500ms) - 表示等待连接
- WiFi 运行模式: 极慢呼吸 (Cycle=4000ms) - 表示稳定运行
"""
from lib.BreathLED import BreathLED

# -----------------
# 性能优化配置
# -----------------
# 适当调整以平衡效果与CPU占用
BreathLED.UPDATE_INTERVAL_MIN = 30 
BreathLED.UPDATE_INTERVAL_DIVISOR = 40

class SystemStatus:
    # 呼吸周期定义 (毫秒)
    CYCLE_CONNECTING = 500   # 快速
    CYCLE_AP_MODE = 1500     # 中速
    CYCLE_RUNNING = 4000     # 慢速 (常亮呼吸)

    def __init__(self):
        try:
            # ESP32-S2 只有一个板载 LED，通常在 GPIO 15
            self.led = BreathLED(pin=15, led_type='normal', max_brightness=1023, breath_cycle=self.CYCLE_CONNECTING)
        except Exception as e:
            print(f"[SystemStatus] LED初始化失败: {e}")
            self.led = None

    def start_connecting(self):
        """指示正在连接WiFi: 快速呼吸"""
        print("[Status] LED指示: 正在连接 WiFi (GPIO15 Fast Breath)")
        self._set_cycle(self.CYCLE_CONNECTING)

    def start_ap_mode(self):
        """指示处于AP热点模式: 中速呼吸"""
        print("[Status] LED指示: AP模式开启 (GPIO15 Medium Breath)")
        self._set_cycle(self.CYCLE_AP_MODE)

    def start_running(self):
        """指示系统稳定运行 (WiFi连接成功): 极慢呼吸"""
        print("[Status] LED指示: WiFi连接成功/运行中 (GPIO15 Slow Breath)")
        self._set_cycle(self.CYCLE_RUNNING)

    def stop(self):
        """停止所有LED指示"""
        if self.led: self.led.stop()

    def _set_cycle(self, cycle):
        """内部方法：设置LED呼吸周期"""
        if self.led:
            self.led.set_breath_cycle(cycle)
            if not self.led.is_running():
                self.led.start()

# 全局实例，供 boot.py 和 main.py 共享调用
status_led = SystemStatus()
