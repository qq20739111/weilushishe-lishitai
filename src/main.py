import sys

try:
    import json
    import os
    import gc
    import network
    import time
    import machine
    import uhashlib
    import ubinascii
    from lib.microdot import Microdot, Response, send_file
    from lib.Logger import log, debug, info, warn, error
    from lib.Watchdog import watchdog
    from lib.SystemStatus import status_led
    info("main.py 模块导入成功", "Init")
except ImportError as e:
    print(f"\n[CRITICAL] 导入失败: {e}")
    sys.exit()

# 记录系统启动时间（用于计算uptime）
_system_start_time = time.time()

# 运行时Token签名密钥（每次启动随机生成128位，与密码盐值完全独立）
_RUNTIME_TOKEN_SECRET = ubinascii.hexlify(os.urandom(16)).decode('utf-8')
info("Token签名密钥已生成（128位随机）", "Security")

# 看门狗定时喂狗器（防止空闲超时）
_watchdog_timer = None

def _watchdog_timer_callback(timer):
    """定时器回调：周期性喂狗"""
    watchdog.feed()

def stop_watchdog_timer():
    """停止看门狗定时喂狗器"""
    global _watchdog_timer
    if _watchdog_timer is not None:
        _watchdog_timer.deinit()
        _watchdog_timer = None
        info("看门狗定时喂狗器已停止", "Watchdog")

def start_watchdog_timer():
    """启动看门狗定时喂狗器"""
    global _watchdog_timer
    if _watchdog_timer is None and watchdog.is_enabled:
        # 使用 Timer(1) 避免与 LED 呼吸效果的定时器冲突（LED使用Timer(0)或虚拟定时器）
        _watchdog_timer = machine.Timer(1)
        # 每30秒喂一次狗（超时120秒的1/4，留足安全裕度）
        _watchdog_timer.init(period=30000, mode=machine.Timer.PERIODIC, callback=_watchdog_timer_callback)
        info("看门狗定时喂狗器已启动（周期30秒）", "Watchdog")

app = Microdot()

# 维护模式白名单（这些接口即使在维护模式下也可访问）
MAINTENANCE_WHITELIST = [
    '/api/login',
    '/api/settings/system',
]

# 公开数据白名单（allow_guest=false时，这些GET接口仍可访问，因为前端已处理登录跳转）
PUBLIC_DATA_WHITELIST = [
    '/api/poems',
    '/api/poems/random',
    '/api/activities',
    '/api/members',
    '/api/chat/messages',
    '/api/chat/users',
    '/api/chat/status',
    '/api/points/yearly_ranking',
]

def api_route(url, methods=['GET']):
    """
    API路由装饰器，包装原生route装饰器
    在API请求处理完成后自动触发LED快闪和看门狗喂狗
    支持路径参数（如 /api/backup/table/<table>）
    包含维护模式检查和游客访问控制
    """
    def decorator(f):
        def wrapper(request, *args, **kwargs):
            watchdog.feed()  # 每次API请求时喂狗
            
            # 维护模式和游客访问检查（白名单接口除外）
            if url not in MAINTENANCE_WHITELIST:
                s = get_settings()
                user_id, role = get_operator_role(request)
                
                # 维护模式检查
                if s.get('maintenance_mode', False):
                    if role not in ['super_admin', 'admin']:
                        from lib.microdot import Response
                        return Response('{"error": "系统维护中，请稍后再试"}', 503, {'Content-Type': 'application/json'})
                
                # 游客访问控制（未登录用户）
                # 公开数据接口的GET请求允许访问（前端已处理登录跳转）
                is_get_request = request.method == 'GET'
                is_public_data = url in PUBLIC_DATA_WHITELIST
                if not s.get('allow_guest', True) and not user_id:
                    if not (is_get_request and is_public_data):
                        from lib.microdot import Response
                        return Response('{"error": "请先登录后访问"}', 401, {'Content-Type': 'application/json'})
            
            result = f(request, *args, **kwargs)
            status_led.flash_once()  # API响应后LED快闪
            return result
        # 注册到microdot路由
        app.routes.append((url, methods, wrapper))
        return wrapper
    return decorator

def file_exists(path):
    try:
        os.stat(path)
        return True
    except OSError:
        return False

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
    """验证密码是否匹配哈希值，同时支持旧版明文密码兼容"""
    if not password or not hashed:
        return False
    # 如果存储的是64位哈希值，则进行哈希比较
    if len(hashed) == 64:
        return hash_password(password) == hashed
    # 否则为旧版明文密码，直接比较
    return password == hashed

# ============================================================================
# 数据验证函数
# ============================================================================

def validate_phone(phone):
    """
    验证手机号格式
    规则: 11位数字，以1开头，第二位为3-9
    返回: (valid: bool, error: str|None)
    """
    if not phone:
        return False, '手机号为必填项'
    if not isinstance(phone, str):
        phone = str(phone)
    # 简化正则：11位数字，1开头，第二位3-9
    if len(phone) != 11:
        return False, '请输入有效的手机号码（11位）'
    if phone[0] != '1' or phone[1] not in '3456789':
        return False, '请输入有效的手机号码'
    for c in phone:
        if c not in '0123456789':
            return False, '请输入有效的手机号码'
    return True, None

def validate_password_strength(password):
    """
    验证密码强度
    规则: 至少6位，包含至少两种字符类型（数字、小写字母、大写字母、特殊字符）
    返回: (valid: bool, error: str|None)
    """
    if not password:
        return False, '密码为必填项'
    if len(password) < 6:
        return False, '密码长度至少6位'
    if len(password) > 32:
        return False, '密码长度不能超过32位'
    
    # 检查字符类型
    type_count = 0
    has_digit = False
    has_lower = False
    has_upper = False
    has_special = False
    
    for c in password:
        if c.isdigit():
            has_digit = True
        elif c.islower():
            has_lower = True
        elif c.isupper():
            has_upper = True
        else:
            has_special = True
    
    type_count = sum([has_digit, has_lower, has_upper, has_special])
    if type_count < 2:
        return False, '密码需包含至少两种字符类型（数字、小写字母、大写字母、特殊字符）'
    
    return True, None

def validate_name(name, max_length=10):
    """
    验证姓名
    规则: 必填，1-10字符
    返回: (valid: bool, error: str|None)
    """
    if not name:
        return False, '姓名为必填项'
    if len(name) > max_length:
        return False, f'姓名不能超过{max_length}个字符'
    return True, None

def validate_alias(alias, max_length=10):
    """
    验证雅号
    规则: 可选，最长10字符
    返回: (valid: bool, error: str|None)
    """
    if alias and len(alias) > max_length:
        return False, f'雅号不能超过{max_length}个字符'
    return True, None

def validate_birthday(birthday):
    """
    验证生日
    规则: 可选，格式YYYY-MM-DD，只校验格式正确性
    返回: (valid: bool, error: str|None)
    """
    if not birthday:
        return True, None  # 可选字段
    
    # 简单格式检查
    if len(birthday) != 10 or birthday[4] != '-' or birthday[7] != '-':
        return False, '日期格式不正确，应为YYYY-MM-DD'
    
    try:
        year = int(birthday[:4])
        month = int(birthday[5:7])
        day = int(birthday[8:10])
        
        # 基本范围检查
        if month < 1 or month > 12:
            return False, '月份应在1-12之间'
        if day < 1 or day > 31:
            return False, '日期应在1-31之间'
        
    except (ValueError, TypeError):
        return False, '日期格式不正确'
    
    return True, None

def validate_points(points):
    """
    验证积分
    规则: 可选，数字，范围0-999999
    返回: (valid: bool, error: str|None)
    """
    if points is None or points == '':
        return True, None
    
    try:
        p = int(points)
        if p < 0:
            return False, '积分值不能小于0'
        if p > 999999:
            return False, '积分值不能超过999999'
    except (ValueError, TypeError):
        return False, '积分值必须是数字'
    
    return True, None

def validate_custom_fields(custom_data, custom_fields_config):
    """
    验证自定义字段
    custom_data: 用户提交的自定义字段数据 {field_id: value}
    custom_fields_config: 自定义字段配置列表 [{id, label, type, required}, ...]
    返回: (valid: bool, error: str|None)
    """
    if not custom_fields_config:
        return True, None
    
    for field in custom_fields_config:
        field_id = field.get('id')
        label = field.get('label', '自定义字段')
        field_type = field.get('type', 'text')
        required = field.get('required', False)
        
        value = custom_data.get(field_id, '') if custom_data else ''
        
        # 必填检查
        if required and not value:
            return False, f'{label}为必填项'
        
        # 空值跳过后续验证
        if not value:
            continue
        
        # 类型验证
        if field_type == 'number':
            try:
                float(value)
            except (ValueError, TypeError):
                return False, f'{label}必须是有效的数字'
        elif field_type == 'email':
            if '@' not in value or '.' not in value:
                return False, f'{label}格式不正确'
        elif field_type == 'date':
            valid, err = validate_birthday(value)  # 复用日期验证
            if not valid:
                return False, f'{label}格式不正确'
    
    return True, None

# ============================================================================
# Token 鉴权机制
# ============================================================================
# Token格式: user_id:expire_timestamp:signature
# signature = sha256(user_id:expire_timestamp:secret_key)[:32]
# 签名密钥: 每次启动随机生成128位，与密码盐值(password_salt)完全独立
# 默认过期时间: 30天

DEFAULT_TOKEN_EXPIRE_DAYS = 30  # 默认30天

def _get_token_expire_seconds():
    """获取Token有效期秒数（从系统设置读取）"""
    settings = get_settings()
    days = settings.get('token_expire_days', DEFAULT_TOKEN_EXPIRE_DAYS)
    return int(days) * 24 * 3600

def _get_token_secret():
    """获取Token签名密钥（运行时随机生成，与密码盐值独立，重启后失效）"""
    return _RUNTIME_TOKEN_SECRET

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
    signature = ubinascii.hexlify(h.digest()).decode('utf-8')[:32]
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
        expected_signature = ubinascii.hexlify(h.digest()).decode('utf-8')[:32]
        
        if provided_signature != expected_signature:
            return False, None, "Token签名无效"
        
        return True, user_id, None
    except Exception as e:
        debug(f"Token验证失败: {e}", "Auth")
        return False, None, "Token解析失败"

def check_token(request):
    """
    从请求中验证Token（支持Header和参数两种方式）
    返回: (是否有效, user_id或None, 错误响应或None)
    """
    # 优先从Header获取
    token = request.headers.get('authorization', '').replace('Bearer ', '')
    # 其次从URL参数获取
    if not token:
        token = request.args.get('token', '')
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

# ==============================================================================
#  JSON Lines (JSONL) Database Manager
# ==============================================================================
class JsonlDB:
    def __init__(self, filepath, auto_migrate=True):
        self.filepath = filepath
        self._ensure_dir()
        if auto_migrate:
            self._migrate_legacy_json()

    def _ensure_dir(self):
        dirname = self.filepath.split('/')[0] if '/' in self.filepath else ''
        if dirname:
            try:
                os.stat(dirname)
            except OSError:
                os.mkdir(dirname)

    def _migrate_legacy_json(self):
        """Convert .json logic to .jsonl if .jsonl is missing"""
        if file_exists(self.filepath): return
        
        legacy_path = self.filepath.replace('.jsonl', '.json')
        if file_exists(legacy_path):
            debug(f"迁移 {legacy_path} -> {self.filepath}", "DB")
            try:
                with open(legacy_path, 'r') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        with open(self.filepath, 'w') as out:
                            for item in data:
                                out.write(json.dumps(item) + "\n")
                # os.remove(legacy_path) # Optional: Delete old file
            except Exception as e:
                error(f"迁移失败: {e}", "DB")

    def append(self, record):
        """Append a new record to the end of file"""
        try:
            with open(self.filepath, 'a') as f:
                f.write(json.dumps(record) + "\n")
            return True
        except Exception as e:
            error(f"追加记录失败: {e}", "DB")
            return False

    def get_max_id(self):
        """Scan file to find max numeric ID"""
        max_id = 0
        try:
            with open(self.filepath, 'r') as f:
                for line in f:
                    if not line.strip(): continue
                    try:
                        obj = json.loads(line)
                        if 'id' in obj:
                            # Handle string IDs if they are numeric
                            pid = int(obj['id']) 
                            if pid > max_id: max_id = pid
                    except Exception as e:
                        debug(f"解析ID行失败: {e}", "DB")
        except OSError:
            pass  # 文件可能不存在，正常情况
        return max_id

    def fetch_page(self, page=1, limit=10, reverse=True, search_term=None, search_fields=None):
        """
        Fetch a page of records.
        - Memory optimized: Scans file to find line offsets first.
        - Returns: (records_list, total_count)
        """
        if not file_exists(self.filepath): return [], 0
        
        search_lower = search_term.lower() if search_term else None
        
        if not search_lower:
            # --- Fast Path: No Search ---
            offsets = []
            try:
                with open(self.filepath, 'r') as f:
                    while True:
                        pos = f.tell()
                        line = f.readline()
                        if not line: break
                        if line.strip(): offsets.append(pos)
            except Exception as e:
                debug(f"读取文件偏移失败: {e}", "DB")
            
            total = len(offsets)
            if reverse: offsets.reverse()
            
            # Pagination Logic
            start_idx = (page - 1) * limit
            end_idx = start_idx + limit
            
            target_offsets = offsets[start_idx:end_idx]
            results = []
            
            if target_offsets:
                with open(self.filepath, 'r') as f:
                    for off in target_offsets:
                        f.seek(off)
                        line = f.readline()
                        try:
                            results.append(json.loads(line))
                        except Exception as e:
                            debug(f"解析记录失败: {e}", "DB")
            return results, total
            
        else:
            # --- Slow Path: Search (Scan Full File) ---
            # 内存优化：先扫描记录匹配行的偏移量，最后只解析需要的分页范围
            matched_offsets = []
            try:
                with open(self.filepath, 'r') as f:
                    while True:
                        pos = f.tell()
                        line = f.readline()
                        if not line: break
                        if not line.strip(): continue
                        
                        # 快速检查：先在原始行中搜索（不解析JSON）
                        if search_lower not in line.lower():
                            continue
                        
                        # 确认匹配：解析JSON后精确匹配字段值
                        try:
                            obj = json.loads(line)
                            found = False
                            for k, v in obj.items():
                                if search_lower in str(v).lower():
                                    found = True
                                    break
                            if found:
                                matched_offsets.append(pos)
                        except:
                            pass
            except Exception as e:
                debug(f"搜索文件读取失败: {e}", "DB")
            
            total = len(matched_offsets)
            if reverse:
                matched_offsets.reverse()
            
            # 只读取当前页需要的记录
            start_idx = (page - 1) * limit
            end_idx = start_idx + limit
            target_offsets = matched_offsets[start_idx:end_idx]
            
            results = []
            if target_offsets:
                try:
                    with open(self.filepath, 'r') as f:
                        for off in target_offsets:
                            f.seek(off)
                            line = f.readline()
                            try:
                                results.append(json.loads(line))
                            except:
                                pass
                except Exception as e:
                    debug(f"读取搜索结果失败: {e}", "DB")
            
            return results, total

    def update(self, id_val, update_func):
        """
        Rewrite file to update record.
        update_func(record) -> should modify record in place
        """
        if not file_exists(self.filepath): return False
        
        tmp_path = self.filepath + '.tmp'
        found = False
        try:
            with open(self.filepath, 'r') as f_in, open(tmp_path, 'w') as f_out:
                for line in f_in:
                    if not line.strip(): continue
                    try:
                        record = json.loads(line)
                        r_id = record.get('id')
                        # loose comparison
                        if str(r_id) == str(id_val):
                            update_func(record)
                            found = True
                        f_out.write(json.dumps(record) + '\n')
                    except Exception as e:
                        debug(f"更新解析记录失败: {e}", "DB")
            
            if found:
                os.remove(self.filepath)
                os.rename(tmp_path, self.filepath)
                return True
            else:
                os.remove(tmp_path)
                return False
        except Exception as e:
            error(f"更新记录失败: {e}", "DB")
            if file_exists(tmp_path): os.remove(tmp_path)
            return False

    def delete(self, id_val):
        """Rewrite file excluding record"""
        if not file_exists(self.filepath): return False
        tmp_path = self.filepath + '.tmp'
        found = False
        try:
            with open(self.filepath, 'r') as f_in, open(tmp_path, 'w') as f_out:
                for line in f_in:
                    if not line.strip(): continue
                    try:
                        record = json.loads(line)
                        if str(record.get('id')) == str(id_val):
                            found = True
                            continue # Skip writing
                        f_out.write(json.dumps(record) + '\n')
                    except Exception as e:
                        debug(f"删除解析记录失败: {e}", "DB")
            
            os.remove(self.filepath)
            os.rename(tmp_path, self.filepath)
            return found
        except Exception as e:
            error(f"删除记录失败: {e}", "DB")
            if file_exists(tmp_path): os.remove(tmp_path)
            return False
            
    def get_all(self):
        """Load ALL records (Use only for small datasets like Members/Settings)"""
        res = []
        if not file_exists(self.filepath): return []
        with open(self.filepath, 'r') as f:
            for line in f:
                if line.strip():
                    try:
                        res.append(json.loads(line))
                    except Exception as e:
                        debug(f"get_all解析记录失败: {e}", "DB")
        return res

    def get_by_id(self, id_val):
        """根据ID获取单条记录"""
        if not file_exists(self.filepath): return None
        try:
            with open(self.filepath, 'r') as f:
                for line in f:
                    if not line.strip(): continue
                    try:
                        record = json.loads(line)
                        if str(record.get('id')) == str(id_val):
                            return record
                    except:
                        pass
        except Exception as e:
            debug(f"get_by_id读取失败: {e}", "DB")
        return None

    def iter_records(self):
        """流式迭代器：逐行读取记录，内存友好（用于聚合计算）"""
        if not file_exists(self.filepath):
            return
        try:
            with open(self.filepath, 'r') as f:
                for line in f:
                    if line.strip():
                        try:
                            yield json.loads(line)
                        except:
                            pass
        except Exception as e:
            debug(f"iter_records失败: {e}", "DB")

    def count(self):
        """统计记录数量（只计数，不解析JSON，内存友好）"""
        if not file_exists(self.filepath):
            return 0
        count = 0
        try:
            with open(self.filepath, 'r') as f:
                for line in f:
                    if line.strip():
                        count += 1
        except Exception as e:
            debug(f"统计记录数失败: {e}", "DB")
        return count


# Initialize DBs
db_poems = JsonlDB('data/poems.jsonl')
db_members = JsonlDB('data/members.jsonl')
db_activities = JsonlDB('data/activities.jsonl')
db_finance = JsonlDB('data/finance.jsonl')
db_tasks = JsonlDB('data/tasks.jsonl')
db_login_logs = JsonlDB('data/login_logs.jsonl')
db_points_logs = JsonlDB('data/points_logs.jsonl')

def get_current_time():
    """获取当前时间字符串 (ISO格式近似)"""
    t = time.localtime()
    return "{:04d}-{:02d}-{:02d}T{:02d}:{:02d}:{:02d}".format(
        t[0], t[1], t[2], t[3], t[4], t[5]
    )

# ============================================================================
# 权限验证辅助函数
# ============================================================================

# 权限级别定义
ROLE_SUPER_ADMIN = ['super_admin']  # 超级管理员级别：仅超管
ROLE_ADMIN = ['super_admin', 'admin']  # 管理员级别：超管、管理员
ROLE_DIRECTOR = ['super_admin', 'admin', 'director']  # 理事级别：超管、管理员、理事
ROLE_FINANCE = ['super_admin', 'admin', 'finance']  # 财务级别：超管、管理员、财务

# 角色权限层级（数字越小权限越高）
ROLE_LEVEL = {
    'super_admin': 0,
    'admin': 1,
    'director': 2,
    'finance': 3,
    'member': 4
}

def can_assign_role(operator_role, target_role):
    """
    检查操作者是否可以分配目标角色
    返回: (allowed: bool, error_message: str|None)
    """
    # 禁止通过API添加超级管理员
    if target_role == 'super_admin':
        return False, '不能通过此方式添加超级管理员'
    
    # 理事只能添加社员，不能添加财务
    if operator_role == 'director' and target_role != 'member':
        return False, '理事只能添加社员'
    
    operator_level = ROLE_LEVEL.get(operator_role, 4)
    target_level = ROLE_LEVEL.get(target_role, 4)
    
    # 非超级管理员不能分配比自己权限高或相同的角色
    if operator_role != 'super_admin' and target_level <= operator_level:
        return False, '不能添加与自己权限相同或更高的角色'
    
    return True, None

def can_manage_member(operator_id, operator_role, target_member_id, target_member_role):
    """
    检查操作者是否可以管理（编辑/删除）目标成员
    返回: (allowed: bool, error_message: str|None)
    规则：
    - 超级管理员只能由自己编辑
    - 不能管理权限比自己高或相同的用户（超管除外）
    """
    # 超级管理员只能由自己编辑
    if target_member_role == 'super_admin':
        if operator_id == target_member_id:
            return True, None
        return False, '超级管理员资料只能由其本人修改'
    
    # 超级管理员可以管理其他所有用户
    if operator_role == 'super_admin':
        return True, None
    
    # 不能管理权限比自己高或相同的用户
    operator_level = ROLE_LEVEL.get(operator_role, 3)
    target_level = ROLE_LEVEL.get(target_member_role, 3)
    if target_level <= operator_level:
        return False, '无权管理此用户'
    
    return True, None

def get_operator_role(request):
    """
    从请求中获取操作者角色（通过Token验证）
    返回: (user_id, role) 或 (None, None)
    """
    try:
        data = request.json if request.json else {}
        
        # 从Header、URL参数或请求体获取Token
        token = request.headers.get('authorization', '').replace('Bearer ', '')
        if not token:
            token = request.args.get('token', '') or data.get('token', '')
        
        if not token:
            return None, None
        
        valid, user_id, err_msg = verify_token(token)
        if valid and user_id:
            # Token有效，查询用户角色
            with open(db_members.filepath, 'r') as f:
                for line in f:
                    try:
                        m = json.loads(line)
                        if m.get('id') == user_id:
                            return user_id, m.get('role', 'member')
                    except:
                        pass
    except Exception as e:
        debug(f"获取操作者角色失败: {e}", "Auth")
    return None, None

# ============================================================================
# 鉴权装饰器 - 简化API权限验证
# ============================================================================

def require_login(f):
    """
    装饰器：需要登录
    用法：@require_login
    """
    def wrapper(request, *args, **kwargs):
        data = request.json if request.json else {}
        token = request.headers.get('authorization', '').replace('Bearer ', '')
        if not token:
            token = request.args.get('token', '') or data.get('token', '')
        
        if not token:
            return Response('{"error": "请先登录"}', 401, {'Content-Type': 'application/json'})
        
        valid, user_id, err_msg = verify_token(token)
        if not valid:
            return Response(json.dumps({"error": err_msg}), 401, {'Content-Type': 'application/json'})
        
        return f(request, *args, **kwargs)
    return wrapper

def require_permission(allowed_roles):
    """
    装饰器：需要指定角色权限
    用法：@require_permission(ROLE_ADMIN) 或 @require_permission(['super_admin', 'admin'])
    """
    def decorator(f):
        def wrapper(request, *args, **kwargs):
            user_id, role = get_operator_role(request)
            if not user_id:
                return Response('{"error": "请先登录"}', 401, {'Content-Type': 'application/json'})
            if role not in allowed_roles:
                return Response('{"error": "权限不足"}', 403, {'Content-Type': 'application/json'})
            return f(request, *args, **kwargs)
        return wrapper
    return decorator

# 保留原有函数供特殊场景使用
def check_permission(request, allowed_roles):
    """检查请求者是否具有指定权限（供特殊场景调用）"""
    user_id, role = get_operator_role(request)
    if not user_id:
        return False, Response('{"error": "请先登录"}', 401, {'Content-Type': 'application/json'})
    if role not in allowed_roles:
        return False, Response('{"error": "权限不足"}', 403, {'Content-Type': 'application/json'})
    return True, None

def check_login(request):
    """检查请求是否已登录（供特殊场景调用）"""
    data = request.json if request.json else {}
    token = request.headers.get('authorization', '').replace('Bearer ', '')
    if not token:
        token = request.args.get('token', '') or data.get('token', '')
    
    if not token:
        return False, None, Response('{"error": "请先登录"}', 401, {'Content-Type': 'application/json'})
    
    valid, user_id, err_msg = verify_token(token)
    if valid:
        return True, user_id, None
    else:
        return False, None, Response(json.dumps({"error": err_msg}), 401, {'Content-Type': 'application/json'})

def check_login_get(request):
    """
    检查 GET 请求是否已登录（通过Token验证）
    返回: (已登录, 错误响应或None)
    """
    token = request.headers.get('authorization', '').replace('Bearer ', '')
    if not token:
        token = request.args.get('token', '')
    
    if not token:
        return False, Response('{"error": "请先登录"}', 401, {'Content-Type': 'application/json'})
    
    valid, user_id, err_msg = verify_token(token)
    if valid:
        return True, None
    else:
        return False, Response(json.dumps({"error": err_msg}), 401, {'Content-Type': 'application/json'})

def record_points_change(member_id, member_name, change, reason):
    """记录积分变动日志"""
    log = {
        'id': db_points_logs.get_max_id() + 1,
        'member_id': member_id,
        'member_name': member_name,
        'change': change,
        'reason': reason,
        'timestamp': get_current_time()
    }
    db_points_logs.append(log)

def record_login_log(member_id, member_name, phone, status):
    """记录登录日志"""
    log = {
        'id': db_login_logs.get_max_id() + 1,
        'member_id': member_id,
        'member_name': member_name,
        'phone': phone[:3] + '****' + phone[-4:] if len(phone) >= 7 else phone,
        'login_time': get_current_time(),
        'status': status
    }
    db_login_logs.append(log)
    
    # 保留最近100条日志，清理旧日志
    try:
        all_logs = db_login_logs.get_all()
        if len(all_logs) > 100:
            # 只保留最新100条
            keep_logs = all_logs[-100:]
            tmp_path = db_login_logs.filepath + '.tmp'
            with open(tmp_path, 'w') as f:
                for l in keep_logs:
                    f.write(json.dumps(l) + '\n')
            os.remove(db_login_logs.filepath)
            os.rename(tmp_path, db_login_logs.filepath)
    except Exception as e:
        debug(f"清理登录日志失败: {e}", "Log")

# Legacy for settings (kept as simple JSON for now)
def get_settings():
    """获取系统设置，从合并后的配置文件中读取"""
    try:
        with open('data/config.json', 'r') as f:
            config = json.load(f)
            # 返回系统设置相关的键值
            return {
                'custom_member_fields': config.get('custom_member_fields', []),
                'password_salt': config.get('password_salt', 'weilu2018'),
                'points_name': config.get('points_name', '围炉值'),
                'system_name': config.get('system_name', '围炉诗社·理事台'),
                'token_expire_days': config.get('token_expire_days', DEFAULT_TOKEN_EXPIRE_DAYS),
                'maintenance_mode': config.get('maintenance_mode', False),
                'allow_guest': config.get('allow_guest', True),
                'chat_enabled': config.get('chat_enabled', True),
                'chat_guest_max': config.get('chat_guest_max', 10),
                'chat_max_users': config.get('chat_max_users', 20),
                'chat_cache_size': config.get('chat_cache_size', 128)
            }
    except: 
        return {
            'custom_member_fields': [],
            'password_salt': 'weilu2018',
            'points_name': '围炉值',
            'system_name': '围炉诗社·理事台',
            'token_expire_days': DEFAULT_TOKEN_EXPIRE_DAYS,
            'maintenance_mode': False,
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
        for key in ['custom_member_fields', 'password_salt', 'points_name', 'system_name', 'token_expire_days',
                    'maintenance_mode', 'allow_guest', 'chat_enabled', 'chat_guest_max', 'chat_max_users', 'chat_cache_size']:
            if key in data:
                config[key] = data[key]
        
        # 保存回配置文件
        with open('data/config.json', 'w') as f:
            json.dump(config, f)
    except Exception as e:
        error(f"保存设置失败: {e}", "Settings")

def print_system_status():
    info("-" * 50, "System")
    info("围炉诗社运营管理系统 - 系统状态", "System")
    info("-" * 50, "System")
    try:
        wlan_sta = network.WLAN(network.STA_IF)
        if wlan_sta.active() and wlan_sta.isconnected():
            ifconf = wlan_sta.ifconfig()
            info(f"WiFi IP: {ifconf[0]}", "System")
    except Exception as e:
        debug(f"获取WiFi状态失败: {e}", "System")
    try:
        gc.collect() 
        info(f"可用内存: {gc.mem_free()/1024:.2f} KB", "System")
    except Exception as e:
        debug(f"获取内存状态失败: {e}", "System")
    info("-" * 50, "System")

# ==============================================================================
#  Routes & API Controllers
# ==============================================================================

@app.route('/')
def index(request): return send_file('static/index.html')
@app.route('/static/style.css')
def style(request): return send_file('static/style.css')
@app.route('/static/app.js')
def app_js(request): return send_file('static/app.js')
@app.route('/static/logo.png')
def logo_png(request): return send_file('static/logo.png')
@app.route('/static/marked.umd.js')
def marked_js(request): return send_file('static/marked.umd.js')
@app.route('/static/purify.min.js')
def purify_js(request): return send_file('static/purify.min.js')

# --- Poems API ---
@api_route('/api/poems', methods=['GET'])
def list_poems(request):
    # args: page=1, limit=10, q=...
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 10))
        q = request.args.get('q', None)
        
        if q:
            # print(f"[API] Raw query: {q}")
            q = simple_unquote(q)
            # print(f"[API] Decoded: {q}")
        
        # Backward compatibility: if no args, return top 20? 
        # But if 'all=true' (implied currently by frontend logic), existing logic expects everything.
        # But for 10k records we can't.
        # So we default to returning the first page (latest 20).
        # Frontend 'fetchPoems' will receive this array.
        
        items, total = db_poems.fetch_page(page, limit, reverse=True, search_term=q)
        return items 
    except Exception as e:
        error(f"获取诗歌列表失败: {e}", "API")
        return []

@api_route('/api/poems/random', methods=['GET'])
def random_poem(request):
    """获取随机一首诗词（用于今日推荐）"""
    try:
        import urandom
        total = db_poems.count()
        if total == 0:
            return {}  # 无数据时返回空对象
        # 生成随机索引
        random_index = urandom.getrandbits(16) % total
        # 读取该位置的诗词
        count = 0
        with open(db_poems.filepath, 'r') as f:
            for line in f:
                if count == random_index:
                    return json.loads(line)
                count += 1
        return {}  # 未找到时返回空对象
    except Exception as e:
        error(f"获取随机诗歌失败: {e}", "API")
        return {}  # 异常时返回空对象

@api_route('/api/poems', methods=['POST'])
@require_login
def create_poem(request):
    if not request.json: return Response('Invalid JSON', 400)
    data = request.json
    
    # 必填项验证
    if not data.get('title') or not data.get('content'):
        return Response('{"error": "诗名和正文为必填项"}', 400, {'Content-Type': 'application/json'})
    
    new_id = db_poems.get_max_id() + 1
    data['id'] = new_id
    if 'date' not in data: data['date'] = '2026-01-01'
    
    if db_poems.append(data):
        return data
    return Response('Write Failed', 500)

@api_route('/api/poems/update', methods=['POST'])
@require_login
def update_poem(request):
    if not request.json: return Response('Invalid', 400)
    data = request.json
    pid = data.get('id')
    
    # 必填项验证
    if not pid:
        return Response('{"error": "缺少记录ID"}', 400, {'Content-Type': 'application/json'})
    if not data.get('title') or not data.get('content'):
        return Response('{"error": "诗名和正文为必填项"}', 400, {'Content-Type': 'application/json'})
    
    def updater(record):
        if 'title' in data: record['title'] = data['title']
        if 'content' in data: record['content'] = data['content']
        if 'type' in data: record['type'] = data['type']
        if 'date' in data: record['date'] = data['date']
        
    if db_poems.update(pid, updater):
        return {"status": "success"}
    return Response("Poem not found", 404)

@api_route('/api/poems/delete', methods=['POST'])
@require_login
def delete_poem(request):
    if not request.json: return Response('Invalid', 400)
    pid = request.json.get('id')
    if db_poems.delete(pid):
        return {"status": "success"}
    return Response("Poem not found", 404)

# --- Activities API ---
@api_route('/api/activities', methods=['GET'])
def list_activities(request):
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 50))
        q = request.args.get('q', None)
        if q: q = simple_unquote(q)
        items, _ = db_activities.fetch_page(page, limit, reverse=True, search_term=q)
        return items
    except: return []

@api_route('/api/activities', methods=['POST'])
@require_permission(ROLE_DIRECTOR)
def create_activity(request):
    if not request.json: return Response('Invalid', 400)
    data = request.json
    
    # 必填项验证
    if not data.get('title') or not data.get('date'):
        return Response('{"error": "活动主题和时间为必填项"}', 400, {'Content-Type': 'application/json'})
    
    data['id'] = db_activities.get_max_id() + 1
    db_activities.append(data)
    return data

@api_route('/api/activities/update', methods=['POST'])
@require_permission(ROLE_DIRECTOR)
def update_activity(request):
    data = request.json
    if not data: return Response('Invalid', 400)
    
    # 必填项验证
    if not data.get('id'):
        return Response('{"error": "缺少记录ID"}', 400, {'Content-Type': 'application/json'})
    if not data.get('title') or not data.get('date'):
        return Response('{"error": "活动主题和时间为必填项"}', 400, {'Content-Type': 'application/json'})
    
    def updater(r):
        for k in ['title', 'desc', 'date', 'location', 'status']:
            if k in data: r[k] = data[k]
            
    if db_activities.update(data.get('id'), updater):
        return {"status": "success"}
    return Response("Not Found", 404)

@api_route('/api/activities/delete', methods=['POST'])
@require_permission(ROLE_DIRECTOR)
def delete_activity(request):
    pid = request.json.get('id')
    if db_activities.delete(pid): return {"status": "success"}
    return Response("Not Found", 404)

# --- Tasks API ---
@api_route('/api/tasks', methods=['GET'])
@require_login
def list_tasks(request):
    """获取任务列表，支持分页和搜索"""
    try:
        page = int(request.args.get('page', 0))
        limit = int(request.args.get('limit', 0))
        q = request.args.get('q', None)
        if q:
            q = simple_unquote(q)
        
        # 如果提供了分页参数，使用分页查询
        if page > 0 and limit > 0:
            items, total = db_tasks.fetch_page(page, limit, reverse=True, search_term=q)
            return {"data": items, "total": total, "page": page, "limit": limit}
        else:
            # 向后兼容：不带分页参数时返回全部数据
            return db_tasks.get_all()
    except Exception as e:
        error(f"获取任务列表失败: {e}", "API")
        return []

@api_route('/api/tasks', methods=['POST'])
@require_permission(ROLE_DIRECTOR)
def create_task(request):
    """创建新任务"""
    data = request.json
    if not data: return Response('Invalid', 400)
    
    # 必填项验证
    if not data.get('title'):
        return Response('{"error": "事务标题为必填项"}', 400, {'Content-Type': 'application/json'})
    
    # 检查是否直接派发给指定用户
    assignee = data.get('assignee')
    status = 'open'
    claimed_at = None
    
    if assignee:
        # 直接派发模式：状态为已领取
        status = 'claimed'
        claimed_at = get_current_time()
    
    task = {
        'id': db_tasks.get_max_id() + 1,
        'title': data.get('title', ''),
        'description': data.get('description', ''),
        'reward': int(data.get('reward', 0)),
        'status': status,
        'creator': data.get('creator', ''),
        'creator_id': data.get('creator_id'),  # 存储创建者ID用于动态查找
        'assignee': assignee,
        'assignee_id': data.get('assignee_id'),  # 存储领取者ID用于动态查找
        'created_at': get_current_time(),
        'claimed_at': claimed_at,
        'submitted_at': None,
        'completed_at': None
    }
    db_tasks.append(task)
    return task

@api_route('/api/tasks/update', methods=['POST'])
@require_permission(ROLE_DIRECTOR)
def update_task(request):
    """更新任务（仅理事及以上权限）"""
    data = request.json
    if not data: return Response('Invalid', 400)
    
    tid = data.get('id')
    if not tid:
        return Response('{"error": "缺少任务ID"}', 400, {'Content-Type': 'application/json'})
    
    updated = False
    
    def task_updater(t):
        nonlocal updated
        # 更新可修改字段
        if 'title' in data and data['title']:
            t['title'] = data['title']
        if 'description' in data:
            t['description'] = data['description']
        if 'reward' in data:
            t['reward'] = int(data['reward']) if data['reward'] else 0
        updated = True
        return t
    
    db_tasks.update(tid, task_updater)
    
    if updated:
        return {'success': True}
    return Response('{"error": "任务不存在"}', 404, {'Content-Type': 'application/json'})

@api_route('/api/tasks/claim', methods=['POST'])
@require_login
def claim_task(request):
    """领取任务"""
    data = request.json
    tid = data.get('task_id')
    u_name = data.get('member_name')
    u_id = data.get('member_id')  # 获取领取者ID
    
    task_found = False
    
    def task_updater(t):
        nonlocal task_found
        if t.get('status') == 'open':
            t['status'] = 'claimed'
            t['assignee'] = u_name
            t['assignee_id'] = u_id  # 存储领取者ID用于动态查找
            t['claimed_at'] = get_current_time()
            task_found = True
            
    db_tasks.update(tid, task_updater)
    
    if not task_found: return Response('Task not available', 404)
    return {"status": "success"}

@api_route('/api/tasks/unclaim', methods=['POST'])
@require_login
def unclaim_task(request):
    """撤销领取任务"""
    data = request.json
    tid = data.get('task_id')
    
    task_found = False
    
    def task_updater(t):
        nonlocal task_found
        if t.get('status') == 'claimed':
            t['status'] = 'open'
            t['assignee'] = None
            t['claimed_at'] = None
            task_found = True
            
    db_tasks.update(tid, task_updater)
    
    if not task_found: return Response('Task not found or cannot unclaim', 404)
    return {"status": "success"}

@api_route('/api/tasks/submit', methods=['POST'])
@require_login
def submit_task(request):
    """提交任务完成"""
    data = request.json
    tid = data.get('task_id')
    
    task_found = False
    
    def task_updater(t):
        nonlocal task_found
        if t.get('status') == 'claimed':
            t['status'] = 'submitted'
            t['submitted_at'] = get_current_time()
            task_found = True
            
    db_tasks.update(tid, task_updater)
    
    if not task_found: return Response('Task not claimable', 404)
    return {"status": "success"}

@api_route('/api/tasks/approve', methods=['POST'])
@require_permission(ROLE_DIRECTOR)
def approve_task(request):
    """审批任务"""
    data = request.json
    tid = data.get('task_id')
    force = data.get('force', False)  # 管理员强制验收标志
    
    reward = 0
    assignee_name = None
    task_status = None
    task_found = False
    
    def task_updater(t):
        nonlocal reward, assignee_name, task_status, task_found
        task_found = True
        task_status = t.get('status')
        # 允许验收submitted状态，或force模式下的claimed状态
        if task_status == 'submitted' or (force and task_status == 'claimed'):
            t['status'] = 'completed'
            t['completed_at'] = get_current_time()
            if not t.get('submitted_at'):
                t['submitted_at'] = get_current_time()
            reward = t.get('reward', 0)
            assignee_name = t.get('assignee')
            
    db_tasks.update(tid, task_updater)
    
    # 任务不存在
    if not task_found:
        return Response('Task not found', 404)
    
    # 任务已完成（可能是重复请求）
    if task_status == 'completed':
        return {"status": "success", "gained": 0, "message": "已验收"}
    
    # 任务状态不允许验收
    if task_status not in ['submitted', 'claimed']:
        return Response('Task cannot be approved in current status', 400)
    
    # 非force模式下，claimed状态不能验收
    if task_status == 'claimed' and not force:
        return Response('Task not submitted yet', 400)
    
    # 发放奖励
    if assignee_name and reward > 0:
        members = db_members.get_all()
        target_mid = None
        for m in members:
            if m.get('name') == assignee_name:
                target_mid = m.get('id')
                break
                
        if target_mid:
            def member_updater(m):
                m['points'] = m.get('points', 0) + reward
            db_members.update(target_mid, member_updater)
            record_points_change(target_mid, assignee_name, reward, '完成任务')
    
    return {"status": "success", "gained": reward}

@api_route('/api/tasks/reject', methods=['POST'])
@require_permission(ROLE_DIRECTOR)
def reject_task(request):
    """拒绝任务"""
    data = request.json
    tid = data.get('task_id')
    
    task_found = False
    
    def task_updater(t):
        nonlocal task_found
        if t.get('status') == 'submitted':
            t['status'] = 'claimed'  # 退回到进行中状态
            t['submitted_at'] = None
            task_found = True
            
    db_tasks.update(tid, task_updater)
    
    if not task_found: return Response('Task not found', 404)
    return {"status": "success"}

@api_route('/api/tasks/delete', methods=['POST'])
@require_permission(ROLE_DIRECTOR)
def delete_task(request):
    """删除任务"""
    data = request.json
    tid = data.get('task_id')
    if db_tasks.delete(tid):
        return {"status": "success"}
    return Response("Error", 500)

@api_route('/api/tasks/complete', methods=['POST'])
@require_permission(ROLE_DIRECTOR)
def complete_task(request):
    """快速完成任务"""
    data = request.json
    tid = data.get('task_id')
    u_name = data.get('member_name')
    
    reward = 0
    task_found = False
    
    def task_updater(t):
        nonlocal reward, task_found
        if t.get('status') == 'open':
            t['status'] = 'completed'
            t['assignee'] = u_name
            reward = t.get('reward', 0)
            task_found = True
            
    db_tasks.update(tid, task_updater)
    
    if not task_found: return Response('Task not open or found', 404)
    
    def member_updater(m):
        m['points'] = m.get('points', 0) + reward
        
    members = db_members.get_all()
    target_mid = None
    for m in members:
        if m.get('name') == u_name:
            target_mid = m.get('id')
            break
            
    if target_mid:
        db_members.update(target_mid, member_updater)
        # 记录积分变动日志
        if reward > 0:
            record_points_change(target_mid, u_name, reward, '完成任务')
        
    return {"status": "success", "gained": reward}

# --- Members API ---
@api_route('/api/members', methods=['GET'])
def list_members(request):
    """获取成员列表，支持分页和搜索
    参数 public=1 时返回公开信息（雅号、围炉值），用于未登录访问
    """
    try:
        page = int(request.args.get('page', 0))
        limit = int(request.args.get('limit', 0))
        q = request.args.get('q', None)
        public_mode = request.args.get('public', '0') == '1'
        if q:
            q = simple_unquote(q)
        
        # 如果提供了分页参数，使用分页查询
        if page > 0 and limit > 0:
            items, total = db_members.fetch_page(page, limit, reverse=False, search_term=q)
            if public_mode:
                # 公开模式：只返回雅号和围炉值
                items = [{'id': m.get('id'), 'alias': m.get('alias', ''), 'points': m.get('points', 0)} for m in items]
            return {"data": items, "total": total, "page": page, "limit": limit}
        else:
            # 向后兼容：不带分页参数时返回全部数据
            members = db_members.get_all()
            if public_mode:
                # 公开模式：只返回雅号和围炉值
                return [{'id': m.get('id'), 'alias': m.get('alias', ''), 'points': m.get('points', 0)} for m in members]
            return members
    except Exception as e:
        error(f"获取成员列表失败: {e}", "API")
        return []

@api_route('/api/members', methods=['POST'])
@require_permission(ROLE_DIRECTOR)
def create_member(request):
    data = request.json
    if not data: return Response('Invalid', 400)
    
    # 必填项验证
    if not data.get('name') or not data.get('phone') or not data.get('password'):
        return Response('{"error": "姓名、手机号和密码为必填项"}', 400, {'Content-Type': 'application/json'})
    
    # 姓名验证
    valid, err = validate_name(data.get('name'))
    if not valid:
        return Response(json.dumps({"error": err}), 400, {'Content-Type': 'application/json'})
    
    # 雅号验证
    valid, err = validate_alias(data.get('alias', ''))
    if not valid:
        return Response(json.dumps({"error": err}), 400, {'Content-Type': 'application/json'})
    
    # 手机号格式验证
    valid, err = validate_phone(data.get('phone'))
    if not valid:
        return Response(json.dumps({"error": err}), 400, {'Content-Type': 'application/json'})
    
    # 密码强度验证
    valid, err = validate_password_strength(data.get('password'))
    if not valid:
        return Response(json.dumps({"error": err}), 400, {'Content-Type': 'application/json'})
    
    # 生日验证
    valid, err = validate_birthday(data.get('birthday', ''))
    if not valid:
        return Response(json.dumps({"error": err}), 400, {'Content-Type': 'application/json'})
    
    # 积分验证
    valid, err = validate_points(data.get('points'))
    if not valid:
        return Response(json.dumps({"error": err}), 400, {'Content-Type': 'application/json'})
    
    # 自定义字段验证
    settings = get_settings()
    custom_fields_config = settings.get('custom_member_fields', [])
    valid, err = validate_custom_fields(data.get('custom'), custom_fields_config)
    if not valid:
        return Response(json.dumps({"error": err}), 400, {'Content-Type': 'application/json'})
    
    # 角色权限验证：不能添加超级管理员或高于自己权限的角色
    target_role = data.get('role', 'member')
    _, operator_role = get_operator_role(request)
    allowed, role_err = can_assign_role(operator_role, target_role)
    if not allowed:
        return Response(json.dumps({"error": role_err}), 400, {'Content-Type': 'application/json'})
    
    # 手机号唯一性检查
    existing = db_members.get_all()
    for m in existing:
        if m.get('phone') == data.get('phone'):
            return Response('{"error": "该手机号已被注册"}', 400, {'Content-Type': 'application/json'})
    
    # 对密码进行哈希处理
    if 'password' in data and data['password']:
        data['password'] = hash_password(data['password'])
            
    data['id'] = db_members.get_max_id() + 1
    db_members.append(data)
    return data

@api_route('/api/members/update', methods=['POST'])
@require_permission(ROLE_DIRECTOR)
def update_member_route(request):
    data = request.json
    mid = data.get('id')
    
    # 获取操作者ID和角色
    operator_id, operator_role = get_operator_role(request)
    
    # 获取目标成员的当前角色，检查是否有权限管理
    target_member = None
    for m in db_members.get_all():
        if m.get('id') == mid:
            target_member = m
            break
    
    if not target_member:
        return Response('{"error": "成员不存在"}', 404, {'Content-Type': 'application/json'})
    
    # 检查是否有权限管理此成员（传入操作者ID和目标成员ID）
    target_member_role = target_member.get('role', 'member')
    allowed, manage_err = can_manage_member(operator_id, operator_role, mid, target_member_role)
    if not allowed:
        return Response(json.dumps({"error": manage_err}), 403, {'Content-Type': 'application/json'})
    
    # 超级管理员角色不可变更（包括自己也不能改）
    if target_member_role == 'super_admin' and 'role' in data:
        if data.get('role') != 'super_admin':
            return Response('{"error": "超级管理员角色不可变更"}', 400, {'Content-Type': 'application/json'})
    
    # 如果更新角色且角色发生变化，验证角色权限
    if 'role' in data and data.get('role') != target_member_role:
        target_role = data.get('role')
        allowed, role_err = can_assign_role(operator_role, target_role)
        if not allowed:
            return Response(json.dumps({"error": role_err}), 400, {'Content-Type': 'application/json'})
    
    # 字段验证
    if 'name' in data:
        valid, err = validate_name(data.get('name'))
        if not valid:
            return Response(json.dumps({"error": err}), 400, {'Content-Type': 'application/json'})
    
    if 'alias' in data:
        valid, err = validate_alias(data.get('alias', ''))
        if not valid:
            return Response(json.dumps({"error": err}), 400, {'Content-Type': 'application/json'})
    
    if 'phone' in data:
        valid, err = validate_phone(data.get('phone'))
        if not valid:
            return Response(json.dumps({"error": err}), 400, {'Content-Type': 'application/json'})
        # 手机号唯一性检查（排除自己）
        for m in db_members.get_all():
            if m.get('phone') == data.get('phone') and m.get('id') != mid:
                return Response('{"error": "该手机号已被其他用户使用"}', 400, {'Content-Type': 'application/json'})
    
    if 'birthday' in data:
        valid, err = validate_birthday(data.get('birthday', ''))
        if not valid:
            return Response(json.dumps({"error": err}), 400, {'Content-Type': 'application/json'})
    
    if 'points' in data:
        valid, err = validate_points(data.get('points'))
        if not valid:
            return Response(json.dumps({"error": err}), 400, {'Content-Type': 'application/json'})
    
    # 自定义字段验证
    if 'custom' in data:
        settings = get_settings()
        custom_fields_config = settings.get('custom_member_fields', [])
        valid, err = validate_custom_fields(data.get('custom'), custom_fields_config)
        if not valid:
            return Response(json.dumps({"error": err}), 400, {'Content-Type': 'application/json'})
    
    # 如果更新密码，验证强度并哈希处理
    if 'password' in data and data['password']:
        valid, err = validate_password_strength(data['password'])
        if not valid:
            return Response(json.dumps({"error": err}), 400, {'Content-Type': 'application/json'})
        data['password'] = hash_password(data['password'])
    
    # 处理积分字段类型转换
    if 'points' in data:
        try:
            data['points'] = int(data['points'])
        except (ValueError, TypeError):
            data['points'] = 0
    
    # 记录积分变动（如果有）
    points_change = 0
    member_name = ''
    old_points = 0
    
    if 'points' in data:
        # 先获取原积分值
        members = db_members.get_all()
        for m in members:
            if m.get('id') == mid:
                old_points = int(m.get('points', 0))
                member_name = m.get('name', '')
                break
        points_change = data['points'] - old_points
    
    def updater(m):
        for k in ['name', 'alias', 'phone', 'role', 'points', 'password', 'custom', 'birthday']:
            if k in data: m[k] = data[k]
    
    if db_members.update(mid, updater):
        # 如果积分有变动，记录日志
        if points_change != 0 and member_name:
            record_points_change(mid, member_name, points_change, '管理员调整')
        return {"status": "success"}
    return Response("Not Found", 404)

@api_route('/api/members/change_password', methods=['POST'])
def change_password_route(request):
    """用户修改自己的密码（需要登录）"""
    # 登录验证
    ok, user_id, err = check_login(request)
    if not ok:
        return err
    
    data = request.json
    member_id = data.get('id')
    old_password = data.get('old_password', '')
    new_password = data.get('new_password', '')
    
    if not member_id or not old_password or not new_password:
        return Response('{"error": "原密码和新密码为必填项"}', 400, {'Content-Type': 'application/json'})
    
    # 新密码强度验证
    valid, err = validate_password_strength(new_password)
    if not valid:
        return Response(json.dumps({"error": err}), 400, {'Content-Type': 'application/json'})
    
    # 获取当前成员
    members = db_members.get_all()
    member = None
    for m in members:
        if m.get('id') == member_id:
            member = m
            break
    
    if not member:
        return Response('{"error": "用户不存在"}', 404, {'Content-Type': 'application/json'})
    
    # 验证旧密码
    if not verify_password(old_password, member.get('password', '')):
        return Response('{"error": "原密码错误"}', 400, {'Content-Type': 'application/json'})
    
    # 更新密码（哈希处理）
    new_hashed = hash_password(new_password)
    
    def updater(m):
        m['password'] = new_hashed
    
    if db_members.update(member_id, updater):
        return {"status": "success"}
    return Response('{"error": "更新失败"}', 500, {'Content-Type': 'application/json'})

@api_route('/api/members/delete', methods=['POST'])
@require_permission(ROLE_ADMIN)
def delete_member_route(request):
    member_id = request.json.get('id')
    
    # 获取操作者ID和角色
    operator_id, operator_role = get_operator_role(request)
    
    # 不能删除自己
    if member_id == operator_id:
        return Response('{"error": "不能删除自己的账号"}', 400, {'Content-Type': 'application/json'})
    
    # 获取要删除的成员信息
    member = db_members.get_by_id(member_id)
    if not member:
        return Response('{"error": "成员不存在"}', 404, {'Content-Type': 'application/json'})
    
    # 检查要删除的成员是否是超级管理员
    if member.get('role') == 'super_admin':
        return Response('{"error": "超级管理员不能被删除"}', 400, {'Content-Type': 'application/json'})
    
    # 检查是否有权限删除此成员（只能删除比自己权限低的用户）
    allowed, err = can_manage_member(operator_id, operator_role, member_id, member.get('role', 'member'))
    if not allowed:
        return Response(json.dumps({"error": err}), 403, {'Content-Type': 'application/json'})
    
    if db_members.delete(member_id): return {"status": "success"}
    return Response("Error", 500)

@api_route('/api/points/yearly_ranking', methods=['GET'])
def yearly_points_ranking(request):
    """获取年度积分排行榜（最近1年新增积分）"""
    # 计算1年前的时间戳
    t = time.localtime()
    one_year_ago = "{:04d}-{:02d}-{:02d}T00:00:00".format(
        t[0] - 1, t[1], t[2]
    )
    
    # 统计每个成员最近1年的积分变动（流式处理，不加载全部日志）
    member_yearly_points = {}
    for log in db_points_logs.iter_records():
        ts = log.get('timestamp', '')
        if ts >= one_year_ago:
            mid = log.get('member_id')
            change = log.get('change', 0)
            if mid not in member_yearly_points:
                member_yearly_points[mid] = {'points': 0, 'name': log.get('member_name', '')}
            member_yearly_points[mid]['points'] += change
    
    # 获取成员的雅号信息（成员数据量小，可以直接加载）
    member_alias_map = {m.get('id'): m.get('alias', '') for m in db_members.iter_records()}
    
    # 转换为列表并排序，添加雅号字段
    ranking = [
        {
            'member_id': mid, 
            'name': data['name'], 
            'alias': member_alias_map.get(mid, ''),
            'yearly_points': data['points']
        }
        for mid, data in member_yearly_points.items()
    ]
    ranking.sort(key=lambda x: x['yearly_points'], reverse=True)
    
    # 返回前10名
    return ranking[:10]

@api_route('/api/check-token', methods=['GET'])
def check_token_route(request):
    """轻量Token验证接口，用于前端检测Token是否仍然有效"""
    valid, user_id, err_resp = check_token(request)
    if not valid:
        return err_resp
    return {"valid": True, "user_id": user_id}

@api_route('/api/login', methods=['POST'])
def login_route(request):
    data = request.json
    p = data.get('phone')
    pw = data.get('password')
    
    # 必填项验证
    if not p or not pw:
        return Response('{"error": "手机号和密码为必填项"}', 400, {'Content-Type': 'application/json'})
    
    try:
        with open(db_members.filepath, 'r') as f:
            for line in f:
                try:
                    m = json.loads(line)
                    if m.get('phone') == p and verify_password(pw, m.get('password', '')):
                        # 检查维护模式：只允许管理员登录
                        s = get_settings()
                        if s.get('maintenance_mode', False):
                            role = m.get('role', 'member')
                            if role not in ['super_admin', 'admin']:
                                record_login_log(m.get('id'), m.get('name', '未知'), p, 'failed')
                                return Response('{"error": "系统维护中，仅管理员可登录"}', 503, {'Content-Type': 'application/json'})
                        
                        m_safe = m.copy()
                        if 'password' in m_safe: del m_safe['password']
                        # 生成登录Token
                        token, expires_in = generate_token(m.get('id'))
                        m_safe['token'] = token
                        m_safe['expires_in'] = expires_in  # 有效期秒数，前端自行计算过期时间
                        # 记录登录成功日志
                        record_login_log(m.get('id'), m.get('name', '未知'), p, 'success')
                        return m_safe
                except Exception as e:
                    debug(f"解析用户记录失败: {e}", "Login")
    except Exception as e:
        debug(f"读取用户文件失败: {e}", "Login")
    
    # 记录登录失败日志
    record_login_log(None, '未知', p or '', 'failed')
    return Response('Invalid credentials', 401)

@api_route('/api/profile/update', methods=['POST'])
def update_profile(request):
    """更新个人资料（需要登录，只能修改自己的资料）"""
    # 登录验证
    ok, token_user_id, err = check_login(request)
    if not ok:
        return err
    
    data = request.json
    if not data:
        return Response('{"error": "无效的请求数据"}', 400, {'Content-Type': 'application/json'})
    
    user_id = data.get('id')
    
    # 只能修改自己的资料
    if user_id != token_user_id:
        return Response('{"error": "只能修改自己的资料"}', 403, {'Content-Type': 'application/json'})
    
    # 只允许修改有限的字段（alias, birthday）
    allowed_fields = {'alias', 'birthday'}
    update_data = {k: v for k, v in data.items() if k in allowed_fields}
    
    if not update_data:
        return Response('{"error": "没有可更新的字段"}', 400, {'Content-Type': 'application/json'})
    
    # 字段验证
    if 'alias' in update_data:
        valid, err = validate_alias(update_data.get('alias', ''))
        if not valid:
            return Response(json.dumps({"error": err}), 400, {'Content-Type': 'application/json'})
    
    if 'birthday' in update_data:
        valid, err = validate_birthday(update_data.get('birthday', ''))
        if not valid:
            return Response(json.dumps({"error": err}), 400, {'Content-Type': 'application/json'})
    
    # 更新数据库
    def updater(m):
        for k, v in update_data.items():
            m[k] = v
    
    if db_members.update(user_id, updater):
        return {"success": True}
    return Response('{"error": "更新失败"}', 500, {'Content-Type': 'application/json'})

# --- Finance API ---
@api_route('/api/finance', methods=['GET'])
@require_login
def list_finance(request):
    """获取财务记录列表（需要登录）"""
    items, _ = db_finance.fetch_page(1, 100, reverse=True)
    return items

@api_route('/api/finance', methods=['POST'])
@require_permission(ROLE_FINANCE)
def add_finance(request):
    data = request.json
    
    # 必填项验证
    amount = data.get('amount')
    if amount is None or not data.get('summary') or not data.get('handler'):
        return Response('{"error": "金额、摘要和经办人为必填项"}', 400, {'Content-Type': 'application/json'})
    
    data['id'] = db_finance.get_max_id() + 1
    db_finance.append(data)
    return data

@api_route('/api/finance/update', methods=['POST'])
@require_permission(ROLE_FINANCE)
def update_finance(request):
    """更新财务记录"""
    data = request.json
    if not data or 'id' not in data:
        return Response('{"error": "缺少记录ID"}', 400, {'Content-Type': 'application/json'})
    
    # 必填项验证
    amount = data.get('amount')
    if amount is None or not data.get('summary') or not data.get('handler'):
        return Response('{"error": "金额、摘要和经办人为必填项"}', 400, {'Content-Type': 'application/json'})
    
    fid = data.get('id')
    
    def updater(record):
        for k in ['amount', 'summary', 'date', 'type', 'category', 'handler']:
            if k in data:
                record[k] = data[k]
    
    if db_finance.update(fid, updater):
        return {"status": "success"}
    return Response('{"error": "记录不存在"}', 404, {'Content-Type': 'application/json'})

@api_route('/api/finance/delete', methods=['POST'])
@require_permission(ROLE_FINANCE)
def delete_finance(request):
    """删除财务记录"""
    data = request.json
    if not data or 'id' not in data:
        return Response('{"error": "缺少记录ID"}', 400, {'Content-Type': 'application/json'})
    
    fid = data.get('id')
    if db_finance.delete(fid):
        return {"status": "success"}
    return Response('{"error": "记录不存在"}', 404, {'Content-Type': 'application/json'})

# --- Login Logs API ---
@api_route('/api/login_logs', methods=['GET'])
@require_login
def list_login_logs(request):
    """获取登录日志（需要登录）"""
    items, _ = db_login_logs.fetch_page(1, 20, reverse=True)
    return items

# --- Settings ---
@api_route('/api/settings/fields', methods=['GET', 'POST'])
def settings_fields(request):
    s = get_settings()
    if request.method == 'GET':
        return s.get('custom_member_fields', [])
    else:
        # 权限验证：理事级别
        ok, err = check_permission(request, ROLE_DIRECTOR)
        if not ok:
            return err
        # 兼容两种格式：{fields: [...]} 或直接数组 [...]
        data = request.json
        if isinstance(data, list):
            fields = data
        else:
            fields = data.get('fields', [])
        s['custom_member_fields'] = fields
        save_settings(s)
        return {"status": "success"}

@api_route('/api/settings/system', methods=['GET', 'POST'])
def settings_system(request):
    """获取或更新系统基础设置（理事及以上权限）
    包含：系统名称、积分名称、维护模式、龙门阸开关、龙门阸人数上限、缓存大小
    """
    s = get_settings()
    if request.method == 'GET':
        # 公开返回系统基础设置，不返回敏感的salt
        return {
            "system_name": s.get('system_name', '围炉诗社·理事台'),
            "points_name": s.get('points_name', '围炉值'),
            "maintenance_mode": s.get('maintenance_mode', False),
            "allow_guest": s.get('allow_guest', True),
            "chat_enabled": s.get('chat_enabled', True),
            "chat_guest_max": s.get('chat_guest_max', 10),
            "chat_max_users": s.get('chat_max_users', 20),
            "chat_cache_size": s.get('chat_cache_size', 128)
        }
    else:
        data = request.json
        # 修改系统基础设置需要理事权限
        ok, err = check_permission(request, ROLE_DIRECTOR)
        if not ok:
            return err
        if 'system_name' in data:
            sn = data['system_name'].strip() if isinstance(data['system_name'], str) else ''
            if not sn or len(sn) > 32:
                return Response('{"error": "系统名称为必填项且不超过32个字符"}', 400, {'Content-Type': 'application/json'})
            s['system_name'] = sn
        if 'points_name' in data:
            pn = data['points_name'].strip() if isinstance(data['points_name'], str) else ''
            if not pn or len(pn) > 10:
                return Response('{"error": "积分名称为必填项且不超过10个字符"}', 400, {'Content-Type': 'application/json'})
            s['points_name'] = pn
        if 'maintenance_mode' in data:
            s['maintenance_mode'] = bool(data['maintenance_mode'])
        if 'allow_guest' in data:
            s['allow_guest'] = bool(data['allow_guest'])
        if 'chat_enabled' in data:
            s['chat_enabled'] = bool(data['chat_enabled'])
        if 'chat_guest_max' in data:
            guest_max = int(data['chat_guest_max'])
            # 限制范围：0-10人（对应路人甲-癸）
            if guest_max < 0:
                guest_max = 0
            elif guest_max > 10:
                guest_max = 10
            s['chat_guest_max'] = guest_max
        if 'chat_max_users' in data:
            max_users = int(data['chat_max_users'])
            # 限制范围：5-100人
            if max_users < 5:
                max_users = 5
            elif max_users > 100:
                max_users = 100
            s['chat_max_users'] = max_users
        if 'chat_cache_size' in data:
            cache_size = int(data['chat_cache_size'])
            # 限制范围：16-1024KB（考虑PSRAM 2MB限制）
            if cache_size < 16:
                cache_size = 16
            elif cache_size > 1024:
                cache_size = 1024
            s['chat_cache_size'] = cache_size
        save_settings(s)
        return {"status": "success"}

@api_route('/api/settings/salt', methods=['GET', 'POST'])
@require_permission(ROLE_SUPER_ADMIN)
def settings_salt(request):
    """获取或更新密码盐值（超级管理员权限）"""
    s = get_settings()
    if request.method == 'GET':
        return {"password_salt": s.get('password_salt', 'weilu2018')}
    else:
        data = request.json
        new_salt = data.get('password_salt', '').strip() if isinstance(data.get('password_salt', ''), str) else ''
        if not new_salt or len(new_salt) < 32 or len(new_salt) > 1024:
            return Response('{"error": "Salt长度必须为32-1024个字符"}', 400, {'Content-Type': 'application/json'})
        
        # 修改Salt时必须同时提供新的超级管理员密码
        new_pwd = data.get('super_admin_password', '')
        if not new_pwd or len(new_pwd) < 6 or len(new_pwd) > 32:
            return Response('{"error": "请提供新的超级管理员密码（6-32位）"}', 400, {'Content-Type': 'application/json'})
        
        # 先更新Salt
        s['password_salt'] = new_salt
        save_settings(s)
        
        # 用新Salt哈希超级管理员密码并更新
        new_hashed = hash_password(new_pwd)
        def updater(m):
            m['password'] = new_hashed
        db_members.update(1, updater)  # 超级管理员ID固定为1
        gc.collect()
        
        return {"status": "success"}

@api_route('/api/settings/token_expire', methods=['GET', 'POST'])
@require_permission(ROLE_SUPER_ADMIN)
def settings_token_expire(request):
    """获取或更新登录有效期（超级管理员权限）"""
    s = get_settings()
    if request.method == 'GET':
        return {"token_expire_days": s.get('token_expire_days', DEFAULT_TOKEN_EXPIRE_DAYS)}
    else:
        data = request.json
        if 'token_expire_days' in data:
            days = int(data['token_expire_days'])
            # 限制有效期范围：1-365天
            if days < 1:
                days = 1
            elif days > 365:
                days = 365
            s['token_expire_days'] = days
            save_settings(s)
        return {"status": "success"}

# --- WiFi 配置接口 ---
def get_wifi_config():
    """获取WiFi配置"""
    try:
        with open('data/config.json', 'r') as f:
            config = json.load(f)
            # 返回WiFi相关的配置
            return {
                'wifi_ssid': config.get('wifi_ssid', ''),
                'wifi_password': config.get('wifi_password', ''),
                'sta_use_static_ip': config.get('sta_use_static_ip', False),
                'sta_ip': config.get('sta_ip', ''),
                'sta_subnet': config.get('sta_subnet', '255.255.255.0'),
                'sta_gateway': config.get('sta_gateway', ''),
                'sta_dns': config.get('sta_dns', '8.8.8.8'),
                'ap_ssid': config.get('ap_ssid', '围炉诗社小热点'),
                'ap_password': config.get('ap_password', ''),
                'ap_ip': config.get('ap_ip', '192.168.1.68')
            }
    except:
        return {}

def save_wifi_config(data):
    """保存WiFi配置"""
    try:
        # 先读取完整配置
        with open('data/config.json', 'r') as f:
            config = json.load(f)
        
        # 更新WiFi相关配置
        for key in ['wifi_ssid', 'wifi_password', 'sta_use_static_ip', 'sta_ip', 'sta_subnet', 'sta_gateway', 'sta_dns', 'ap_ssid', 'ap_password', 'ap_ip']:
            if key in data:
                config[key] = data[key]
        
        # 保存完整配置
        with open('data/config.json', 'w') as f:
            json.dump(config, f)
        return True
    except:
        return False

@api_route('/api/wifi/config', methods=['GET', 'POST'])
@require_permission(ROLE_ADMIN)
def wifi_config(request):
    """获取或更新WiFi配置（管理员权限）"""
    if request.method == 'GET':
        config = get_wifi_config()
        # 返回配置（密码用星号隐藏）
        return {
            "wifi_ssid": config.get('wifi_ssid', ''),
            "wifi_password": '********' if config.get('wifi_password') else '',
            "sta_use_static_ip": config.get('sta_use_static_ip', False),
            "sta_ip": config.get('sta_ip', ''),
            "sta_subnet": config.get('sta_subnet', '255.255.255.0'),
            "sta_gateway": config.get('sta_gateway', ''),
            "sta_dns": config.get('sta_dns', '8.8.8.8'),
            "ap_ssid": config.get('ap_ssid', '围炉诗社小热点'),
            "ap_password": '********' if config.get('ap_password') else '',
            "ap_ip": config.get('ap_ip', '192.168.1.68')
        }
    else:
        data = request.json
        
        # 后端数据校验
        wifi_ssid = data.get('wifi_ssid', '')
        if not wifi_ssid or len(wifi_ssid) > 32:
            return Response('{"error": "WiFi名称为必填项且不超过32字符"}', 400, {'Content-Type': 'application/json'})
        
        wifi_pwd = data.get('wifi_password', '')
        if wifi_pwd and wifi_pwd != '********' and (len(wifi_pwd) < 8 or len(wifi_pwd) > 63):
            return Response('{"error": "WiFi密码长度必须为8-63个字符"}', 400, {'Content-Type': 'application/json'})
        
        ap_ssid = data.get('ap_ssid', '')
        if ap_ssid and len(ap_ssid) > 32:
            return Response('{"error": "热点名称不能超过32个字符"}', 400, {'Content-Type': 'application/json'})
        
        ap_pwd = data.get('ap_password', '')
        if ap_pwd and ap_pwd != '********' and (len(ap_pwd) < 8 or len(ap_pwd) > 63):
            return Response('{"error": "热点密码长度必须为8-63个字符"}', 400, {'Content-Type': 'application/json'})
        
        # IPv4格式校验辅助函数
        def _valid_ipv4(ip):
            parts = ip.split('.')
            if len(parts) != 4:
                return False
            for p in parts:
                if not p.isdigit() or int(p) < 0 or int(p) > 255:
                    return False
            return True
        
        # 静态IP模式下校验IP字段
        if data.get('sta_use_static_ip'):
            for field, label in [('sta_ip', 'IP地址'), ('sta_subnet', '子网掩码'), ('sta_gateway', '网关'), ('sta_dns', 'DNS')]:
                val = data.get(field, '')
                if not val:
                    return Response('{"error": "静态IP模式下%s为必填项"}' % label, 400, {'Content-Type': 'application/json'})
                if not _valid_ipv4(val):
                    return Response('{"error": "%s格式不正确"}' % label, 400, {'Content-Type': 'application/json'})
        
        # AP IP格式校验
        ap_ip = data.get('ap_ip', '')
        if ap_ip and not _valid_ipv4(ap_ip):
            return Response('{"error": "AP模式IP地址格式不正确"}', 400, {'Content-Type': 'application/json'})
        
        config = get_wifi_config()
        
        # 更新WiFi STA配置
        if 'wifi_ssid' in data:
            config['wifi_ssid'] = data['wifi_ssid']
        if 'wifi_password' in data and data['wifi_password'] != '********':
            config['wifi_password'] = data['wifi_password']
        
        # 更新静态IP配置
        if 'sta_use_static_ip' in data:
            config['sta_use_static_ip'] = data['sta_use_static_ip']
        if 'sta_ip' in data:
            config['sta_ip'] = data['sta_ip']
        if 'sta_subnet' in data:
            config['sta_subnet'] = data['sta_subnet']
        if 'sta_gateway' in data:
            config['sta_gateway'] = data['sta_gateway']
        if 'sta_dns' in data:
            config['sta_dns'] = data['sta_dns']
        
        # 更新AP配置
        if 'ap_ssid' in data:
            config['ap_ssid'] = data['ap_ssid']
        if 'ap_password' in data and data['ap_password'] != '********':
            config['ap_password'] = data['ap_password']
        if 'ap_ip' in data:
            config['ap_ip'] = data['ap_ip']
        
        if save_wifi_config(config):
            return {"status": "success", "message": "WiFi配置已保存，重启后生效"}
        else:
            return Response('{"error": "保存失败"}', 500, {'Content-Type': 'application/json'})

@api_route('/api/system/info')
@require_login
def sys_info(request):
    """获取系统信息（登录用户可查看）"""
    try:
        gc.collect()
        s = os.statvfs('/')
        free_ram = gc.mem_free()
        # 尝试获取总内存，若无法获取则默认2048KB
        try:
            total_ram = gc.mem_free() + gc.mem_alloc()
        except:
            total_ram = 2048 * 1024  # 默认2048KB
        
        # 计算系统运行时间
        uptime_seconds = int(time.time() - _system_start_time)
        uptime_hours = uptime_seconds // 3600
        uptime_minutes = (uptime_seconds % 3600) // 60
        uptime_secs = uptime_seconds % 60
        
        # 获取系统时间
        t = time.localtime()
        system_time = "{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(
            t[0], t[1], t[2], t[3], t[4], t[5]
        )
        
        # 获取WiFi信号强度和模式
        wifi_rssi = None
        wifi_ssid = None
        wifi_mode = None  # 'STA' 或 'AP'（兼容旧逻辑）
        sta_active = False  # STA模式是否激活并连接
        ap_active = False   # AP模式是否激活
        try:
            wlan_sta = network.WLAN(network.STA_IF)
            wlan_ap = network.WLAN(network.AP_IF)
            
            # 检测STA模式
            if wlan_sta.active() and wlan_sta.isconnected():
                sta_active = True
                wifi_mode = 'STA'
                wifi_rssi = wlan_sta.status('rssi')
                wifi_ssid = wlan_sta.config('essid')
            
            # 检测AP模式（独立检测，不是elif）
            if wlan_ap.active():
                ap_active = True
                if wifi_mode is None:
                    wifi_mode = 'AP'
                    wifi_ssid = wlan_ap.config('essid')
        except Exception as e:
            debug(f"获取WiFi信息失败: {e}", "System")
        
        # 尝试获取CPU温度
        cpu_temp = None
        try:
            import esp32
            # ESP32-S2/S3/C3/C6 使用 mcu_temperature()，直接返回摄氏度
            cpu_temp = esp32.mcu_temperature()
        except Exception as e:
            debug(f"获取CPU温度失败: {e}", "System")
        
        return {
            "platform": "ESP32-S2",
            "free_storage": s[0]*s[3],
            "total_storage": s[0]*s[2],
            "free_ram": free_ram,
            "total_ram": total_ram,
            "uptime": f"{uptime_hours}h {uptime_minutes}m {uptime_secs}s",
            "uptime_seconds": uptime_seconds,
            "system_time": system_time,
            "wifi_rssi": wifi_rssi,
            "wifi_ssid": wifi_ssid,
            "wifi_mode": wifi_mode,
            "sta_active": sta_active,
            "ap_active": ap_active,
            "cpu_temp": cpu_temp
        }
    except Exception as e:
        debug(f"获取系统信息失败: {e}", "System")
        return {}

@api_route('/api/system/stats')
@require_login
def sys_stats(request):
    """获取各模块数据统计（登录用户可查看）"""
    try:
        return {
            "members": db_members.count(),
            "poems": db_poems.count(),
            "activities": db_activities.count(),
            "tasks": db_tasks.count(),
            "finance": db_finance.count()
        }
    except Exception as e:
        error(f"获取统计数据失败: {e}", "Stats")
        return {}

@api_route('/api/backup/export')
@require_permission(ROLE_SUPER_ADMIN)
def backup_export(request):
    """导出全站数据备份（管理员权限）"""
    try:
        # 获取WiFi配置（包含密码）
        wifi_config = get_wifi_config()
        wifi_backup = {
            "wifi_ssid": wifi_config.get('wifi_ssid', ''),
            "wifi_password": wifi_config.get('wifi_password', ''),
            "sta_use_static_ip": wifi_config.get('sta_use_static_ip', False),
            "sta_ip": wifi_config.get('sta_ip', ''),
            "sta_subnet": wifi_config.get('sta_subnet', '255.255.255.0'),
            "sta_gateway": wifi_config.get('sta_gateway', ''),
            "sta_dns": wifi_config.get('sta_dns', '8.8.8.8'),
            "ap_ssid": wifi_config.get('ap_ssid', ''),
            "ap_password": wifi_config.get('ap_password', ''),
            "ap_ip": wifi_config.get('ap_ip', '192.168.1.68')
        }
        
        # 获取系统配置（debug_mode, watchdog配置）
        system_config = {}
        try:
            with open('data/config.json', 'r') as f:
                config = json.load(f)
                system_config = {
                    "debug_mode": config.get('debug_mode', False),
                    "watchdog_enabled": config.get('watchdog_enabled', True),
                    "watchdog_timeout": config.get('watchdog_timeout', 120)
                }
        except:
            system_config = {"debug_mode": False, "watchdog_enabled": True, "watchdog_timeout": 120}
        
        backup_data = {
            "version": "1.0",
            "data": {
                "members": db_members.get_all(),
                "poems": db_poems.get_all(),
                "activities": db_activities.get_all(),
                "tasks": db_tasks.get_all(),
                "finance": db_finance.get_all(),
                "points_logs": db_points_logs.get_all(),
                "login_logs": db_login_logs.get_all(),
                "settings": get_settings(),
                "wifi_config": wifi_backup,
                "system_config": system_config
            }
        }
        gc.collect()
        return backup_data
    except Exception as e:
        error(f"备份导出失败: {e}", "Backup")
        return Response('{"error": "导出失败"}', 500, {'Content-Type': 'application/json'})

@api_route('/api/backup/import', methods=['POST'])
@require_permission(ROLE_SUPER_ADMIN)
def backup_import(request):
    """导入数据备份（管理员权限）"""
    try:
        # 喂狗，防止处理大数据时超时
        watchdog.feed()
        gc.collect()  # 解析前释放内存
        
        backup = request.json
        # 如果 request.json 为空（大文件跳过了自动解析），手动解析
        if not backup and request.body:
            gc.collect()  # 解析前再次释放内存
            watchdog.feed()
            try:
                backup = json.loads(request.body)
                debug(f"备份导入: 手动解析JSON成功, 大小={len(request.body)}", "Backup")
            except Exception as parse_err:
                debug(f"备份导入: 手动解析JSON失败: {parse_err}, body长度={len(request.body)}", "Backup")
                return Response('{"error": "JSON解析失败，文件可能过大或格式错误"}', 400, {'Content-Type': 'application/json'})
        
        # 详细的错误诊断
        if not backup:
            body_len = len(request.body) if request.body else 0
            debug(f"备份导入失败: backup为空, body长度={body_len}", "Backup")
            return Response('{"error": "无法解析备份数据，请检查文件格式"}', 400, {'Content-Type': 'application/json'})
        if 'version' not in backup:
            return Response('{"error": "备份文件缺少版本信息"}', 400, {'Content-Type': 'application/json'})
        if 'data' not in backup:
            return Response('{"error": "备份文件缺少数据内容"}', 400, {'Content-Type': 'application/json'})
        
        data = backup['data']
        
        # 逐个恢复数据，每个数据类型处理后释放内存并喂狗
        if 'members' in data:
            with open('data/members.jsonl', 'w') as f:
                for item in data['members']:
                    f.write(json.dumps(item) + "\n")
            data['members'] = None  # 释放内存
            gc.collect()
            watchdog.feed()
        
        if 'poems' in data:
            with open('data/poems.jsonl', 'w') as f:
                for item in data['poems']:
                    f.write(json.dumps(item) + "\n")
            data['poems'] = None
            gc.collect()
            watchdog.feed()
        
        if 'activities' in data:
            with open('data/activities.jsonl', 'w') as f:
                for item in data['activities']:
                    f.write(json.dumps(item) + "\n")
            data['activities'] = None
            gc.collect()
            watchdog.feed()
        
        if 'tasks' in data:
            with open('data/tasks.jsonl', 'w') as f:
                for item in data['tasks']:
                    f.write(json.dumps(item) + "\n")
            data['tasks'] = None
            gc.collect()
            watchdog.feed()
        
        if 'finance' in data:
            with open('data/finance.jsonl', 'w') as f:
                for item in data['finance']:
                    f.write(json.dumps(item) + "\n")
            data['finance'] = None
            gc.collect()
            watchdog.feed()
        
        if 'points_logs' in data:
            with open('data/points_logs.jsonl', 'w') as f:
                for item in data['points_logs']:
                    f.write(json.dumps(item) + "\n")
            data['points_logs'] = None
            gc.collect()
            watchdog.feed()
        
        if 'login_logs' in data:
            with open('data/login_logs.jsonl', 'w') as f:
                for item in data['login_logs']:
                    f.write(json.dumps(item) + "\n")
            data['login_logs'] = None
            gc.collect()
            watchdog.feed()
        
        if 'settings' in data:
            # 从配置文件读取完整的配置
            with open('data/config.json', 'r') as f:
                config = json.load(f)
            
            # 合并设置数据
            settings_data = data['settings']
            for key in ['custom_member_fields', 'password_salt', 'points_name', 'system_name']:
                if key in settings_data:
                    config[key] = settings_data[key]
            
            # 保存回配置文件
            with open('data/config.json', 'w') as f:
                json.dump(config, f)
            data['settings'] = None
            gc.collect()
            watchdog.feed()
        
        # 恢复WiFi配置（包含密码）
        if 'wifi_config' in data:
            existing_config = get_wifi_config()
            new_config = data['wifi_config']
            # 更新所有WiFi配置包括密码
            existing_config['wifi_ssid'] = new_config.get('wifi_ssid', existing_config.get('wifi_ssid', ''))
            if 'wifi_password' in new_config and new_config['wifi_password']:
                existing_config['wifi_password'] = new_config['wifi_password']
            existing_config['sta_use_static_ip'] = new_config.get('sta_use_static_ip', False)
            existing_config['sta_ip'] = new_config.get('sta_ip', '')
            existing_config['sta_subnet'] = new_config.get('sta_subnet', '255.255.255.0')
            existing_config['sta_gateway'] = new_config.get('sta_gateway', '')
            existing_config['sta_dns'] = new_config.get('sta_dns', '8.8.8.8')
            existing_config['ap_ssid'] = new_config.get('ap_ssid', existing_config.get('ap_ssid', ''))
            if 'ap_password' in new_config and new_config['ap_password']:
                existing_config['ap_password'] = new_config['ap_password']
            existing_config['ap_ip'] = new_config.get('ap_ip', '192.168.1.68')
            save_wifi_config(existing_config)
            data['wifi_config'] = None
            gc.collect()
            watchdog.feed()
        
        # 恢复系统配置（debug_mode, watchdog配置）
        if 'system_config' in data:
            try:
                with open('data/config.json', 'r') as f:
                    config = json.load(f)
                sys_cfg = data['system_config']
                for key in ['debug_mode', 'watchdog_enabled', 'watchdog_timeout']:
                    if key in sys_cfg:
                        config[key] = sys_cfg[key]
                with open('data/config.json', 'w') as f:
                    json.dump(config, f)
            except Exception as e:
                debug(f"恢复系统配置失败: {e}", "Backup")
            data['system_config'] = None
            gc.collect()
            watchdog.feed()
        
        # 最终清理
        backup = None
        data = None
        gc.collect()
        return {"status": "success", "message": "数据恢复成功"}
    except Exception as e:
        error(f"备份导入失败: {e}", "Backup")
        return Response('{"error": "导入失败"}', 500, {'Content-Type': 'application/json'})

# --- 分表备份API（支持大数据量） ---
# 数据表映射
BACKUP_TABLES = {
    'members': db_members,
    'poems': db_poems,
    'activities': db_activities,
    'tasks': db_tasks,
    'finance': db_finance,
    'points_logs': db_points_logs,
    'login_logs': db_login_logs
}

@api_route('/api/backup/tables')
@require_permission(ROLE_SUPER_ADMIN)
def backup_list_tables(request):
    """获取可备份的表列表（管理员权限）"""
    return {"tables": list(BACKUP_TABLES.keys()) + ['settings', 'wifi_config', 'system_config']}

@api_route('/api/backup/export-table')
@require_permission(ROLE_SUPER_ADMIN)
def backup_export_table(request):
    """分表导出（管理员权限）
    查询参数：name=表名, page=页码(可选), limit=每页条数(可选,默认100)
    返回：{table, data, page, total, hasMore}
    """
    # 获取表名
    table = request.args.get('name', '')
    if not table:
        return Response('{"error": "未指定表名"}', 400, {'Content-Type': 'application/json'})
    
    # 获取分页参数
    page = int(request.args.get('page', 1))
    limit = int(request.args.get('limit', 100))
    
    watchdog.feed()
    gc.collect()
    
    try:
        if table in BACKUP_TABLES:
            # JSONL 数据表 - 使用分页读取避免内存溢出
            data, total = BACKUP_TABLES[table].fetch_page(page=page, limit=limit, reverse=False)
            gc.collect()
            has_more = (page * limit) < total
            return {"table": table, "data": data, "page": page, "total": total, "hasMore": has_more}
        
        elif table == 'settings':
            return {"table": table, "data": get_settings(), "page": 1, "total": 1, "hasMore": False}
        
        elif table == 'wifi_config':
            wifi_config = get_wifi_config()
            return {"table": table, "data": {
                "wifi_ssid": wifi_config.get('wifi_ssid', ''),
                "wifi_password": wifi_config.get('wifi_password', ''),
                "sta_use_static_ip": wifi_config.get('sta_use_static_ip', False),
                "sta_ip": wifi_config.get('sta_ip', ''),
                "sta_subnet": wifi_config.get('sta_subnet', '255.255.255.0'),
                "sta_gateway": wifi_config.get('sta_gateway', ''),
                "sta_dns": wifi_config.get('sta_dns', '8.8.8.8'),
                "ap_ssid": wifi_config.get('ap_ssid', ''),
                "ap_password": wifi_config.get('ap_password', ''),
                "ap_ip": wifi_config.get('ap_ip', '192.168.1.68')
            }, "page": 1, "total": 1, "hasMore": False}
        
        elif table == 'system_config':
            try:
                with open('data/config.json', 'r') as f:
                    config = json.load(f)
                return {"table": table, "data": {
                    "debug_mode": config.get('debug_mode', False),
                    "watchdog_enabled": config.get('watchdog_enabled', True),
                    "watchdog_timeout": config.get('watchdog_timeout', 120)
                }, "page": 1, "total": 1, "hasMore": False}
            except:
                return {"table": table, "data": {"debug_mode": False, "watchdog_enabled": True, "watchdog_timeout": 120}, "page": 1, "total": 1, "hasMore": False}
        
        else:
            return Response('{"error": "未知的表名"}', 400, {'Content-Type': 'application/json'})
    
    except Exception as e:
        error(f"分表导出失败 [{table}]: {e}", "Backup")
        return Response(f'{{"error": "导出失败: {str(e)}"}}', 500, {'Content-Type': 'application/json'})

@api_route('/api/backup/import-table', methods=['POST'])
@require_permission(ROLE_SUPER_ADMIN)
def backup_import_table(request):
    """分表导入（管理员权限）
    查询参数：name=表名
    """
    # 获取表名
    table = request.args.get('name', '')
    info(f"分表导入请求: table={table}", "Backup")
    
    if not table:
        return Response('{"error": "未指定表名"}', 400, {'Content-Type': 'application/json'})
    
    watchdog.feed()
    gc.collect()
    
    try:
        data = request.json
        # 如果 request.json 为空，尝试手动解析（大请求体跳过了自动解析）
        if not data and request.body:
            try:
                # 确保是字符串类型（MicroPython的json.loads可能不支持bytes）
                body_str = request.body
                if isinstance(body_str, bytes):
                    body_str = body_str.decode('utf-8')
                data = json.loads(body_str)
            except Exception as parse_err:
                error(f"分表导入 [{table}]: JSON解析失败 - {parse_err}", "Backup")
                return Response('{"error": "JSON解析失败"}', 400, {'Content-Type': 'application/json'})
        
        if not data or 'data' not in data:
            error(f"分表导入 [{table}]: 缺少data字段", "Backup")
            return Response('{"error": "缺少数据内容"}', 400, {'Content-Type': 'application/json'})
        
        table_data = data['data']
        # 获取导入模式：overwrite(覆盖,默认) 或 append(追加,用于分批导入)
        mode = request.args.get('mode', 'overwrite')
        info(f"分表导入 [{table}]: 开始处理, 记录数={len(table_data) if isinstance(table_data, list) else 'N/A'}, 模式={mode}", "Backup")
        
        if table in BACKUP_TABLES:
            # JSONL 数据表 - 根据模式选择写入方式
            filepath = f'data/{table}.jsonl'
            file_mode = 'w' if mode == 'overwrite' else 'a'
            with open(filepath, file_mode) as f:
                for item in table_data:
                    f.write(json.dumps(item) + "\n")
            gc.collect()
            watchdog.feed()
            info(f"分表导入 [{table}]: 成功写入 {len(table_data)} 条记录", "Backup")
            return {"status": "success", "table": table, "count": len(table_data)}
        
        elif table == 'settings':
            # 从配置文件读取完整的配置
            with open('data/config.json', 'r') as f:
                config = json.load(f)
            # 合并设置数据
            for key in ['custom_member_fields', 'password_salt', 'points_name', 'system_name']:
                if key in table_data:
                    config[key] = table_data[key]
            with open('data/config.json', 'w') as f:
                json.dump(config, f)
            gc.collect()
            return {"status": "success", "table": table}
        
        elif table == 'wifi_config':
            existing_config = get_wifi_config()
            existing_config['wifi_ssid'] = table_data.get('wifi_ssid', existing_config.get('wifi_ssid', ''))
            if 'wifi_password' in table_data and table_data['wifi_password']:
                existing_config['wifi_password'] = table_data['wifi_password']
            existing_config['sta_use_static_ip'] = table_data.get('sta_use_static_ip', False)
            existing_config['sta_ip'] = table_data.get('sta_ip', '')
            existing_config['sta_subnet'] = table_data.get('sta_subnet', '255.255.255.0')
            existing_config['sta_gateway'] = table_data.get('sta_gateway', '')
            existing_config['sta_dns'] = table_data.get('sta_dns', '8.8.8.8')
            existing_config['ap_ssid'] = table_data.get('ap_ssid', existing_config.get('ap_ssid', ''))
            if 'ap_password' in table_data and table_data['ap_password']:
                existing_config['ap_password'] = table_data['ap_password']
            existing_config['ap_ip'] = table_data.get('ap_ip', '192.168.1.68')
            save_wifi_config(existing_config)
            gc.collect()
            return {"status": "success", "table": table}
        
        elif table == 'system_config':
            with open('data/config.json', 'r') as f:
                config = json.load(f)
            for key in ['debug_mode', 'watchdog_enabled', 'watchdog_timeout']:
                if key in table_data:
                    config[key] = table_data[key]
            with open('data/config.json', 'w') as f:
                json.dump(config, f)
            gc.collect()
            return {"status": "success", "table": table}
        
        else:
            return Response('{"error": "未知的表名"}', 400, {'Content-Type': 'application/json'})
    
    except Exception as e:
        error(f"分表导入失败 [{table}]: {e}", "Backup")
        return Response(f'{{"error": "导入失败: {str(e)}"}}', 500, {'Content-Type': 'application/json'})

# ============================================================================
# 聊天室 - 内存缓存消息系统
# ============================================================================

# 聊天室配置
CHAT_MAX_SIZE_DEFAULT = 128 * 1024  # 默认128KB 最大消息缓存
CHAT_MSG_MAX_CHARS = 1024   # 单条消息最大字符数
CHAT_GUEST_MAX_DEFAULT = 10 # 默认最大游客数量
CHAT_GUEST_EXPIRE = 3600    # 游客昵称使用时长（秒）= 1小时
CHAT_GUEST_NAMES = ['路人甲', '路人乙', '路人丙', '路人丁', '路人戊', 
                    '路人己', '路人庚', '路人辛', '路人壬', '路人癸']

def get_chat_max_size():
    """获取聊天室缓存大小配置（KB转字节）"""
    s = get_settings()
    return s.get('chat_cache_size', 128) * 1024

def get_chat_guest_max():
    """获取龙门阵游客上限配置"""
    s = get_settings()
    return s.get('chat_guest_max', 10)

# 内存缓存数据结构
_chat_messages = []       # 消息列表: [{id, user_id, user_name, content, timestamp}, ...]
_chat_users = {}          # 在线用户: {user_id: user_name, ...}
_chat_guests = {}         # 游客映射: {guest_id: {'name': ..., 'expire': timestamp}, ...}
_chat_current_size = 0    # 当前消息占用字节数
_chat_msg_id = 0          # 消息ID计数器

def _estimate_msg_size(msg):
    """估算单条消息占用的内存大小"""
    return len(json.dumps(msg))

def _chat_cleanup():
    """清理过期消息，保持总大小在限制内"""
    global _chat_messages, _chat_current_size, _chat_users, _chat_guests
    
    max_size = get_chat_max_size()
    # 删除最早的消息直到空间足够
    while _chat_current_size > max_size and _chat_messages:
        old_msg = _chat_messages.pop(0)
        _chat_current_size -= _estimate_msg_size(old_msg)
        
        # 检查该用户是否还有消息
        user_id = old_msg.get('user_id')
        has_other_msg = any(m.get('user_id') == user_id for m in _chat_messages)
        
        if not has_other_msg:
            # 移除用户在线状态
            if user_id in _chat_users:
                del _chat_users[user_id]
            if user_id in _chat_guests:
                del _chat_guests[user_id]
    
    gc.collect()

def _get_member_display_name(member_id):
    """获取成员显示名称（优先雅号）"""
    try:
        with open(db_members.filepath, 'r') as f:
            for line in f:
                m = json.loads(line)
                if m.get('id') == member_id:
                    return m.get('alias') or m.get('name') or '未知'
    except:
        pass
    return '未知'

def _allocate_guest_name():
    """分配一个可用的游客昵称，返回 (guest_id, guest_name) 或 (None, None)"""
    global _chat_guests
    
    # 检查游客上限配置
    guest_max = get_chat_guest_max()
    if guest_max <= 0:
        return None, None  # 不允许游客
    
    now = int(time.time())
    
    # 先清理过期的游客
    expired_ids = [gid for gid, info in _chat_guests.items() 
                   if info.get('expire', 0) < now]
    for gid in expired_ids:
        del _chat_guests[gid]
    
    # 检查当前游客数量是否已达上限
    if len(_chat_guests) >= guest_max:
        return None, None
    
    # 查找可用的昵称（仅在配置范围内）
    used_names = set(info.get('name') for info in _chat_guests.values())
    for i, name in enumerate(CHAT_GUEST_NAMES[:guest_max]):
        if name not in used_names:
            guest_id = -(i + 1)  # 负数ID标识游客
            return guest_id, name
    return None, None

def _get_guest_name(guest_id):
    """获取游客昵称"""
    info = _chat_guests.get(guest_id)
    if info:
        return info.get('name')
    return None

@api_route('/api/chat/messages', methods=['GET'])
def chat_get_messages(request):
    """获取聊天消息（支持增量获取）"""
    try:
        after_id = int(request.args.get('after', 0))
        # 返回指定ID之后的消息
        if after_id > 0:
            messages = [m for m in _chat_messages if m.get('id', 0) > after_id]
        else:
            messages = list(_chat_messages)  # 返回所有消息
        return messages
    except Exception as e:
        error(f"获取聊天消息失败: {e}", "Chat")
        return []

@api_route('/api/chat/users', methods=['GET'])
def chat_get_users(request):
    """获取当前在线用户列表"""
    now = int(time.time())
    # 合并登录用户和游客（过滤过期游客）
    users = []
    for uid, name in _chat_users.items():
        users.append({'id': uid, 'name': name, 'is_guest': False})
    for uid, info in _chat_guests.items():
        if info.get('expire', 0) >= now:
            users.append({'id': uid, 'name': info.get('name'), 'is_guest': True})
    return users

@api_route('/api/chat/join', methods=['POST'])
def chat_join(request):
    """加入聊天室（游客自动分配昵称，有效期1小时）"""
    global _chat_users, _chat_guests
    
    # 检查聊天室是否开启
    s = get_settings()
    if not s.get('chat_enabled', True):
        return Response('{"error": "龙门阵已关闭"}', 403, {'Content-Type': 'application/json'})
    
    data = request.json or {}
    
    # 检查是否登录用户
    user_id, role = get_operator_role(request)
    
    # 公共人数限制检查（登录用户和游客都需要检查）
    max_users = s.get('chat_max_users', 20)
    now = int(time.time())
    active_guests = sum(1 for info in _chat_guests.values() if info.get('expire', 0) >= now)
    current_users = len(_chat_users) + active_guests
    
    if user_id:
        # 登录用户：检查是否已在聊天室（已在则不重复计数）
        if user_id not in _chat_users:
            # 新用户加入，检查人数限制
            if current_users >= max_users:
                return Response('{"error": "龙门阵人数已满，请稍后再试"}', 403, {'Content-Type': 'application/json'})
        # 登录用户，使用真实名称
        display_name = _get_member_display_name(user_id)
        _chat_users[user_id] = display_name
        return {'user_id': user_id, 'user_name': display_name, 'is_guest': False}
    else:
        # 游客：检查人数限制
        if current_users >= max_users:
            return Response('{"error": "龙门阵人数已满，请稍后再试"}', 403, {'Content-Type': 'application/json'})
        
        # 游客，自动分配昵称
        guest_id, guest_name = _allocate_guest_name()
        if guest_id is None:
            return Response('{"error": "游客位置已满，请稍后再试"}', 403, {'Content-Type': 'application/json'})
        
        # 记录游客信息，设置过期时间
        _chat_guests[guest_id] = {
            'name': guest_name,
            'expire': int(time.time()) + CHAT_GUEST_EXPIRE
        }
        return {'user_id': guest_id, 'user_name': guest_name, 'is_guest': True}

@api_route('/api/chat/send', methods=['POST'])
def chat_send_message(request):
    """发送聊天消息"""
    global _chat_messages, _chat_current_size, _chat_msg_id, _chat_users, _chat_guests
    
    # 检查聊天室是否开启
    s = get_settings()
    if not s.get('chat_enabled', True):
        return Response('{"error": "龙门阵已关闭"}', 403, {'Content-Type': 'application/json'})
    
    data = request.json or {}
    content = data.get('content', '').strip()
    request_user_id = data.get('user_id')  # 前端传来的用户ID
    
    if not content:
        return Response('{"error": "消息内容不能为空"}', 400, {'Content-Type': 'application/json'})
    
    # 检查消息字符数限制
    if len(content) > CHAT_MSG_MAX_CHARS:
        return Response('{"error": "消息过长，最多1024个字符"}', 400, {'Content-Type': 'application/json'})
    
    # 验证发送者身份
    sender_id = None
    user_name = None
    is_guest = False
    
    # 严格鉴权：先检查Token获取登录用户身份
    token_user_id, _ = get_operator_role(request)
    
    if token_user_id:
        # 已登录用户：只使用Token中的身份，忽略请求体中的user_id，防止冒充
        sender_id = token_user_id
        user_name = _chat_users.get(sender_id) or _get_member_display_name(sender_id)
        _chat_users[sender_id] = user_name
    elif request_user_id and request_user_id < 0:
        # 游客：验证游客身份（负数ID）
        sender_id = request_user_id
        if sender_id not in _chat_guests:
            return Response('{"error": "请先加入龙门阵"}', 401, {'Content-Type': 'application/json'})
        guest_info = _chat_guests[sender_id]
        # 检查是否过期
        if guest_info.get('expire', 0) < int(time.time()):
            del _chat_guests[sender_id]
            return Response('{"error": "昵称已过期，请重新加入"}', 401, {'Content-Type': 'application/json'})
        user_name = guest_info.get('name')
        is_guest = True
    elif request_user_id and request_user_id > 0:
        # 请求体中包含正数user_id但无有效Token：拒绝，防止冒充登录用户
        return Response('{"error": "登录已过期，请重新登录"}', 401, {'Content-Type': 'application/json'})
    else:
        return Response('{"error": "请先加入聊天室"}', 401, {'Content-Type': 'application/json'})
    
    # 构建消息
    _chat_msg_id += 1
    msg = {
        'id': _chat_msg_id,
        'user_id': sender_id,
        'user_name': user_name,
        'content': content,
        'timestamp': int(time.time()),
        'is_guest': is_guest
    }
    
    # 添加消息并更新大小
    msg_size = _estimate_msg_size(msg)
    _chat_messages.append(msg)
    _chat_current_size += msg_size
    
    # 检查并清理超限消息
    _chat_cleanup()
    
    return msg

@api_route('/api/chat/leave', methods=['POST'])
def chat_leave(request):
    """离开聊天室"""
    global _chat_users, _chat_guests
    
    data = request.json or {}
    user_id = data.get('user_id')
    
    # 也检查Token
    token_user_id, _ = get_operator_role(request)
    if token_user_id:
        user_id = token_user_id
    
    if user_id in _chat_users:
        del _chat_users[user_id]
    if user_id in _chat_guests:
        del _chat_guests[user_id]
    
    return {'status': 'success'}

@api_route('/api/chat/status', methods=['GET'])
def chat_status(request):
    """获取聊天室状态（内存使用、用户数等）"""
    now = int(time.time())
    s = get_settings()
    # 计算未过期的游客数量
    active_guests = sum(1 for info in _chat_guests.values() if info.get('expire', 0) >= now)
    max_users = s.get('chat_max_users', 20)
    guest_max = get_chat_guest_max()
    return {
        'memory_used': _chat_current_size,
        'memory_limit': get_chat_max_size(),
        'message_count': len(_chat_messages),
        'user_count': len(_chat_users) + active_guests,
        'max_users': max_users,
        'guest_count': active_guests,
        'guest_available': guest_max - active_guests,
        'guest_max': guest_max,
        'chat_enabled': s.get('chat_enabled', True)
    }

if __name__ == '__main__':
    try:
        info("正在启动 Microdot Web服务...", "System")
        print_system_status()
        watchdog.feed()  # 启动前喂狗
        start_watchdog_timer()  # 启动定时喂狗器，防止空闲超时
        app.run(port=80, debug=log.is_debug)
    except KeyboardInterrupt:
        info("收到中断信号，正在停止服务...", "System")
    except Exception as e:
        error(f"Web服务启动失败: {e}", "System")
    finally:
        # 确保退出时停止定时器
        stop_watchdog_timer()
        status_led.stop()
        info("服务已停止", "System")
