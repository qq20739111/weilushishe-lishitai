"""
Watchdog.py - 看门狗管理模块
实现硬件看门狗机制，防止系统锁死

使用方法:
1. 在 boot.py 中初始化: watchdog.init()
2. 在主循环或定时任务中定期喂狗: watchdog.feed()
3. 若系统超时未喂狗，将自动重启

注意: ESP32 MicroPython 的 WDT 一旦启用就无法停止
"""

import machine
import json
import gc

class Watchdog:
    """硬件看门狗管理器"""
    
    _instance = None
    
    # 默认配置
    DEFAULT_TIMEOUT = 300  # 默认超时300秒
    MIN_TIMEOUT = 10       # 最小超时10秒
    MAX_TIMEOUT = 600      # 最大超时600秒
    
    def __new__(cls):
        """单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._wdt = None
        self._enabled = False
        self._timeout = self.DEFAULT_TIMEOUT
    
    def _load_config(self):
        """从配置文件加载看门狗设置"""
        try:
            with open('data/config.json', 'r') as f:
                config = json.load(f)
                self._enabled = config.get('watchdog_enabled', True)
                timeout = config.get('watchdog_timeout', self.DEFAULT_TIMEOUT)
                # 限制超时范围
                self._timeout = max(self.MIN_TIMEOUT, min(self.MAX_TIMEOUT, timeout))
        except Exception as e:
            print(f"[Watchdog] 配置加载失败: {e}，使用默认值")
            self._enabled = True
            self._timeout = self.DEFAULT_TIMEOUT
        gc.collect()
    
    def init(self):
        """
        初始化看门狗
        注意: WDT 一旦启用就无法停止，直到下次重启
        """
        self._load_config()
        
        if not self._enabled:
            print("[Watchdog] 看门狗已禁用（配置中 watchdog_enabled=false）")
            return False
        
        if self._wdt is not None:
            print("[Watchdog] 看门狗已经初始化")
            return True
        
        try:
            # ESP32 WDT 超时参数单位为毫秒
            self._wdt = machine.WDT(timeout=self._timeout * 1000)
            print(f"[Watchdog] 看门狗已启动，超时时间: {self._timeout}秒")
            return True
        except Exception as e:
            print(f"[Watchdog] 看门狗初始化失败: {e}")
            self._wdt = None
            return False
    
    def feed(self):
        """
        喂狗 - 重置看门狗计时器
        应在主循环或定期任务中调用
        """
        if self._wdt is not None:
            try:
                self._wdt.feed()
            except Exception:
                pass  # 喂狗失败静默处理，避免日志刷屏
    
    @property
    def is_enabled(self):
        """看门狗是否启用"""
        return self._enabled and self._wdt is not None
    
    @property
    def timeout(self):
        """获取超时时间（秒）"""
        return self._timeout


# 全局看门狗实例
watchdog = Watchdog()

# 便捷函数
def init():
    """初始化看门狗"""
    return watchdog.init()

def feed():
    """喂狗"""
    watchdog.feed()

def is_enabled():
    """检查看门狗是否启用"""
    return watchdog.is_enabled
