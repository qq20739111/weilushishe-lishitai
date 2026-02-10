# 认证与 Token 管理模块
# 密码哈希、Token 生成/验证、URL 解码

import json
import os
import time
import uhashlib
import ubinascii
from lib.Logger import debug, info, warn
from lib.CacheManager import cache
from lib.Settings import get_settings, DEFAULT_TOKEN_EXPIRE_DAYS
from lib.microdot import Response

# 注册运行时 Token 签名密钥（128位随机，重启后失效）
cache.register('runtime:token_secret', ctype='const',
               initial=ubinascii.hexlify(os.urandom(16)).decode('utf-8'))
info("Token签名密钥已生成（128位随机）", "Security")


def hash_password(password):
    """使用SHA256对密码进行哈希处理（带salt）"""
    if not password:
        return ''
    # 从设置中获取salt，默认为 weilu2018
    settings = get_settings()
    salt = settings.get('password_salt', 'weilu2018')
    salted_password = salt + password
    h = uhashlib.sha256(salted_password.encode('utf-8'))
    return ubinascii.hexlify(h.digest()).decode('utf-8')


def verify_password(password, hashed):
    """验证密码是否匹配哈希值（仅支持SHA256哈希）"""
    if not password or not hashed:
        return False
    # 仅支持64位SHA256哈希比较，不再兼容旧版明文密码
    if len(hashed) == 64:
        return hash_password(password) == hashed
    return False


def _get_token_expire_seconds():
    """获取Token有效期秒数（从系统设置读取）"""
    settings = get_settings()
    days = settings.get('token_expire_days', DEFAULT_TOKEN_EXPIRE_DAYS)
    return int(days) * 24 * 3600


def _get_token_secret():
    """获取Token签名密钥（运行时随机生成，与密码盐值独立，重启后失效）"""
    return cache.get_val('runtime:token_secret')


def generate_token(user_id):
    """
    生成登录Token
    返回: (token字符串, 有效期秒数)
    注: 返回有效期秒数而非时间戳，避免不同硬件时间纪元差异问题
    """
    expire_seconds = _get_token_expire_seconds()
    # 使用设备内部时间计算过期时间（用于Token签名和后端验证）
    expire_time = int(time.time()) + expire_seconds
    secret = _get_token_secret()
    # 生成签名
    sign_data = f"{user_id}:{expire_time}:{secret}"
    h = uhashlib.sha256(sign_data.encode('utf-8'))
    signature = ubinascii.hexlify(h.digest()).decode('utf-8')
    # 组装Token
    token = f"{user_id}:{expire_time}:{signature}"
    # 返回token和有效期秒数（前端用自己的时间计算过期时间点）
    return token, expire_seconds


def verify_token(token):
    """
    验证Token有效性
    返回: (是否有效, user_id或None, 错误消息)
    """
    if not token:
        return False, None, "未提供Token"
    
    try:
        parts = token.split(':')
        if len(parts) != 3:
            return False, None, "Token格式错误"
        
        user_id = int(parts[0])
        expire_time = int(parts[1])
        provided_signature = parts[2]
        
        # 检查是否过期
        current_time = int(time.time())
        if current_time > expire_time:
            return False, None, "Token已过期，请重新登录"
        
        # 验证签名
        secret = _get_token_secret()
        sign_data = f"{user_id}:{expire_time}:{secret}"
        h = uhashlib.sha256(sign_data.encode('utf-8'))
        expected_signature = ubinascii.hexlify(h.digest()).decode('utf-8')
        
        if provided_signature != expected_signature:
            return False, None, "Token签名无效"
        
        return True, user_id, None
    except Exception as e:
        debug(f"Token验证失败: {e}", "Auth")
        return False, None, "Token解析失败"


def check_token(request):
    """
    从请求中验证Token（支持Header和请求体两种方式）
    返回: (是否有效, user_id或None, 错误响应或None)
    """
    # 从Header获取
    token = request.headers.get('authorization', '').replace('Bearer ', '')
    # POST请求也尝试从body获取
    if not token and request.json:
        token = request.json.get('token', '')
    
    valid, user_id, err_msg = verify_token(token)
    if not valid:
        return False, None, Response(json.dumps({"error": err_msg}), 401, {'Content-Type': 'application/json'})
    
    return True, user_id, None


def simple_unquote(s):
    """Robust unquote for UTF-8 inputs"""
    if not isinstance(s, str): return s
    s = s.replace('+', ' ')
    if '%' not in s: return s
    try:
        res = bytearray()
        parts = s.split('%')
        res.extend(parts[0].encode('utf-8'))
        for p in parts[1:]:
            if len(p) >= 2:
                try:
                    res.append(int(p[:2], 16))
                    res.extend(p[2:].encode('utf-8'))
                except:
                    res.extend(b'%'); res.extend(p.encode('utf-8'))
            else:
                res.extend(b'%'); res.extend(p.encode('utf-8'))
        decoded = res.decode('utf-8')
        return decoded
    except Exception as e:
        warn(f"URL解码错误: {e}", "Util")
        return s
