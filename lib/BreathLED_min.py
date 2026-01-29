from machine import Pin, Timer, PWM
import math
import gc
import neopixel
class BreathLED:
    _SINE_TABLE = None
    _TABLE_SIZE = 360
    LED_TYPE_WS2812 = 'ws2812'
    LED_TYPE_NORMAL = 'normal'
    PIN_MIN = 0
    PIN_MAX = 40
    PWM_FREQ_MIN = 1
    PWM_FREQ_MAX = 40000
    BREATH_CYCLE_MIN = 100
    WS2812_BRIGHTNESS_MAX = 255
    NORMAL_LED_BRIGHTNESS_MAX = 1023
    COLOR_VALUE_MAX = 255
    PWM_DUTY_MAX = 65535
    SINE_PRECISION = 1000
    UPDATE_INTERVAL_MIN = 10
    UPDATE_INTERVAL_DIVISOR = 200
    DEFAULT_PIN = 16
    DEFAULT_COLOR = (0, 127, 127)
    DEFAULT_MAX_BRIGHTNESS_WS2812 = 127
    DEFAULT_MIN_BRIGHTNESS = 0
    DEFAULT_BREATH_CYCLE = 3000
    DEFAULT_PWM_FREQ = 1000
    DEFAULT_DEBUG = False
    @classmethod
    def _init_sine_table(cls):
        if cls._SINE_TABLE is None:
            try:
                if cls._SINE_TABLE is None:
                    cls._SINE_TABLE = []
                    for i in range(cls._TABLE_SIZE):
                        radians = i * 2 * math.pi / cls._TABLE_SIZE
                        sine_value = (math.sin(radians - math.pi/2) + 1) / 2
                        cls._SINE_TABLE.append(int(sine_value * cls.SINE_PRECISION))
            except Exception:
                cls._SINE_TABLE = None
                raise
    def __init__(self, pin=None, led_type=None, num_leds=None, color=None, max_brightness=None, min_brightness=None, breath_cycle=None, pwm_freq=None, debug=None):
        resolved_pin = pin if pin is not None else self.DEFAULT_PIN
        resolved_led_type = led_type if led_type is not None else self.LED_TYPE_WS2812
        resolved_num_leds = num_leds if num_leds is not None else 1
        resolved_color = color if color is not None else self.DEFAULT_COLOR
        resolved_min_brightness = min_brightness if min_brightness is not None else self.DEFAULT_MIN_BRIGHTNESS
        resolved_breath_cycle = breath_cycle if breath_cycle is not None else self.DEFAULT_BREATH_CYCLE
        resolved_pwm_freq = pwm_freq if pwm_freq is not None else self.DEFAULT_PWM_FREQ
        resolved_debug = debug if debug is not None else self.DEFAULT_DEBUG
        if max_brightness is not None:
            resolved_max_brightness = max_brightness
        else:
            if resolved_led_type == self.LED_TYPE_WS2812:
                resolved_max_brightness = self.DEFAULT_MAX_BRIGHTNESS_WS2812
            else:
                resolved_max_brightness = self.NORMAL_LED_BRIGHTNESS_MAX
        self._validate_init_parameters(
            resolved_pin, resolved_led_type, resolved_num_leds, resolved_color,
            resolved_max_brightness, resolved_min_brightness, resolved_breath_cycle, resolved_pwm_freq, resolved_debug
        )
        self.pin = resolved_pin
        self.led_type = resolved_led_type
        self.num_leds = resolved_num_leds
        self.color = resolved_color
        self.max_brightness = resolved_max_brightness
        self.min_brightness = resolved_min_brightness
        self.breath_cycle = resolved_breath_cycle
        self.pwm_freq = resolved_pwm_freq
        self.debug_enabled = resolved_debug
        self._initialized = False
        self.current_angle = 0
        self.is_breathing = False
        self.timer = None
        self.led_pin = None
        self.np = None
        self.pwm = None
        self._remaining_updates = 0
        self.update_interval = max(self.UPDATE_INTERVAL_MIN, self.breath_cycle // self.UPDATE_INTERVAL_DIVISOR)
        self._setup_hardware()
        self._init_sine_table()
        self._initialized = True
    def __del__(self):
        try:
            if getattr(self, '_initialized', False):
                self.cleanup()
        except Exception:
            pass
    def _validate_init_parameters(self, pin, led_type, num_leds, color, max_brightness, min_brightness, breath_cycle, pwm_freq, debug):
        if not isinstance(pin, int) or not (self.PIN_MIN <= pin <= self.PIN_MAX):
            raise ValueError(f"引脚号必须是{self.PIN_MIN}-{self.PIN_MAX}之间的整数")
        if led_type not in [self.LED_TYPE_WS2812, self.LED_TYPE_NORMAL]:
            raise ValueError("led_type必须是'ws2812'或'normal'")
        if not isinstance(num_leds, int) or num_leds < 1:
            raise ValueError("num_leds必须是大于0的整数")
        if not isinstance(color, (tuple, list)) or len(color) != 3:
            raise ValueError("color必须是包含3个元素的元组或列表")
        for i, value in enumerate(color):
            if not isinstance(value, int) or not (0 <= value <= self.COLOR_VALUE_MAX):
                raise ValueError(f"颜色值[{i}]必须是0-{self.COLOR_VALUE_MAX}之间的整数")
        max_allowed = self.WS2812_BRIGHTNESS_MAX if led_type == self.LED_TYPE_WS2812 else self.NORMAL_LED_BRIGHTNESS_MAX
        if not isinstance(max_brightness, int) or not (0 <= max_brightness <= max_allowed):
            raise ValueError(f"最大亮度必须是0-{max_allowed}之间的整数")
        if not isinstance(min_brightness, int) or not (0 <= min_brightness <= max_allowed):
            raise ValueError(f"最小亮度必须是0-{max_allowed}之间的整数")
        if min_brightness >= max_brightness:
            raise ValueError("最小亮度必须小于最大亮度")
        if not isinstance(breath_cycle, int) or breath_cycle < self.BREATH_CYCLE_MIN:
            raise ValueError(f"呼吸周期必须是不小于{self.BREATH_CYCLE_MIN}毫秒的整数")
        if led_type == self.LED_TYPE_NORMAL:
            if not isinstance(pwm_freq, int) or not (self.PWM_FREQ_MIN <= pwm_freq <= self.PWM_FREQ_MAX):
                raise ValueError(f"PWM频率必须是{self.PWM_FREQ_MIN}-{self.PWM_FREQ_MAX}Hz之间的整数")
        if not isinstance(debug, bool):
            raise ValueError("debug参数必须是布尔值（True或False）")
    def _setup_hardware(self):
        try:
            self.led_pin = Pin(self.pin, Pin.OUT)
            if self.led_type == self.__class__.LED_TYPE_WS2812:
                self.np = neopixel.NeoPixel(self.led_pin, self.num_leds)
                self._debug_print(f"WS2812 初始化成功，{self.num_leds}个LED")
            else:
                self.pwm = PWM(self.led_pin)
                self.pwm.freq(self.pwm_freq)
                self._debug_print(f"普通LED PWM初始化成功，频率{self.pwm_freq}Hz")
        except Exception as e:
            self._debug_print(f"硬件初始化失败: {e}", "ERROR")
            raise RuntimeError(f"硬件初始化失败: {e}")
    def _clamp(self, value, min_val, max_val):
        return max(min_val, min(value, max_val))
    def _debug_print(self, message, level="INFO"):
        if self.debug_enabled:
            print(f"[BreathLED-{level}] {message}")
    def _set_remaining_updates(self, value):
        if value < 0:
            self._remaining_updates = -1
        else:
            self._remaining_updates = int(value)
    def _create_timer(self):
        try:
            timer = Timer()
            self._debug_print("使用Timer()创建定时器")
            return timer
        except Exception as e1:
            self._debug_print(f"Timer()失败: {e1}")
            try:
                timer = Timer(0)
                self._debug_print("使用Timer(0)创建定时器")
                return timer
            except Exception as e2:
                self._debug_print(f"Timer(0)失败: {e2}")
                try:
                    timer = Timer(-1)
                    self._debug_print("使用Timer(-1)创建定时器")
                    return timer
                except Exception as e3:
                    raise RuntimeError(f"无法创建Timer，请检查硬件平台支持: {e3}")
    def _calculate_brightness(self):
        if self.__class__._SINE_TABLE is None or self.__class__.SINE_PRECISION <= 0:
            self._debug_print("正弦查找表未正确初始化", "ERROR")
            return self.min_brightness
        table_index = int(self.current_angle % self.__class__._TABLE_SIZE)
        sine_value = self.__class__._SINE_TABLE[table_index] / self.__class__.SINE_PRECISION
        brightness_range = self.max_brightness - self.min_brightness
        brightness = self.min_brightness + sine_value * brightness_range
        max_allowed = self.__class__.WS2812_BRIGHTNESS_MAX if self.led_type == self.__class__.LED_TYPE_WS2812 else self.__class__.NORMAL_LED_BRIGHTNESS_MAX
        return self._clamp(int(brightness), 0, max_allowed)
    def _update_led(self, timer_obj):
        try:
            brightness = self._calculate_brightness()
            if self.led_type == self.__class__.LED_TYPE_WS2812:
                adjusted_color = tuple(
                    int(c * brightness / self.__class__.WS2812_BRIGHTNESS_MAX) for c in self.color
                )
                for i in range(self.num_leds):
                    self.np[i] = adjusted_color
                self.np.write()
            else:
                duty = int(brightness * self.__class__.PWM_DUTY_MAX / self.__class__.NORMAL_LED_BRIGHTNESS_MAX)
                duty = self._clamp(duty, 0, self.__class__.PWM_DUTY_MAX)
                self.pwm.duty_u16(duty)
            angle_step = self.__class__._TABLE_SIZE * self.update_interval / self.breath_cycle
            self.current_angle = (self.current_angle + angle_step) % self.__class__._TABLE_SIZE
        except Exception as e:
            timer_info = f"Timer: {timer_obj}" if timer_obj else "手动调用"
            self._debug_print(f"LED更新错误 ({timer_info}): {e}", "ERROR")
            if self.is_breathing:
                try:
                    self.stop()
                except:
                    pass
    def start(self):
        if self.is_breathing and self._remaining_updates == -1:
            self._debug_print("呼吸灯已在无限次数模式运行中，无需重复启动")
            return
        if self.is_breathing and self._remaining_updates > 0:
            self._debug_print(f"检测到正在执行按次呼吸(剩余{self._remaining_updates}次刷新)，切换为无限次数呼吸模式")
            self.stop()
        try:
            if self.led_type == self.__class__.LED_TYPE_WS2812 and self.np is None:
                self._debug_print("重新初始化WS2812硬件")
                self._setup_hardware()
            elif self.led_type == self.__class__.LED_TYPE_NORMAL and self.pwm is None:
                self._debug_print("重新初始化普通LED硬件")
                self._setup_hardware()
            self._set_remaining_updates(-1)
            self.timer = self._create_timer()
            self.timer.init(mode=Timer.PERIODIC, period=self.update_interval, callback=self._update_led)
            self.is_breathing = True
            self._debug_print("无限次数呼吸灯效果已启动")
        except Exception as e:
            self._debug_print(f"启动呼吸灯失败: {e}", "ERROR")
            raise
    def breath(self, cycles=1):
        def breath_callback(timer_obj):
            try:
                if self._remaining_updates > 0:
                    self._update_led(timer_obj)
                    self._set_remaining_updates(self._remaining_updates - 1)
                    if self._remaining_updates == 0:
                        self.stop()
                        self._debug_print("完成指定次数呼吸，自动停止")
            except Exception as e:
                self._debug_print(f"按次数呼吸回调错误: {e}", "ERROR")
                if self.is_breathing:
                    try:
                        self.stop()
                    except:
                        pass
        if self._remaining_updates == -1:
            self._debug_print(f"忽略breath({cycles})调用，当前处于高优先级start()启动的无限次数呼吸，请先调用stop()方法停止")
            return
        if cycles <= 0:
            self._debug_print(f"忽略breath({cycles})调用，参数必须大于0")
            return
        new_updates = int((cycles * self.breath_cycle) // self.update_interval)
        if self._remaining_updates >= 0:
            self._set_remaining_updates(self._remaining_updates + new_updates)
            self._debug_print(f"新增呼吸{cycles}次，剩余刷新次数: {self._remaining_updates}")
        if not self.is_breathing:
            if self.led_type == self.__class__.LED_TYPE_WS2812 and self.np is None:
                self._setup_hardware()
            elif self.led_type == self.__class__.LED_TYPE_NORMAL and self.pwm is None:
                self._setup_hardware()
            self.current_angle = 0
            try:
                self.timer = self._create_timer()
                self.timer.init(mode=Timer.PERIODIC, period=self.update_interval, callback=breath_callback)
                self.is_breathing = True
                self._debug_print("按次数呼吸定时器已启动")
            except Exception as e:
                self._debug_print(f"启动失败: {e}", "ERROR")
                raise
    def breath_once(self):
        self.breath(1)
    def stop(self):
        self.is_breathing = False
        self._set_remaining_updates(0)
        try:
            if self.timer:
                self.timer.deinit()
                self.timer = None
            self._turn_off_led()
            self._debug_print("呼吸灯效果已停止")
        except Exception as e:
            self._debug_print(f"停止呼吸灯时出错: {e}", "ERROR")
        gc.collect()
    def cleanup(self):
        try:
            if self.is_breathing:
                self.stop()
            if self.pwm:
                self.pwm.deinit()
                self.pwm = None
            self.np = None
            self.led_pin = None
            self._debug_print("所有资源已清理完毕")
        except Exception as e:
            self._debug_print(f"清理资源时出错: {e}", "ERROR")
    def _turn_off_led(self):
        try:
            if self.led_type == self.__class__.LED_TYPE_WS2812 and self.np:
                for i in range(self.num_leds):
                    self.np[i] = (0, 0, 0)
                self.np.write()
            elif self.pwm:
                self.pwm.duty_u16(0)
        except Exception as e:
            self._debug_print(f"关闭LED时出错: {e}", "ERROR")
    def set_color(self, color):
        if not isinstance(color, (tuple, list)) or len(color) != 3:
            raise ValueError("color必须是包含3个元素的元组或列表")
        for i, value in enumerate(color):
            if not isinstance(value, int) or not (0 <= value <= self.__class__.COLOR_VALUE_MAX):
                raise ValueError(f"颜色值[{i}]必须是0-{self.__class__.COLOR_VALUE_MAX}之间的整数")
        self.color = tuple(color)
        self._debug_print(f"颜色已设置为: {self.color}")
    def set_brightness_range(self, min_brightness, max_brightness):
        max_allowed = self.__class__.WS2812_BRIGHTNESS_MAX if self.led_type == self.__class__.LED_TYPE_WS2812 else self.__class__.NORMAL_LED_BRIGHTNESS_MAX
        if not isinstance(min_brightness, int) or not (0 <= min_brightness <= max_allowed):
            raise ValueError(f"最小亮度必须是0-{max_allowed}之间的整数")
        if not isinstance(max_brightness, int) or not (0 <= max_brightness <= max_allowed):
            raise ValueError(f"最大亮度必须是0-{max_allowed}之间的整数")
        if min_brightness >= max_brightness:
            raise ValueError("最小亮度必须小于最大亮度")
        self.min_brightness = min_brightness
        self.max_brightness = max_brightness
        self._debug_print(f"亮度范围已设置为: {min_brightness}-{max_brightness}")
    def set_breath_cycle(self, breath_cycle):
        if not isinstance(breath_cycle, int) or breath_cycle < self.__class__.BREATH_CYCLE_MIN:
            raise ValueError(f"呼吸周期必须是不小于{self.__class__.BREATH_CYCLE_MIN}毫秒的整数")
        old_cycle = self.breath_cycle
        self.breath_cycle = breath_cycle
        self.update_interval = max(self.__class__.UPDATE_INTERVAL_MIN, self.breath_cycle // self.__class__.UPDATE_INTERVAL_DIVISOR)
        if self.is_breathing and old_cycle != breath_cycle:
            try:
                if self.timer:
                    self.timer.deinit()
                    self.timer.init(mode=Timer.PERIODIC, period=self.update_interval, callback=self._update_led)
                    self._debug_print(f"定时器已重新配置，新间隔: {self.update_interval}ms")
            except Exception as e:
                self._debug_print(f"重新配置定时器失败: {e}", "ERROR")
                try:
                    self.stop()
                    self.start()
                except Exception as e2:
                    self._debug_print(f"重启呼吸灯失败: {e2}", "ERROR")
                    raise
        self._debug_print(f"呼吸周期已设置为: {breath_cycle}ms")
    def get_status(self):
        return {
            'pin': self.pin,
            'led_type': self.led_type,
            'num_leds': self.num_leds,
            'color': self.color,
            'max_brightness': self.max_brightness,
            'min_brightness': self.min_brightness,
            'breath_cycle': self.breath_cycle,
            'pwm_freq': self.pwm_freq,
            'debug_enabled': self.debug_enabled,
            'is_breathing': self.is_breathing,
            'current_angle': self.current_angle,
            'update_interval': self.update_interval
        }
    def is_running(self):
        return self.is_breathing
    def get_current_brightness(self):
        return self._calculate_brightness()