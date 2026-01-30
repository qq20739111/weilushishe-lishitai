# BreathLED v2.1.0

一个功能强大的MicroPython呼吸灯控制库，支持WS2812彩色LED和普通LED。

## 🚀 新版本特性 (v2.1.0)

### 相对于v2.0.0的重大升级：

- **🎯 精确次数控制**：新增`breath(cycles)`方法，支持执行指定次数的呼吸后自动停止
- **⚡ 单次呼吸快捷方法**：新增`breath_once()`方法，一键执行单次完整呼吸
- **🧮 极简算法**：基于总更新次数的精确控制，完美适配各种呼吸周期长度
- **🔄 智能优先级管理**：自动处理`start()`无限循环与`breath(cycles)`有限次数的优先级冲突
- **🎯 自动停止机制**：指定次数呼吸完成后自动停止，无需手动干预
- **📈 累加功能**：多次调用`breath(cycles)`时智能累加剩余次数

### 相对于v1.0.0的重大升级：

- **🎨 双LED类型支持**：同时支持WS2812彩色LED和普通LED
- **🔢 多LED控制**：支持控制多个WS2812 LED同步呼吸
- **⚙️ PWM控制**：普通LED使用高精度PWM控制
- **🛡️ 完整参数验证**：严格的输入验证和错误处理
- **🔧 更多配置选项**：PWM频率、调试模式等
- **📊 状态查询**：实时获取运行状态和配置信息
- **🧹 改进的资源管理**：更安全的初始化和清理机制
- **🐛 调试功能**：内置调试输出系统

## 📦 安装

将 `BreathLED.py` 文件复制到您的MicroPython项目目录中。

## 🎯 快速开始

### v2.1.0 新功能演示

```python
from BreathLED import BreathLED

# 创建WS2812呼吸灯
breath_led = BreathLED(pin=16, led_type='ws2812', debug=True)

# 🎯 新功能1：执行指定次数呼吸
breath_led.breath(3)  # 执行3次呼吸后自动停止
import time
time.sleep(10)  # 等待完成

# ⚡ 新功能2：单次呼吸快捷方法
breath_led.breath_once()  # 执行一次完整呼吸
time.sleep(4)  # 等待完成

# 🔄 新功能3：智能次数累加
breath_led.breath(2)  # 执行2次呼吸
breath_led.breath(1)  # 再累加1次，总共3次呼吸

# 清理资源
breath_led.cleanup()
```

### WS2812 彩色LED (传统方式)

```python
from BreathLED import BreathLED

# 创建WS2812呼吸灯
breath_led = BreathLED(
    pin=16,                    # GPIO引脚
    led_type='ws2812',         # LED类型
    color=(0, 127, 255),       # 蓝绿色
    max_brightness=127,        # 最大亮度
    breath_cycle=3000          # 3秒呼吸周期
)

# 开始无限循环呼吸效果
breath_led.start()

# 运行一段时间后停止
import time
time.sleep(10)
breath_led.stop()
breath_led.cleanup()
```

### 普通LED

```python
from BreathLED import BreathLED

# 创建普通LED呼吸灯
breath_led = BreathLED(
    pin=18,                    # GPIO引脚
    led_type='normal',         # LED类型
    max_brightness=512,        # 最大亮度(0-1023)
    pwm_freq=1000,            # PWM频率1kHz
    breath_cycle=2000          # 2秒呼吸周期
)

breath_led.start()
```

## 📋 完整API参考

### 构造函数参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|---------|------|
| `pin` | int | 16 | GPIO引脚号 (0-40) |
| `led_type` | str | 'ws2812' | LED类型 ('ws2812' 或 'normal') |
| `num_leds` | int | 1 | LED数量 (仅WS2812有效) |
| `color` | tuple | (0, 127, 127) | RGB颜色 (R, G, B) |
| `max_brightness` | int | 127/1023 | 最大亮度 |
| `min_brightness` | int | 0 | 最小亮度 |
| `breath_cycle` | int | 3000 | 呼吸周期(毫秒) |
| `pwm_freq` | int | 1000 | PWM频率(仅普通LED) |
| `debug` | bool | False | 调试输出开关 |

### 亮度范围

- **WS2812**: 0-255
- **普通LED**: 0-1023

### 主要方法

#### 控制方法
- `start()` - 开始无限循环呼吸效果
- `breath(cycles)` - **[v2.1.0新增]** 执行指定次数的呼吸后自动停止
- `breath_once()` - **[v2.1.0新增]** 执行一次完整呼吸的快捷方法
- `stop()` - 停止呼吸效果
- `cleanup()` - 清理所有资源

#### 配置方法
- `set_color(color)` - 设置颜色 (仅WS2812)
- `set_brightness_range(min_brightness, max_brightness)` - 设置亮度范围
- `set_breath_cycle(breath_cycle)` - 设置呼吸周期

#### 查询方法
- `is_running()` - 检查是否正在运行
- `get_status()` - 获取完整状态信息
- `get_current_brightness()` - 获取当前亮度值
- `get_current_brightness()` - 获取当前亮度值

## 🎨 使用场景示例

### v2.1.0 新功能演示

#### 1. 指示状态变化
```python
# 系统启动：快速闪烁3次
led = BreathLED(pin=16, led_type='ws2812', breath_cycle=800, debug=True)
led.breath(3)  # 执行3次呼吸后自动停止
time.sleep(3)  # 等待完成

# 连接成功：单次慢呼吸确认
led.set_breath_cycle(2000)
led.set_color((0, 255, 0))  # 绿色
led.breath_once()  # 执行一次完整呼吸
time.sleep(3)  # 等待完成

# 工作状态：持续呼吸
led.set_color((0, 127, 255))  # 蓝色
led.start()  # 开始无限循环呼吸
time.sleep(5)
led.stop()
led.cleanup()
```

#### 2. 不同呼吸周期演示
```python
cycles_demo = [
    (300, "快速呼吸"),
    (1000, "正常呼吸"), 
    (2000, "缓慢呼吸")
]

for cycle_ms, description in cycles_demo:
    print(f"{description} (周期: {cycle_ms}ms)")
    led = BreathLED(pin=16, led_type='ws2812', breath_cycle=cycle_ms, debug=True)
    led.breath(2)  # 每种模式呼吸2次
    time.sleep(cycle_ms * 2 / 1000 + 1)  # 等待完成
    led.cleanup()
```

#### 3. 优先级管理演示
```python
led = BreathLED(pin=16, led_type='ws2812', debug=True)

# 开始无限循环
led.start()

# 这个调用会被忽略（优先级低）
led.breath(3)  # 调试信息：忽略调用，当前处于高优先级无限次数呼吸

# 停止无限循环
led.stop()

# 现在可以使用有限次数呼吸
led.breath(3)  # 正常执行3次呼吸
time.sleep(10)  # 等待自动完成

led.cleanup()
```

#### 4. 次数累加功能
```python
led = BreathLED(pin=16, led_type='ws2812', debug=True)

# 连续累加呼吸次数
led.breath(2)  # 执行2次呼吸
led.breath(1)  # 再累加1次，总共3次呼吸
led.breath(2)  # 再累加2次，总共5次呼吸

# 等待所有呼吸完成
time.sleep(16)  # 5次呼吸大约需要15秒
led.cleanup()
```

### 传统功能示例

### 1. 高级WS2812示例

```python
# 高级配置的WS2812呼吸灯
led = BreathLED(

### 2. 多LED WS2812示例

```python
# 控制8个WS2812 LED同步呼吸
led_strip = BreathLED(
    pin=19,
    led_type='ws2812',
    num_leds=8,               # 8个LED
    color=(255, 0, 255),      # 紫色
    max_brightness=100,
    breath_cycle=4000
)

led_strip.start()

# 彩虹色循环
colors = [
    (255, 0, 0),    # 红
    (255, 127, 0),  # 橙
    (255, 255, 0),  # 黄
    (0, 255, 0),    # 绿
    (0, 255, 255),  # 青
    (0, 0, 255),    # 蓝
    (127, 0, 255),  # 靛
    (255, 0, 255)   # 紫
]

for color in colors:
    led_strip.set_color(color)
    time.sleep(2)

led_strip.cleanup()
```

### 3. 普通LED示例

```python
# 普通LED呼吸灯
normal_led = BreathLED(
    pin=18,
    led_type='normal',
    max_brightness=800,        # 高亮度
    min_brightness=20,         # 微亮
    breath_cycle=1500,         # 快速呼吸
    pwm_freq=2000,            # 2kHz PWM
    debug=True
)

normal_led.start()
time.sleep(5)

# 调整亮度范围
normal_led.set_brightness_range(100, 1000)
time.sleep(3)

normal_led.cleanup()
```

### 4. 动态配置示例

```python
led = BreathLED(pin=21, debug=True)

led.start()

# 实时状态查询
print(f"运行状态: {led.is_running()}")
print(f"当前亮度: {led.get_current_brightness()}")

status = led.get_status()
print("完整状态:", status)

# 动态调整
led.set_breath_cycle(1000)      # 改为1秒快速呼吸
led.set_color((255, 192, 203))  # 改为粉色
led.set_brightness_range(50, 200)  # 调整亮度范围

led.cleanup()
```

## 🔧 v2.1.0 新算法特点

### 精确次数控制算法
- **基于总更新次数**：根据呼吸周期和更新间隔精确计算总刷新次数
- **完美适配各种周期**：无论是300ms快速呼吸还是5000ms缓慢呼吸都能精确控制
- **自动停止机制**：达到指定次数后自动停止，无需额外计时

### 智能优先级管理
- **start()优先级最高**：无限循环呼吸时忽略`breath(cycles)`调用
- **次数累加功能**：多次调用`breath(cycles)`时智能累加剩余次数
- **状态自动转换**：从有限次数呼吸可以无缝切换到无限循环

### 算法优势对比

| 特性 | v2.0.0 | v2.1.0 |
|------|--------|--------|
| 呼吸控制 | 仅无限循环 | 无限循环 + 精确次数 |
| 自动停止 | 手动stop() | 自动停止 + 手动stop() |
| 次数累加 | ❌ | ✅ |
| 优先级管理 | ❌ | ✅ |
| 算法复杂度 | 简单 | 极简且智能 |

## ⚡ 性能优化

v2.1.0版本在v2.0基础上继续优化：

1. **预计算正弦查找表** - 360个预计算值，避免实时三角函数计算
2. **自适应更新间隔** - 根据呼吸周期自动调整更新频率  
3. **内存优化** - 类级别共享正弦查找表，减少内存占用
4. **16位PWM精度** - 普通LED使用高精度PWM控制
5. **优化的资源管理** - 改进的cleanup机制，防止内存泄漏
6. **🆕 极简次数控制** - v2.1.0新增：基于总更新次数的高效算法
7. **🆕 智能状态管理** - v2.1.0新增：自动优先级处理和状态转换

## 🛡️ 错误处理

v2.0版本提供完整的参数验证和错误处理：

```python
try:
    # 参数验证会在初始化时进行
    led = BreathLED(
        pin=50,                # 无效引脚 - 会抛出ValueError
        color=(300, 0, 0)      # 无效颜色值 - 会抛出ValueError
    )
except ValueError as e:
    print(f"参数错误: {e}")
except RuntimeError as e:
    print(f"硬件错误: {e}")
```

常见错误类型：
- `ValueError` - 参数超出有效范围
- `RuntimeError` - 硬件初始化失败

## 🔍 调试功能

启用调试模式查看详细运行信息：

```python
led = BreathLED(debug=True)  # 启用调试输出

# 输出示例：
# [BreathLED-INFO] WS2812 初始化成功，1个LED
# [BreathLED-INFO] 呼吸灯效果已启动
# [BreathLED-INFO] 颜色已设置为: (255, 100, 0)
```

## 🆚 版本对比

| 特性 | v1.0.0 | v2.0.0 | v2.1.0 |
|------|--------|--------|--------|
| LED类型 | 仅WS2812 | WS2812 + 普通LED | WS2812 + 普通LED |
| 多LED支持 | ❌ | ✅ | ✅ |
| PWM控制 | ❌ | ✅ | ✅ |
| 参数验证 | 基础 | 完整 | 完整 |
| 调试功能 | ❌ | ✅ | ✅ |
| 状态查询 | 基础 | 完整 | 完整 |
| 资源管理 | 基础 | 改进 | 改进 |
| 错误处理 | 基础 | 完整 | 完整 |
| **呼吸控制** | **仅无限循环** | **仅无限循环** | **🆕 无限循环 + 精确次数** |
| **自动停止** | **❌** | **❌** | **🆕 ✅** |
| **次数累加** | **❌** | **❌** | **🆕 ✅** |
| **优先级管理** | **❌** | **❌** | **🆕 ✅** |

## 🎯 适用场景

- **状态指示升级** - 使用`breath(cycles)`精确控制指示次数，如启动闪烁3次
- **定时提醒** - 单次呼吸提醒，如`breath_once()`表示消息到达
- **装饰照明** - 使用WS2812彩色LED条创建动态装饰效果
- **设备状态** - 使用普通LED作为设备状态呼吸指示灯
- **氛围灯** - 创建舒缓的呼吸氛围灯
- **原型开发** - 快速为项目添加视觉反馈
- **教学演示** - LED控制和PWM原理演示
- **🆕 精确控制场景** - 需要准确次数控制的应用

## 🔧 硬件要求

- **MicroPython开发板** (ESP32、ESP8266等)
- **WS2812 LED** 或 **普通LED**
- **适当的电阻** (普通LED需要)
- **稳定的电源** (多LED时需要)

## 📝 注意事项

1. **引脚选择** - 确保选择的GPIO引脚支持所需功能
2. **电源供应** - 多个WS2812 LED需要足够的电流供应
3. **时序要求** - WS2812对时序敏感，避免长时间中断
4. **资源释放** - 使用完毕后务必调用`cleanup()`释放资源
5. **调试模式** - 生产环境建议关闭调试输出以节省性能

## 🤝 贡献

欢迎提交Issue和Pull Request来改进这个库！

## 📄 许可证

本项目采用MIT许可证 - 详见LICENSE文件。

---

## 🌟 v2.1.0 版本总结

v2.1.0是在v2.0.0坚实基础上的重要功能升级，主要聚焦于**精确控制**和**智能管理**：

### 核心新增功能
1. **`breath(cycles)` 方法** - 革命性的精确次数控制
2. **`breath_once()` 方法** - 单次呼吸的便捷快捷方式  
3. **极简算法** - 基于总更新次数的高效控制机制
4. **智能优先级** - 自动处理无限循环与有限次数的冲突
5. **次数累加** - 多次调用自动累加剩余次数

### 应用价值
- **更精确的状态指示** - 准确控制闪烁次数传达不同信息
- **更智能的管理** - 自动处理各种使用场景的优先级
- **更简单的使用** - 单次呼吸等常用操作变得更便捷
- **完全向后兼容** - 所有v2.0.0代码无需修改即可使用

**享受您的呼吸灯项目！** ✨
