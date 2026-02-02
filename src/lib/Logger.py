"""
Logger.py - 日志级别控制模块
根据配置文件中的 debug_mode 设置控制日志输出级别

日志级别:
- DEBUG: 详细调试信息，仅在开发环境输出
- INFO: 一般运行信息，始终输出
- WARN: 警告信息，始终输出
- ERROR: 错误信息，始终输出
"""

import json
import gc

# 日志级别常量
DEBUG = 0
INFO = 1
WARN = 2
ERROR = 3

# 日志级别名称映射
LEVEL_NAMES = {
    DEBUG: 'DEBUG',
    INFO: 'INFO',
    WARN: 'WARN',
    ERROR: 'ERROR'
}

class Logger:
    """轻量级日志管理器"""
    
    _instance = None
    _debug_mode = None
    
    def __new__(cls):
        """单例模式，确保全局只有一个Logger实例"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._load_config()
    
    def _load_config(self):
        """从配置文件加载debug_mode设置"""
        try:
            with open('data/config.json', 'r') as f:
                config = json.load(f)
                Logger._debug_mode = config.get('debug_mode', False)
        except Exception:
            # 配置加载失败时默认为生产模式
            Logger._debug_mode = False
        gc.collect()
    
    def reload_config(self):
        """重新加载配置（用于运行时更新）"""
        self._load_config()
    
    @property
    def is_debug(self):
        """当前是否为调试模式"""
        return Logger._debug_mode
    
    def set_debug_mode(self, enabled):
        """动态设置调试模式"""
        Logger._debug_mode = enabled
    
    def _log(self, level, tag, message):
        """内部日志输出方法"""
        # DEBUG级别日志仅在debug_mode=True时输出
        if level == DEBUG and not Logger._debug_mode:
            return
        
        level_name = LEVEL_NAMES.get(level, 'INFO')
        if tag:
            print(f"[{level_name}][{tag}] {message}")
        else:
            print(f"[{level_name}] {message}")
    
    def debug(self, message, tag=None):
        """调试日志 - 仅开发环境输出"""
        self._log(DEBUG, tag, message)
    
    def info(self, message, tag=None):
        """信息日志 - 始终输出"""
        self._log(INFO, tag, message)
    
    def warn(self, message, tag=None):
        """警告日志 - 始终输出"""
        self._log(WARN, tag, message)
    
    def error(self, message, tag=None):
        """错误日志 - 始终输出"""
        self._log(ERROR, tag, message)


# 全局日志实例
log = Logger()

# 便捷函数，供直接导入使用
def debug(message, tag=None):
    """调试日志 - 仅开发环境输出"""
    log.debug(message, tag)

def info(message, tag=None):
    """信息日志 - 始终输出"""
    log.info(message, tag)

def warn(message, tag=None):
    """警告日志 - 始终输出"""
    log.warn(message, tag)

def error(message, tag=None):
    """错误日志 - 始终输出"""
    log.error(message, tag)

def is_debug():
    """检查是否为调试模式"""
    return log.is_debug

def set_debug_mode(enabled):
    """设置调试模式"""
    log.set_debug_mode(enabled)
