# 系统设置管理模块
# 负责系统配置的读取、写入和缓存管理

import json
from lib.Logger import error
from lib.CacheManager import cache

# 默认Token过期天数
DEFAULT_TOKEN_EXPIRE_DAYS = 30

# 系统设置字段列表（get_settings / save_settings / backup 共用）
SETTINGS_KEYS = [
    'custom_member_fields', 'password_salt', 'points_name', 'system_name',
    'token_expire_days', 'site_open', 'allow_guest',
    'chat_enabled', 'chat_guest_max', 'chat_max_users', 'chat_cache_size'
]

# 注册设置缓存槽
cache.register('settings', ctype='value', ttl=3600, initial=None)


def invalidate_settings_cache():
    """清除设置缓存，下次get_settings()将重新从文件读取"""
    cache.invalidate('settings')


def get_settings():
    """获取系统设置，优先从内存缓存读取，缓存未命中时从文件加载"""
    cached = cache.get_val('settings')
    if cached is not None:
        return cached
    try:
        with open('data/config.json', 'r') as f:
            config = json.load(f)
            # 返回系统设置相关的键值
            result = {
                'custom_member_fields': config.get('custom_member_fields', []),
                'password_salt': config.get('password_salt', 'weilu2018'),
                'points_name': config.get('points_name', '围炉值'),
                'system_name': config.get('system_name', '围炉诗社·理事台'),
                'token_expire_days': config.get('token_expire_days', DEFAULT_TOKEN_EXPIRE_DAYS),
                'site_open': config.get('site_open', True),
                'allow_guest': config.get('allow_guest', True),
                'chat_enabled': config.get('chat_enabled', True),
                'chat_guest_max': config.get('chat_guest_max', 10),
                'chat_max_users': config.get('chat_max_users', 20),
                'chat_cache_size': config.get('chat_cache_size', 128)
            }
            cache.set_val('settings', result)
            return result
    except: 
        return {
            'custom_member_fields': [],
            'password_salt': 'weilu2018',
            'points_name': '围炉值',
            'system_name': '围炉诗社·理事台',
            'token_expire_days': DEFAULT_TOKEN_EXPIRE_DAYS,
            'site_open': True,
            'allow_guest': True,
            'chat_enabled': True,
            'chat_guest_max': 10,
            'chat_max_users': 20,
            'chat_cache_size': 128
        }
    

def save_settings(data):
    """保存系统设置到合并后的配置文件"""
    try:
        # 先读取完整的配置文件
        with open('data/config.json', 'r') as f:
            config = json.load(f)
        
        # 更新系统设置部分
        for key in SETTINGS_KEYS:
            if key in data:
                config[key] = data[key]
        
        # 保存回配置文件
        with open('data/config.json', 'w') as f:
            json.dump(config, f)
        # 清除缓存，下次读取时重新加载
        invalidate_settings_cache()
    except Exception as e:
        error(f"保存设置失败: {e}", "Settings")
