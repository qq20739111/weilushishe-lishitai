"""
SystemStatus.py - 管理系统LED状态指示
用于控制 ESP32-S2 板载 LED (GPIO 15) 显示系统运行状态

设计逻辑 (单灯模式 - GPIO 15):
- 正在连接: 快速呼吸 (Cycle=500ms) - 表示忙碌
- 仅AP模式: 呼吸 (Cycle=1000ms) - 仅热点模式
- 仅WiFi模式: 呼吸 (Cycle=2000ms) - 仅STA模式
- AP+WiFi双模式: 慢呼吸 (Cycle=4000ms) - 双模式同时运行
- 请求响应: 快闪一次 (Cycle=200ms) - 表示处理完成

节能策略：
- 连接成功后呼吸1分钟自动关闭LED，节省CPU资源
- 收到请求响应成功后快闪1次提供视觉反馈
"""
from lib.BreathLED import BreathLED
from lib.Logger import debug, error

# -----------------
# 性能优化配置
# -----------------
# 适当调整以平衡效果与CPU占用
BreathLED.UPDATE_INTERVAL_MIN = 30 
BreathLED.UPDATE_INTERVAL_DIVISOR = 40

class SystemStatus:
    # 呼吸周期定义 (毫秒)
    CYCLE_CONNECTING = 500   # 快速 - 正在连接
    CYCLE_AP_MODE = 1000     # 仅AP模式 - 1秒
    CYCLE_RUNNING = 2000     # 仅WiFi模式 - 2秒
    CYCLE_DUAL_MODE = 4000   # AP+WiFi双模式 - 4秒
    CYCLE_FLASH = 200        # 快闪
    
    # 自动关闭时间 (毫秒)
    AUTO_OFF_DELAY = 60000   # 1分钟后自动关闭

    def __init__(self):
        self._is_idle = False  # 是否处于空闲状态（LED已关闭）
        try:
            # ESP32-S2 只有一个板载 LED，通常在 GPIO 15
            self.led = BreathLED(pin=15, led_type='normal', max_brightness=1023, breath_cycle=self.CYCLE_CONNECTING)
        except Exception as e:
            error(f"LED初始化失败: {e}", "Status")
            self.led = None

    def start_connecting(self):
        """指示正在连接WiFi: 快速呼吸"""
        debug("LED指示: 正在连接WiFi (快速呼吸)", "Status")
        self._is_idle = False
        self._set_cycle(self.CYCLE_CONNECTING)

    def start_ap_mode(self):
        """指示仅AP热点模式: 1秒周期呼吸，1分钟后自动关闭"""
        debug("LED指示: 仅AP模式 (1秒呼吸)", "Status")
        self._is_idle = False
        self._set_cycle_with_auto_off(self.CYCLE_AP_MODE)

    def start_running(self):
        """指示仅WiFi模式 (STA连接成功): 2秒周期呼吸，1分钟后自动关闭"""
        debug("LED指示: 仅WiFi模式 (2秒呼吸)", "Status")
        self._is_idle = False
        self._set_cycle_with_auto_off(self.CYCLE_RUNNING)

    def start_dual_mode(self):
        """指示AP+WiFi双模式同时运行: 4秒周期慢呼吸，1分钟后自动关闭"""
        debug("LED指示: AP+WiFi双模式 (4秒慢呼吸)", "Status")
        self._is_idle = False
        self._set_cycle_with_auto_off(self.CYCLE_DUAL_MODE)

    def flash_once(self):
        """
        API请求响应成功后快闪一次
        使用BreathLED的breath方法实现
        - 如果LED正在运行（无限呼吸），不中断，跳过快闪
        - 如果LED空闲，执行一次快速呼吸
        """
        if not self.led:
            return
        
        # 如果LED正在运行无限呼吸模式，跳过（避免中断）
        if self.led.is_running():
            return
        
        try:
            # LED空闲时，设置快闪周期并执行一次呼吸
            self.led.set_breath_cycle(self.CYCLE_FLASH)
            self.led.breath(1)  # 执行1次呼吸后自动停止
        except Exception as e:
            debug(f"快闪执行失败: {e}", "Status")

    def stop(self):
        """停止所有LED指示"""
        self._is_idle = True
        if self.led: 
            self.led.stop()

    def _set_cycle(self, cycle):
        """
        内部方法：设置LED呼吸周期（无限呼吸模式）
        利用 BreathLED.set_breath_cycle() 的热切换能力实现平滑过渡
        """
        if self.led:
            if self.led.is_running():
                # LED正在运行，直接设置新周期，BreathLED会自动重新配置定时器（不会熄灭）
                self.led.set_breath_cycle(cycle)
            else:
                # LED未运行，设置周期后启动
                self.led.set_breath_cycle(cycle)
                self.led.start()

    def _set_cycle_with_auto_off(self, cycle):
        """
        内部方法：设置LED呼吸周期（有限次数呼吸，自动关闭）
        使用 BreathLED.breath(cycles) 实现60秒后自动停止，无需额外定时器
        """
        if not self.led:
            return
        
        # 计算60秒需要多少次呼吸
        cycles = self.AUTO_OFF_DELAY // cycle
        
        # 如果LED正在无限呼吸模式，需要先停止
        if self.led.is_running():
            self.led.stop()
        
        # 设置周期并启动有限次数呼吸
        self.led.set_breath_cycle(cycle)
        self.led.breath(cycles)
        debug(f"LED将呼吸{cycles}次后自动关闭", "Status")

# 全局实例，供 boot.py 和 main.py 共享调用
status_led = SystemStatus()
