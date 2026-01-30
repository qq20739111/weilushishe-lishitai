"""
BreathLED - LED呼吸效果控制类
v2.1.0
"""

from machine import Pin, Timer, PWM
import math
import gc
import neopixel

class BreathLED:
    """
    BreathLED类 - 用于控制WS2812或普通LED呼吸灯效果
    提供参数验证、动态颜色和亮度调整、呼吸周期设置等功能。
    支持在MicroPython环境中使用。
    
    支持两种LED类型：
    - WS2812彩色LED (led_type='ws2812')
    - 普通LED (led_type='normal')
    
    Attributes:
        LED_TYPE_WS2812 (str): WS2812彩色LED类型标识
        LED_TYPE_NORMAL (str): 普通LED类型标识
        WS2812_BRIGHTNESS_MAX (int): WS2812最大亮度值
        NORMAL_LED_BRIGHTNESS_MAX (int): 普通LED最大亮度值
    """
    
    # =============================================================================
    # 类常量定义 (按功能分组)
    # =============================================================================
    
    # 正弦查找表
    _SINE_TABLE = None
    _TABLE_SIZE = 360
    
    # LED类型常量
    LED_TYPE_WS2812 = 'ws2812'    # WS2812彩色LED
    LED_TYPE_NORMAL = 'normal'    # 普通LED
    
    # 硬件限制常量
    PIN_MIN = 0                   # GPIO引脚最小值
    PIN_MAX = 40                  # GPIO引脚最大值
    PWM_FREQ_MIN = 1              # PWM最小频率
    PWM_FREQ_MAX = 40000          # PWM最大频率
    BREATH_CYCLE_MIN = 100        # 最小呼吸周期(毫秒)
    
    # 亮度和颜色常量
    WS2812_BRIGHTNESS_MAX = 255   # WS2812最大亮度
    NORMAL_LED_BRIGHTNESS_MAX = 1023  # 普通LED最大亮度
    COLOR_VALUE_MAX = 255         # RGB颜色值最大值
    PWM_DUTY_MAX = 65535          # PWM占空比最大值
    
    # 算法参数常量
    SINE_PRECISION = 1000         # 正弦表精度倍数
    UPDATE_INTERVAL_MIN = 10      # 最小更新间隔(毫秒)
    UPDATE_INTERVAL_DIVISOR = 200 # 更新间隔计算除数
    
    # 默认值常量
    DEFAULT_PIN = 16              # 默认GPIO引脚
    DEFAULT_COLOR = (0, 127, 127) # 默认颜色(青色)
    DEFAULT_MAX_BRIGHTNESS_WS2812 = 127  # WS2812默认最大亮度
    DEFAULT_MIN_BRIGHTNESS = 0    # 默认最小亮度
    DEFAULT_BREATH_CYCLE = 3000   # 默认呼吸周期(毫秒)
    DEFAULT_PWM_FREQ = 1000       # 默认PWM频率
    DEFAULT_DEBUG = False          # 默认调试开关

    # =============================================================================
    # 类方法
    # =============================================================================
    
    @classmethod
    def _init_sine_table(cls):
        """初始化正弦查找表，用于平滑的呼吸效果计算"""
        if cls._SINE_TABLE is None:
            # 使用简单的锁机制防止多实例同时初始化
            try:
                # 双重检查锁定模式
                if cls._SINE_TABLE is None:
                    cls._SINE_TABLE = []
                    for i in range(cls._TABLE_SIZE):
                        # 将0-360度映射到0-1的正弦值
                        radians = i * 2 * math.pi / cls._TABLE_SIZE
                        sine_value = (math.sin(radians - math.pi/2) + 1) / 2
                        cls._SINE_TABLE.append(int(sine_value * cls.SINE_PRECISION))
            except Exception:
                # 如果初始化失败，重置为None以便下次重试
                cls._SINE_TABLE = None
                raise
    
    # =============================================================================
    # 构造和析构方法
    # =============================================================================
    
    def __init__(self, pin=None, led_type=None, num_leds=None, color=None, max_brightness=None, min_brightness=None, breath_cycle=None, pwm_freq=None, debug=None):
        """
        初始化BreathLED对象
        
        Args:
            pin (int): GPIO引脚编号 (0-40，具体范围依据开发板型号)
            led_type (str): LED类型 ('ws2812' 或 'normal')
            num_leds (int): LED数量，仅对WS2812有效
            color (tuple): RGB颜色元组 (R, G, B)，每个值0-255
            max_brightness (int): 最大亮度，WS2812: 0-255, 普通LED: 0-1023
            min_brightness (int): 最小亮度，WS2812: 0-255, 普通LED: 0-1023
            breath_cycle (int): 呼吸周期，毫秒
            pwm_freq (int): PWM频率，仅对普通LED有效
            debug (bool): 是否启用调试输出，默认False
            
        Raises:
            ValueError: 当参数不在有效范围内时
        """
        # 1. 首先处理默认值（不设置为实例属性，仅用于验证）
        resolved_pin = pin if pin is not None else self.DEFAULT_PIN
        resolved_led_type = led_type if led_type is not None else self.LED_TYPE_WS2812
        resolved_num_leds = num_leds if num_leds is not None else 1
        resolved_color = color if color is not None else self.DEFAULT_COLOR
        resolved_min_brightness = min_brightness if min_brightness is not None else self.DEFAULT_MIN_BRIGHTNESS
        resolved_breath_cycle = breath_cycle if breath_cycle is not None else self.DEFAULT_BREATH_CYCLE
        resolved_pwm_freq = pwm_freq if pwm_freq is not None else self.DEFAULT_PWM_FREQ
        resolved_debug = debug if debug is not None else self.DEFAULT_DEBUG

        # 根据LED类型设置默认最大亮度
        if max_brightness is not None:
            resolved_max_brightness = max_brightness
        else:
            if resolved_led_type == self.LED_TYPE_WS2812:
                resolved_max_brightness = self.DEFAULT_MAX_BRIGHTNESS_WS2812
            else:
                resolved_max_brightness = self.NORMAL_LED_BRIGHTNESS_MAX
        
        # 2. 验证所有参数（在设置实例属性之前）
        self._validate_init_parameters(
            resolved_pin, resolved_led_type, resolved_num_leds, resolved_color,
            resolved_max_brightness, resolved_min_brightness, resolved_breath_cycle, resolved_pwm_freq, resolved_debug
        )
        
        # 3. 参数验证通过后，设置实例属性
        self.pin = resolved_pin
        self.led_type = resolved_led_type
        self.num_leds = resolved_num_leds
        self.color = resolved_color
        self.max_brightness = resolved_max_brightness
        self.min_brightness = resolved_min_brightness
        self.breath_cycle = resolved_breath_cycle
        self.pwm_freq = resolved_pwm_freq
        self.debug_enabled = resolved_debug  # 调试输出开关，从构造函数参数获取
        
        # 4. 初始化状态变量（在参数验证通过后）
        self._initialized = False  # 初始化状态标志
        self.current_angle = 0
        self.is_breathing = False
        self.timer = None
        self.led_pin = None
        self.np = None  # NeoPixel对象
        self.pwm = None  # PWM对象
        self._remaining_updates = 0  # 剩余LED刷新次数，-1表示无限次数
        
        # 5. 计算更新间隔（以毫秒为单位）
        self.update_interval = max(self.UPDATE_INTERVAL_MIN, self.breath_cycle // self.UPDATE_INTERVAL_DIVISOR)
        
        # 6. 初始化硬件（延迟初始化以避免Timer资源冲突）
        self._setup_hardware()
        
        # 7. 初始化正弦查找表
        self._init_sine_table()
        
        # 8. 标记初始化完成
        self._initialized = True
    
    def __del__(self):
        """析构函数，确保资源被正确释放"""
        # 安全检查：只有当对象完全初始化后才执行清理
        try:
            if getattr(self, '_initialized', False):
                self.cleanup()  # 使用cleanup方法完全清理资源
        except Exception:
            # 析构函数中忽略所有异常，避免影响程序退出
            pass
    
    # =============================================================================
    # 私有方法 (参数验证和硬件设置)
    # =============================================================================
    
    def _validate_init_parameters(self, pin, led_type, num_leds, color, max_brightness, min_brightness, breath_cycle, pwm_freq, debug):
        """验证初始化参数（在设置实例属性之前调用）"""
        # 验证引脚号
        if not isinstance(pin, int) or not (self.PIN_MIN <= pin <= self.PIN_MAX):
            raise ValueError(f"引脚号必须是{self.PIN_MIN}-{self.PIN_MAX}之间的整数")
        
        # 验证LED类型
        if led_type not in [self.LED_TYPE_WS2812, self.LED_TYPE_NORMAL]:
            raise ValueError("led_type必须是'ws2812'或'normal'")

        # 验证num_leds参数
        if not isinstance(num_leds, int) or num_leds < 1:
            raise ValueError("num_leds必须是大于0的整数")

        # 验证颜色值
        if not isinstance(color, (tuple, list)) or len(color) != 3:
            raise ValueError("color必须是包含3个元素的元组或列表")
        for i, value in enumerate(color):
            if not isinstance(value, int) or not (0 <= value <= self.COLOR_VALUE_MAX):
                raise ValueError(f"颜色值[{i}]必须是0-{self.COLOR_VALUE_MAX}之间的整数")
        
        # 验证亮度值（根据LED类型）
        max_allowed = self.WS2812_BRIGHTNESS_MAX if led_type == self.LED_TYPE_WS2812 else self.NORMAL_LED_BRIGHTNESS_MAX
        
        if not isinstance(max_brightness, int) or not (0 <= max_brightness <= max_allowed):
            raise ValueError(f"最大亮度必须是0-{max_allowed}之间的整数")
        if not isinstance(min_brightness, int) or not (0 <= min_brightness <= max_allowed):
            raise ValueError(f"最小亮度必须是0-{max_allowed}之间的整数")
        if min_brightness >= max_brightness:
            raise ValueError("最小亮度必须小于最大亮度")
        
        # 验证呼吸周期
        if not isinstance(breath_cycle, int) or breath_cycle < self.BREATH_CYCLE_MIN:
            raise ValueError(f"呼吸周期必须是不小于{self.BREATH_CYCLE_MIN}毫秒的整数")
        
        # 验证PWM频率（仅对普通LED）
        if led_type == self.LED_TYPE_NORMAL:
            if not isinstance(pwm_freq, int) or not (self.PWM_FREQ_MIN <= pwm_freq <= self.PWM_FREQ_MAX):
                raise ValueError(f"PWM频率必须是{self.PWM_FREQ_MIN}-{self.PWM_FREQ_MAX}Hz之间的整数")
        
        # 验证调试参数
        if not isinstance(debug, bool):
            raise ValueError("debug参数必须是布尔值（True或False）")
    
    def _setup_hardware(self):
        """初始化硬件：LED引脚和NeoPixel/PWM对象"""
        try:
            self.led_pin = Pin(self.pin, Pin.OUT)
            
            if self.led_type == self.__class__.LED_TYPE_WS2812:
                self.np = neopixel.NeoPixel(self.led_pin, self.num_leds)
                self._debug_print(f"WS2812 初始化成功，{self.num_leds}个LED")
            else:  # normal LED
                self.pwm = PWM(self.led_pin)
                self.pwm.freq(self.pwm_freq)
                self._debug_print(f"普通LED PWM初始化成功，频率{self.pwm_freq}Hz")
                
        except Exception as e:
            self._debug_print(f"硬件初始化失败: {e}", "ERROR")
            raise RuntimeError(f"硬件初始化失败: {e}")
    
    def _clamp(self, value, min_val, max_val):
        """限制数值在指定范围内"""
        return max(min_val, min(value, max_val))
    
    def _debug_print(self, message, level="INFO"):
        """统一的调试输出方法"""
        if self.debug_enabled:
            print(f"[BreathLED-{level}] {message}")
    
    def _set_remaining_updates(self, value):
        """安全设置剩余刷新次数，确保类型为整数"""
        if value < 0:
            self._remaining_updates = -1  # 无限次数标记
        else:
            self._remaining_updates = int(value)  # 确保为整数
    
    def _create_timer(self):
        """创建Timer对象，兼容不同的硬件平台（特别是RP2040和ESP32）"""
        try:
            # 首先尝试使用Timer()，不指定Timer ID，让系统自动分配，这在RP2040上通常可用
            timer = Timer()
            self._debug_print("使用Timer()创建定时器")
            return timer
        except Exception as e1:  # 捕获所有异常类型，包括TypeError、RuntimeError等
            self._debug_print(f"Timer()失败: {e1}")
            try:
                # 如果Timer()失败，尝试Timer(0)，ESP32上通常可用
                timer = Timer(0)
                self._debug_print("使用Timer(0)创建定时器")
                return timer
            except Exception as e2:  # 同样捕获所有异常类型
                self._debug_print(f"Timer(0)失败: {e2}")
                try:
                    # 如果都失败，尝试使用Timer(-1)，让系统分配虚拟定时器
                    timer = Timer(-1)
                    self._debug_print("使用Timer(-1)创建定时器")
                    return timer
                except Exception as e3:
                    raise RuntimeError(f"无法创建Timer，请检查硬件平台支持: {e3}")
    
    def _calculate_brightness(self):
        """根据当前角度计算亮度值"""
        # 安全检查：确保正弦查找表已初始化
        if self.__class__._SINE_TABLE is None or self.__class__.SINE_PRECISION <= 0:
            self._debug_print("正弦查找表未正确初始化", "ERROR")
            return self.min_brightness
            
        # 使用查找表获取正弦值
        table_index = int(self.current_angle % self.__class__._TABLE_SIZE)
        sine_value = self.__class__._SINE_TABLE[table_index] / self.__class__.SINE_PRECISION
        
        # 映射到亮度范围
        brightness_range = self.max_brightness - self.min_brightness
        brightness = self.min_brightness + sine_value * brightness_range
        
        # 确保亮度在有效范围内
        max_allowed = self.__class__.WS2812_BRIGHTNESS_MAX if self.led_type == self.__class__.LED_TYPE_WS2812 else self.__class__.NORMAL_LED_BRIGHTNESS_MAX
        return self._clamp(int(brightness), 0, max_allowed)
    
    def _update_led(self, timer_obj):
        """定时器回调函数，更新LED亮度"""
        try:
            brightness = self._calculate_brightness()
            
            if self.led_type == self.__class__.LED_TYPE_WS2812:
                # WS2812: 根据亮度调整颜色
                adjusted_color = tuple(
                    int(c * brightness / self.__class__.WS2812_BRIGHTNESS_MAX) for c in self.color
                )
                for i in range(self.num_leds):
                    self.np[i] = adjusted_color
                self.np.write()
                
            else:  # normal LED
                # 普通LED: 直接设置PWM占空比
                duty = int(brightness * self.__class__.PWM_DUTY_MAX / self.__class__.NORMAL_LED_BRIGHTNESS_MAX)
                duty = self._clamp(duty, 0, self.__class__.PWM_DUTY_MAX)
                self.pwm.duty_u16(duty)
            
            # 更新角度（360度对应一个完整的呼吸周期）
            angle_step = self.__class__._TABLE_SIZE * self.update_interval / self.breath_cycle
            self.current_angle = (self.current_angle + angle_step) % self.__class__._TABLE_SIZE
            
        except Exception as e:
            # 可以利用timer_obj参数进行调试
            timer_info = f"Timer: {timer_obj}" if timer_obj else "手动调用"
            self._debug_print(f"LED更新错误 ({timer_info}): {e}", "ERROR")
            # 发生错误时停止呼吸灯以避免持续错误
            if self.is_breathing:
                try:
                    self.stop()
                except:
                    # 忽略停止过程中的异常，避免递归错误
                    pass
    
    # =============================================================================
    # 公共控制方法
    # =============================================================================
    
    def start(self):
        """
        开始呼吸灯效果（无限次数）
        - 优先级高于breath()
        """
        # 如果当前已经是start()启动的无限次数呼吸，无需重复启动
        if self.is_breathing and self._remaining_updates == -1:
            self._debug_print("呼吸灯已在无限次数模式运行中，无需重复启动")
            return
        
        # 如果当前正在执行breath()的按次呼吸，则停止后重新启动为无限次数呼吸
        if self.is_breathing and self._remaining_updates > 0:
            self._debug_print(f"检测到正在执行按次呼吸(剩余{self._remaining_updates}次刷新)，切换为无限次数呼吸模式")
            self.stop()  # 利用现有的stop()方法清理状态
        
        try:
            # 检查硬件是否正确初始化，如果没有则重新初始化
            if self.led_type == self.__class__.LED_TYPE_WS2812 and self.np is None:
                self._debug_print("重新初始化WS2812硬件")
                self._setup_hardware()
            elif self.led_type == self.__class__.LED_TYPE_NORMAL and self.pwm is None:
                self._debug_print("重新初始化普通LED硬件")
                self._setup_hardware()
            
            # 设置为无限次数模式
            self._set_remaining_updates(-1)
            
            # 创建定时器 - 兼容RP2040 和 ESP32
            self.timer = self._create_timer()
            self.timer.init(mode=Timer.PERIODIC, period=self.update_interval, callback=self._update_led)
            self.is_breathing = True
            self._debug_print("无限次数呼吸灯效果已启动")
            
        except Exception as e:
            self._debug_print(f"启动呼吸灯失败: {e}", "ERROR")
            raise
    
    def breath(self, cycles=1):
        """
        执行指定次数的呼吸灯效果，智能处理与start()的优先级关系
        
        Args:
            cycles (int): 呼吸次数，默认为1次。小于等于0时直接忽略
        
        优先级规则：
        - 如果当前处于start()启动的无限次数呼吸(_remaining_updates == -1)，则忽略breath()调用
        - 如果当前处于breath()启动的按次数呼吸(_remaining_updates > 0)，则累加次数
        - 如果当前未在呼吸，则启动按次数呼吸
        """
        def breath_callback(timer_obj):
            """按次数呼吸的专用回调函数 - 封装按次数控制逻辑"""
            try:
                # 检查按次数呼吸是否完成
                if self._remaining_updates > 0:
                    # 刷新LED
                    self._update_led(timer_obj)
                    self._set_remaining_updates(self._remaining_updates - 1)
                    if self._remaining_updates == 0:
                        # 呼吸次数完成，停止
                        self.stop()
                        self._debug_print("完成指定次数呼吸，自动停止")
            except Exception as e:
                # 回调函数异常处理
                self._debug_print(f"按次数呼吸回调错误: {e}", "ERROR")
                if self.is_breathing:
                    try:
                        self.stop()
                    except:
                        pass

        # 如果当前在无限次数呼吸（start()启动的），忽略新调用
        if self._remaining_updates == -1:
            self._debug_print(f"忽略breath({cycles})调用，当前处于高优先级start()启动的无限次数呼吸，请先调用stop()方法停止")
            return
        
        # cycles小于等于0时直接忽略
        if cycles <= 0:
            self._debug_print(f"忽略breath({cycles})调用，参数必须大于0")
            return
        
        # 计算新的刷新次数，确保结果为整数
        new_updates = int((cycles * self.breath_cycle) // self.update_interval)
        
        # 如果当前在按次数呼吸，累加剩余次数
        if self._remaining_updates >= 0:
            self._set_remaining_updates(self._remaining_updates + new_updates)
            self._debug_print(f"新增呼吸{cycles}次，剩余刷新次数: {self._remaining_updates}")
        
        # 如果当前未在呼吸，启动呼吸灯
        if not self.is_breathing:
            # 确保硬件已初始化
            if self.led_type == self.__class__.LED_TYPE_WS2812 and self.np is None:
                self._setup_hardware()
            elif self.led_type == self.__class__.LED_TYPE_NORMAL and self.pwm is None:
                self._setup_hardware()
            
            # 初始化角度
            self.current_angle = 0
            
            try:
                # 启动呼吸定时器，使用专用的按次数回调函数
                self.timer = self._create_timer()
                self.timer.init(mode=Timer.PERIODIC, period=self.update_interval, callback=breath_callback)
                self.is_breathing = True
                self._debug_print("按次数呼吸定时器已启动")
            except Exception as e:
                self._debug_print(f"启动失败: {e}", "ERROR")
                raise

    def breath_once(self):
        """
        执行一次完整的呼吸灯效果（从最暗到最亮再到最暗）
        这是breath(1)的快捷方法
        """
        self.breath(1)

    def stop(self):
        """停止呼吸灯效果并清理资源"""
        self.is_breathing = False
        self._set_remaining_updates(0)  # 重置剩余刷新次数
        
        try:
            # 停止定时器
            if self.timer:
                self.timer.deinit()
                self.timer = None
            
            # 关闭LED
            self._turn_off_led()
            
            self._debug_print("呼吸灯效果已停止")
            
        except Exception as e:
            self._debug_print(f"停止呼吸灯时出错: {e}", "ERROR")
        
        # 强制垃圾回收
        gc.collect()
    
    def cleanup(self):
        """完全清理资源，包括硬件对象"""
        try:
            # 先停止呼吸灯
            if self.is_breathing:
                self.stop()
            
            # 清理PWM资源
            if self.pwm:
                self.pwm.deinit()
                self.pwm = None
            
            # 清理NeoPixel对象
            self.np = None
            self.led_pin = None
            
            self._debug_print("所有资源已清理完毕")
            
        except Exception as e:
            self._debug_print(f"清理资源时出错: {e}", "ERROR")

    def _turn_off_led(self):
        """关闭LED"""
        try:
            if self.led_type == self.__class__.LED_TYPE_WS2812 and self.np:
                for i in range(self.num_leds):
                    self.np[i] = (0, 0, 0)
                self.np.write()
            elif self.pwm:
                self.pwm.duty_u16(0)
        except Exception as e:
            self._debug_print(f"关闭LED时出错: {e}", "ERROR")
    
    # =============================================================================
    # 公共配置方法
    # =============================================================================
    
    def set_color(self, color):
        """
        动态设置颜色（仅对WS2812有效）
        
        Args:
            color (tuple): RGB颜色元组 (R, G, B)，每个值0-255
        """
        if not isinstance(color, (tuple, list)) or len(color) != 3:
            raise ValueError("color必须是包含3个元素的元组或列表")
        
        for i, value in enumerate(color):
            if not isinstance(value, int) or not (0 <= value <= self.__class__.COLOR_VALUE_MAX):
                raise ValueError(f"颜色值[{i}]必须是0-{self.__class__.COLOR_VALUE_MAX}之间的整数")
        
        self.color = tuple(color)  # 确保存储为元组
        self._debug_print(f"颜色已设置为: {self.color}")
    
    def set_brightness_range(self, min_brightness, max_brightness):
        """
        动态设置亮度范围
        
        Args:
            min_brightness (int): 最小亮度
            max_brightness (int): 最大亮度
        """
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
        """
        动态设置呼吸周期
        
        Args:
            breath_cycle (int): 呼吸周期，毫秒
        """
        if not isinstance(breath_cycle, int) or breath_cycle < self.__class__.BREATH_CYCLE_MIN:
            raise ValueError(f"呼吸周期必须是不小于{self.__class__.BREATH_CYCLE_MIN}毫秒的整数")
        
        old_cycle = self.breath_cycle
        self.breath_cycle = breath_cycle
        self.update_interval = max(self.__class__.UPDATE_INTERVAL_MIN, self.breath_cycle // self.__class__.UPDATE_INTERVAL_DIVISOR)
        
        # 如果正在运行且周期有变化，重新配置定时器
        if self.is_breathing and old_cycle != breath_cycle:
            try:
                # 只重新配置定时器，不销毁硬件对象
                if self.timer:
                    self.timer.deinit()
                    self.timer.init(mode=Timer.PERIODIC, period=self.update_interval, callback=self._update_led)
                    self._debug_print(f"定时器已重新配置，新间隔: {self.update_interval}ms")
            except Exception as e:
                self._debug_print(f"重新配置定时器失败: {e}", "ERROR")
                # 如果重新配置失败，尝试完全重启
                try:
                    self.stop()
                    self.start()
                except Exception as e2:
                    self._debug_print(f"重启呼吸灯失败: {e2}", "ERROR")
                    raise
        
        self._debug_print(f"呼吸周期已设置为: {breath_cycle}ms")
    
    # =============================================================================
    # 状态查询方法
    # =============================================================================
    
    def get_status(self):
        """
        获取当前状态信息
        
        Returns:
            dict: 包含当前配置和状态的字典
        """
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
        """
        检查呼吸灯是否正在运行
        
        Returns:
            bool: True表示正在运行，False表示已停止
        """
        return self.is_breathing
    
    def get_current_brightness(self):
        """
        获取当前亮度值
        
        Returns:
            int: 当前亮度值
        """
        return self._calculate_brightness()