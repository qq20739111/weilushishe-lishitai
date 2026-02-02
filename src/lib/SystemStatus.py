"""
SystemStatus.py - 管理系统LED状态指示
用于控制 ESP32-S2 板载 LED (GPIO 15) 显示系统运行状态

设计逻辑 (单灯模式 - GPIO 15):
- 正在连接: 快速呼吸 (Cycle=500ms) - 表示忙碌
- AP 热点模式: 中速呼吸 (Cycle=1500ms) - 表示等待连接
- WiFi 运行模式: 极慢呼吸 (Cycle=4000ms) - 表示稳定运行
- 请求响应: 快闪一次 (Cycle=200ms) - 表示处理完成

节能策略：
- 连接成功后呼吸1分钟自动关闭LED，节省CPU资源
- 收到请求响应成功后快闪1次提供视觉反馈
"""
from machine import Timer
from lib.BreathLED import BreathLED
from lib.Logger import debug, info, warn, error
import time

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
    CYCLE_FLASH = 200        # 快闪
    
    # 自动关闭时间 (毫秒)
    AUTO_OFF_DELAY = 60000   # 1分钟后自动关闭

    def __init__(self):
        self._auto_off_timer = None
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
        self._cancel_auto_off()
        self._is_idle = False
        self._set_cycle(self.CYCLE_CONNECTING)

    def start_ap_mode(self):
        """指示处于AP热点模式: 中速呼吸，1分钟后自动关闭"""
        debug("LED指示: AP模式 (中速呼吸)", "Status")
        self._is_idle = False
        self._set_cycle(self.CYCLE_AP_MODE)
        self._schedule_auto_off()

    def start_running(self):
        """指示系统稳定运行 (WiFi连接成功): 极慢呼吸，1分钟后自动关闭"""
        debug("LED指示: 运行中 (慢速呼吸)", "Status")
        self._is_idle = False
        self._set_cycle(self.CYCLE_RUNNING)
        self._schedule_auto_off()

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
        self._cancel_auto_off()
        self._is_idle = True
        if self.led: 
            self.led.stop()

    def _set_cycle(self, cycle):
        """
        内部方法：设置LED呼吸周期
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

    def _schedule_auto_off(self):
        """安排1分钟后自动关闭LED"""
        self._cancel_auto_off()
        
        try:
            self._auto_off_timer = Timer(-1)
            self._auto_off_timer.init(
                mode=Timer.ONE_SHOT,
                period=self.AUTO_OFF_DELAY,
                callback=self._auto_off_callback
            )
            debug(f"LED将在{self.AUTO_OFF_DELAY//1000}秒后自动关闭", "Status")
        except Exception as e:
            debug(f"设置自动关闭定时器失败: {e}", "Status")

    def _auto_off_callback(self, timer):
        """自动关闭回调"""
        try:
            debug("LED自动关闭，节省CPU资源", "Status")
            self._is_idle = True
            if self.led:
                self.led.stop()
        except Exception as e:
            debug(f"LED自动关闭失败: {e}", "Status")

    def _cancel_auto_off(self):
        """取消自动关闭定时器"""
        if self._auto_off_timer:
            try:
                self._auto_off_timer.deinit()
            except:
                pass
            self._auto_off_timer = None

# 全局实例，供 boot.py 和 main.py 共享调用
status_led = SystemStatus()
