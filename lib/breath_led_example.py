"""
BreathLED v2.1.0 示例代码
演示如何使用BreathLED类控制WS2812和普通LED的呼吸灯效果

新功能亮点：
- breath(cycles) 方法：执行指定次数的呼吸后自动停止
- breath_once() 方法：执行一次呼吸的快捷方法
- 极简算法：基于总更新次数的精确控制
- 完美兼容各种呼吸周期长度
"""

from BreathLED import BreathLED
import time

def demo_basic_usage():
    """基础使用示例"""
    print("=== 基础使用示例 ===")
    
    # 创建WS2812呼吸灯实例
    led = BreathLED(pin=16, led_type='ws2812', debug=True)
    
    print("1. 单次呼吸演示")
    led.breath_once()  # 执行一次呼吸
    time.sleep(4)  # 等待完成
    
    print("\n2. 多次呼吸演示")
    led.breath(3)  # 执行3次呼吸
    time.sleep(10)  # 等待完成
    
    print("\n3. 无限循环呼吸")
    led.start()  # 开始无限循环
    time.sleep(5)  # 运行5秒
    led.stop()   # 手动停止
    
    led.cleanup()

def demo_different_cycles():
    """不同呼吸周期演示"""
    print("\n=== 不同呼吸周期演示 ===")
    
    cycles_to_test = [
        (300, "快速呼吸"),
        (1000, "正常呼吸"), 
        (2000, "缓慢呼吸")
    ]
    
    for cycle_ms, description in cycles_to_test:
        print(f"\n{description} (周期: {cycle_ms}ms)")
        led = BreathLED(pin=16, led_type='ws2812', breath_cycle=cycle_ms, debug=True)
        
        print(f"执行2次呼吸...")
        led.breath(2)
        time.sleep((cycle_ms * 2 / 1000) + 1)  # 等待完成
        
        led.cleanup()

def demo_color_brightness():
    """颜色和亮度演示"""
    print("\n=== 颜色和亮度演示 ===")
    
    # 不同颜色配置
    colors = [
        ((255, 0, 0), "红色"),
        ((0, 255, 0), "绿色"),
        ((0, 0, 255), "蓝色"),
        ((255, 255, 0), "黄色"),
        ((255, 0, 255), "紫色"),
        ((0, 255, 255), "青色")
    ]
    
    for color, name in colors:
        print(f"\n{name}呼吸演示")
        led = BreathLED(
            pin=16, 
            led_type='ws2812',
            color=color,
            max_brightness=100,  # 适中亮度
            breath_cycle=800,    # 较快周期
            debug=True
        )
        
        led.breath_once()
        time.sleep(1.5)
        led.cleanup()

def demo_normal_led():
    """普通LED演示"""
    print("\n=== 普通LED演示 ===")
    
    # 创建普通LED实例
    led = BreathLED(
        pin=18,  # 使用不同引脚
        led_type='normal',
        max_brightness=800,  # 普通LED较高亮度
        breath_cycle=1500,
        debug=True
    )
    
    print("普通LED呼吸演示 (3次)")
    led.breath(3)
    time.sleep(5)
    
    led.cleanup()

def demo_timing_precision():
    """时间精度演示"""
    print("\n=== 时间精度演示 ===")
    
    led = BreathLED(pin=16, led_type='ws2812', breath_cycle=1000, debug=True)
    
    test_cases = [1, 2, 5, 10]
    
    for cycles in test_cases:
        print(f"\n测试 {cycles} 次呼吸的时间精度")
        expected_time = cycles * 1.0  # 每次1秒
        
        start_time = time.time()
        led.breath(cycles)
        
        # 等待完成 (预期时间 + 20%余量)
        wait_time = expected_time * 1.2
        time.sleep(wait_time)
        
        actual_time = time.time() - start_time
        print(f"预期时间: {expected_time:.1f}s, 实际时间: {actual_time:.1f}s")
        print(f"状态: {'✓ 已停止' if not led.is_running() else '✗ 仍在运行'}")
    
    led.cleanup()

def demo_advanced_features():
    """高级功能演示"""
    print("\n=== 高级功能演示 ===")
    
    led = BreathLED(pin=16, led_type='ws2812', debug=True)
    
    print("1. 动态修改颜色")
    led.set_color((255, 100, 0))  # 橙色
    led.breath_once()
    time.sleep(2)
    
    print("2. 动态修改亮度范围")
    led.set_brightness_range(10, 255)  # 更大亮度范围
    led.breath_once()
    time.sleep(2)
    
    print("3. 动态修改呼吸周期")
    led.set_breath_cycle(500)  # 改为快速呼吸
    led.breath(2)
    time.sleep(2)
    
    print("4. 状态查询")
    status = led.get_status()
    print(f"当前配置: 周期={status['breath_cycle']}ms, 颜色={status['color']}")
    print(f"运行状态: {led.is_running()}")
    print(f"当前亮度: {led.get_current_brightness()}")
    
    led.cleanup()

def main():
    """主演示函数"""
    print("BreathLED v2.1.0 完整功能演示")
    print("=" * 50)
    
    try:
        # 基础使用
        demo_basic_usage()
        
        # 不同周期
        demo_different_cycles()
        
        # 颜色亮度
        demo_color_brightness()
        
        # 普通LED
        demo_normal_led()
        
        # 时间精度
        demo_timing_precision()
        
        # 高级功能
        demo_advanced_features()
        
        print("\n" + "=" * 50)
        print("所有演示完成！")
        print("\n主要改进:")
        print("✓ breath(cycles) - 精确次数控制")
        print("✓ breath_once() - 单次呼吸快捷方法") 
        print("✓ 极简算法 - 基于总更新次数控制")
        print("✓ 完美适配各种周期长度")
        print("✓ 自动停止 - 无需手动干预")
        
    except Exception as e:
        print(f"演示过程中出错: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
