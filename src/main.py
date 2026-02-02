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

def api_route(url, methods=['GET']):
    """
    API路由装饰器，包装原生route装饰器
    在API请求处理完成后自动触发LED快闪和看门狗喂狗
    """
    def decorator(f):
        def wrapper(request):
            watchdog.feed()  # 每次API请求时喂狗
            result = f(request)
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
            # Debug log removed to reduce serial clutter
            results = []
            try:
                with open(self.filepath, 'r') as f:
                    for line in f:
                        if not line.strip(): continue
                        try:
                            obj = json.loads(line)
                            
                            found = False
                            # Search all values
                            for k, v in obj.items():
                                # Optional: Limit search fields if needed
                                val_str = str(v).lower()
                                if search_lower in val_str:
                                    found = True
                                    break
                            
                            if found:
                                results.append(obj)
                        except Exception as e:
                            debug(f"搜索解析记录失败: {e}", "DB")
            except Exception as e:
                debug(f"搜索文件读取失败: {e}", "DB")
            
            if reverse:
                results.reverse()
                
            total = len(results)
            start_idx = (page - 1) * limit
            return results[start_idx : start_idx + limit], total

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
ROLE_ADMIN = ['super_admin', 'admin']  # 管理员级别：超管、管理员
ROLE_DIRECTOR = ['super_admin', 'admin', 'director']  # 理事级别：超管、管理员、理事
ROLE_FINANCE = ['super_admin', 'admin', 'finance']  # 财务级别：超管、管理员、财务

# 角色权限层级（数字越小权限越高）
ROLE_LEVEL = {
    'super_admin': 0,
    'admin': 1,
    'director': 2,
    'finance': 2,
    'member': 3
}

def can_assign_role(operator_role, target_role):
    """
    检查操作者是否可以分配目标角色
    返回: (allowed: bool, error_message: str|None)
    """
    # 禁止通过API添加超级管理员
    if target_role == 'super_admin':
        return False, '不能通过此方式添加超级管理员'
    
    operator_level = ROLE_LEVEL.get(operator_role, 3)
    target_level = ROLE_LEVEL.get(target_role, 3)
    
    # 非超级管理员不能分配比自己权限高或相同的角色
    if operator_role != 'super_admin' and target_level <= operator_level:
        return False, '不能添加与自己权限相同或更高的角色'
    
    return True, None

def get_operator_role(request):
    """
    从请求中获取操作者角色
    请求体中需包含 operator_id 字段
    返回: (operator_id, role) 或 (None, None)
    """
    try:
        data = request.json if request.json else {}
        operator_id = data.get('operator_id')
        if not operator_id:
            return None, None
        
        # 确保 operator_id 是整数类型（前端可能传递字符串）
        try:
            operator_id = int(operator_id)
        except (ValueError, TypeError):
            return None, None
        
        # 从数据库查询用户角色
        with open(db_members.filepath, 'r') as f:
            for line in f:
                try:
                    m = json.loads(line)
                    if m.get('id') == operator_id:
                        return operator_id, m.get('role', 'member')
                except:
                    pass
    except Exception as e:
        debug(f"获取操作者角色失败: {e}", "Auth")
    return None, None

def check_permission(request, allowed_roles):
    """
    检查请求者是否具有指定权限
    allowed_roles: 允许的角色列表
    返回: (通过, 错误响应或None)
    """
    operator_id, role = get_operator_role(request)
    if not operator_id:
        return False, Response('{"error": "未提供操作者身份"}', 401, {'Content-Type': 'application/json'})
    if role not in allowed_roles:
        return False, Response('{"error": "权限不足"}', 403, {'Content-Type': 'application/json'})
    return True, None

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
                'system_name': config.get('system_name', '围炉诗社·理事台')
            }
    except: 
        return {
            'custom_member_fields': [],
            'password_salt': 'weilu2018',
            'points_name': '围炉值',
            'system_name': '围炉诗社·理事台'
        }
    
def save_settings(data):
    """保存系统设置到合并后的配置文件"""
    try:
        # 先读取完整的配置文件
        with open('data/config.json', 'r') as f:
            config = json.load(f)
        
        # 更新系统设置部分
        for key in ['custom_member_fields', 'password_salt', 'points_name', 'system_name']:
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

@api_route('/api/poems', methods=['POST'])
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
def delete_activity(request):
    pid = request.json.get('id')
    if db_activities.delete(pid): return {"status": "success"}
    return Response("Not Found", 404)

# --- Tasks API ---
@api_route('/api/tasks', methods=['GET'])
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
def create_task(request):
    """创建新任务（仅理事、管理员、超级管理员可创建）
    支持直接指派任务给特定用户（派发模式）
    """
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

@api_route('/api/tasks/claim', methods=['POST'])
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
def unclaim_task(request):
    """撤销领取任务（仅领取者可操作，仅claimed状态可撤销）"""
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
def submit_task(request):
    """提交任务完成（待审批）"""
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
def approve_task(request):
    """审批任务（管理角色可直接验收claimed或submitted状态的任务）"""
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
def reject_task(request):
    """拒绝任务（退回重做）"""
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
def delete_task(request):
    """删除任务（仅发布者或管理员可删除）"""
    data = request.json
    tid = data.get('task_id')
    if db_tasks.delete(tid):
        return {"status": "success"}
    return Response("Error", 500)

@api_route('/api/tasks/complete', methods=['POST'])
def complete_task(request):
    """快速完成任务（兼容旧版，直接完成并发放奖励）"""
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
    """获取成员列表，支持分页和搜索"""
    try:
        page = int(request.args.get('page', 0))
        limit = int(request.args.get('limit', 0))
        q = request.args.get('q', None)
        if q:
            q = simple_unquote(q)
        
        # 如果提供了分页参数，使用分页查询
        if page > 0 and limit > 0:
            items, total = db_members.fetch_page(page, limit, reverse=False, search_term=q)
            return {"data": items, "total": total, "page": page, "limit": limit}
        else:
            # 向后兼容：不带分页参数时返回全部数据
            return db_members.get_all()
    except Exception as e:
        error(f"获取成员列表失败: {e}", "API")
        return []

@api_route('/api/members', methods=['POST'])
def create_member(request):
    # 权限验证：理事级别
    ok, err = check_permission(request, ROLE_DIRECTOR)
    if not ok:
        return err
    
    data = request.json
    if not data: return Response('Invalid', 400)
    
    # 必填项验证
    if not data.get('name') or not data.get('phone') or not data.get('password'):
        return Response('{"error": "姓名、手机号和密码为必填项"}', 400, {'Content-Type': 'application/json'})
    
    # 角色权限验证：不能添加超级管理员或高于自己权限的角色
    target_role = data.get('role', 'member')
    _, operator_role = get_operator_role(request)
    allowed, role_err = can_assign_role(operator_role, target_role)
    if not allowed:
        return Response(json.dumps({"error": role_err}), 400, {'Content-Type': 'application/json'})
    
    existing = db_members.get_all()
    for m in existing:
        if m.get('phone') == data.get('phone'):
            return Response('Phone exists', 400)
    
    # 对密码进行哈希处理
    if 'password' in data and data['password']:
        data['password'] = hash_password(data['password'])
            
    data['id'] = db_members.get_max_id() + 1
    db_members.append(data)
    return data

@api_route('/api/members/update', methods=['POST'])
def update_member_route(request):
    # 权限验证：理事级别
    ok, err = check_permission(request, ROLE_DIRECTOR)
    if not ok:
        return err
    
    data = request.json
    mid = data.get('id')
    
    # 如果更新角色，验证角色权限
    if 'role' in data:
        target_role = data.get('role')
        _, operator_role = get_operator_role(request)
        allowed, role_err = can_assign_role(operator_role, target_role)
        if not allowed:
            return Response(json.dumps({"error": role_err}), 400, {'Content-Type': 'application/json'})
    
    # 如果更新密码，先进行哈希处理
    if 'password' in data and data['password']:
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
        for k in ['name', 'alias', 'phone', 'role', 'points', 'password', 'custom']:
            if k in data: m[k] = data[k]
    
    if db_members.update(mid, updater):
        # 如果积分有变动，记录日志
        if points_change != 0 and member_name:
            record_points_change(mid, member_name, points_change, '管理员调整')
        return {"status": "success"}
    return Response("Not Found", 404)

@api_route('/api/members/change_password', methods=['POST'])
def change_password_route(request):
    """用户修改自己的密码"""
    data = request.json
    member_id = data.get('id')
    old_password = data.get('old_password', '')
    new_password = data.get('new_password', '')
    
    if not member_id or not old_password or not new_password:
        return Response('{"error": "原密码和新密码为必填项"}', 400, {'Content-Type': 'application/json'})
    
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
def delete_member_route(request):
    # 权限验证：超级管理员级别
    ok, err = check_permission(request, ['super_admin'])
    if not ok:
        return err
    
    member_id = request.json.get('id')
    
    # 检查要删除的成员是否是超级管理员
    member = db_members.get_by_id(member_id)
    if member and member.get('role') == 'super_admin':
        return Response('{"error": "超级管理员不能被删除"}', 400, {'Content-Type': 'application/json'})
    
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
    
    # 统计每个成员最近1年的积分变动
    member_yearly_points = {}
    logs = db_points_logs.get_all()
    
    for log in logs:
        ts = log.get('timestamp', '')
        if ts >= one_year_ago:
            mid = log.get('member_id')
            change = log.get('change', 0)
            if mid not in member_yearly_points:
                member_yearly_points[mid] = {'points': 0, 'name': log.get('member_name', '')}
            member_yearly_points[mid]['points'] += change
    
    # 获取成员的雅号信息
    members = db_members.get_all()
    member_alias_map = {m.get('id'): m.get('alias', '') for m in members}
    
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
                        m_safe = m.copy()
                        if 'password' in m_safe: del m_safe['password']
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
    """更新个人资料（用户只能修改自己的基本信息）"""
    data = request.json
    if not data:
        return Response('{"error": "无效的请求数据"}', 400, {'Content-Type': 'application/json'})
    
    user_id = data.get('id')
    operator_id = data.get('operator_id')
    
    # 验证操作者身份
    if not operator_id:
        return Response('{"error": "未提供操作者身份"}', 401, {'Content-Type': 'application/json'})
    
    # 只能修改自己的资料
    if user_id != operator_id:
        return Response('{"error": "只能修改自己的资料"}', 403, {'Content-Type': 'application/json'})
    
    # 只允许修改有限的字段（alias, birthday）
    allowed_fields = {'alias', 'birthday'}
    update_data = {k: v for k, v in data.items() if k in allowed_fields}
    
    if not update_data:
        return Response('{"error": "没有可更新的字段"}', 400, {'Content-Type': 'application/json'})
    
    # 更新数据库
    def updater(m):
        for k, v in update_data.items():
            m[k] = v
    
    if db_members.update(user_id, updater):
        return {"success": True}
    return Response('{"error": "更新失败"}', 500, {'Content-Type': 'application/json'})

# --- Finance API ---
@api_route('/api/finance', methods=['GET'])
def list_finance(request):
    items, _ = db_finance.fetch_page(1, 100, reverse=True)
    return items

@api_route('/api/finance', methods=['POST'])
def add_finance(request):
    # 权限验证：财务级别
    ok, err = check_permission(request, ROLE_FINANCE)
    if not ok:
        return err
    
    data = request.json
    
    # 必填项验证
    amount = data.get('amount')
    if amount is None or not data.get('summary') or not data.get('handler'):
        return Response('{"error": "金额、摘要和经办人为必填项"}', 400, {'Content-Type': 'application/json'})
    
    data['id'] = db_finance.get_max_id() + 1
    db_finance.append(data)
    return data

@api_route('/api/finance/update', methods=['POST'])
def update_finance(request):
    """更新财务记录"""
    # 权限验证：财务级别
    ok, err = check_permission(request, ROLE_FINANCE)
    if not ok:
        return err
    
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
def delete_finance(request):
    """删除财务记录"""
    # 权限验证：财务级别
    ok, err = check_permission(request, ROLE_FINANCE)
    if not ok:
        return err
    
    data = request.json
    if not data or 'id' not in data:
        return Response('{"error": "缺少记录ID"}', 400, {'Content-Type': 'application/json'})
    
    fid = data.get('id')
    if db_finance.delete(fid):
        return {"status": "success"}
    return Response('{"error": "记录不存在"}', 404, {'Content-Type': 'application/json'})

# --- Login Logs API ---
@api_route('/api/login_logs', methods=['GET'])
def list_login_logs(request):
    """获取登录日志（最近20条）"""
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
        s['custom_member_fields'] = request.json.get('fields', request.json)
        save_settings(s)
        return {"status": "success"}

@api_route('/api/settings/system', methods=['GET', 'POST'])
def settings_system(request):
    """获取或更新系统设置（系统名称、salt和积分名称）"""
    s = get_settings()
    if request.method == 'GET':
        return {
            "system_name": s.get('system_name', '围炉诗社·理事台'),
            "password_salt": s.get('password_salt', 'weilu2018'),
            "points_name": s.get('points_name', '围炉值')
        }
    else:
        data = request.json
        # 修改Salt需要管理员权限
        if 'password_salt' in data:
            ok, err = check_permission(request, ROLE_ADMIN)
            if not ok:
                return err
            s['password_salt'] = data['password_salt']
        # 修改系统名称和积分名称需要理事权限
        if 'system_name' in data or 'points_name' in data:
            ok, err = check_permission(request, ROLE_DIRECTOR)
            if not ok:
                return err
            if 'system_name' in data:
                s['system_name'] = data['system_name']
            if 'points_name' in data:
                s['points_name'] = data['points_name']
        save_settings(s)
        return {"status": "success"}

# --- 密码迁移接口 (一次性使用) ---
@api_route('/api/migrate_passwords', methods=['POST'])
def migrate_passwords(request):
    """将所有明文密码迁移为SHA256哈希值"""
    # 权限验证：管理员级别
    ok, err = check_permission(request, ROLE_ADMIN)
    if not ok:
        return err
    
    migrated = 0
    try:
        members = db_members.get_all()
        for m in members:
            pwd = m.get('password', '')
            # 如果密码不是64位哈希值，则进行迁移
            if pwd and len(pwd) != 64:
                def updater(record):
                    record['password'] = hash_password(pwd)
                if db_members.update(m.get('id'), updater):
                    migrated += 1
        gc.collect()
        return {"status": "success", "migrated": migrated}
    except Exception as e:
        return Response(f"Migration error: {e}", 500)

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
                'ap_ip': config.get('ap_ip', '192.168.18.1')
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
def wifi_config(request):
    """获取或更新WiFi配置"""
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
            "ap_ip": config.get('ap_ip', '192.168.18.1')
        }
    else:
        # 权限验证：管理员级别
        ok, err = check_permission(request, ROLE_ADMIN)
        if not ok:
            return err
        
        data = request.json
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
def sys_info(request):
    """获取系统信息，包括内存、存储、运行时间、WiFi信号、系统时间和CPU温度"""
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
        
        # 获取WiFi信号强度
        wifi_rssi = None
        wifi_ssid = None
        try:
            wlan = network.WLAN(network.STA_IF)
            if wlan.active() and wlan.isconnected():
                wifi_rssi = wlan.status('rssi')
                wifi_ssid = wlan.config('essid')
        except Exception as e:
            debug(f"获取WiFi信号失败: {e}", "System")
        
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
            "cpu_temp": cpu_temp
        }
    except Exception as e:
        debug(f"获取系统信息失败: {e}", "System")
        return {}

@api_route('/api/system/stats')
def sys_stats(request):
    """获取各模块数据统计"""
    try:
        # 统计各模块数量
        members_count = len(db_members.get_all())
        poems_count = len(db_poems.get_all())
        activities_count = len(db_activities.get_all())
        tasks_count = len(db_tasks.get_all())
        finance_count = len(db_finance.get_all())
        
        gc.collect()
        
        return {
            "members": members_count,
            "poems": poems_count,
            "activities": activities_count,
            "tasks": tasks_count,
            "finance": finance_count
        }
    except Exception as e:
        error(f"获取统计数据失败: {e}", "Stats")
        return {}

@api_route('/api/backup/export')
def backup_export(request):
    """导出全站数据备份"""
    # 权限验证：管理员级别（通过URL参数验证）
    try:
        operator_id = int(request.args.get('operator_id', 0))
        if operator_id:
            with open(db_members.filepath, 'r') as f:
                for line in f:
                    try:
                        m = json.loads(line)
                        if m.get('id') == operator_id:
                            if m.get('role') not in ROLE_ADMIN:
                                return Response('{"error": "权限不足"}', 403, {'Content-Type': 'application/json'})
                            break
                    except:
                        pass
        else:
            return Response('{"error": "未提供操作者身份"}', 401, {'Content-Type': 'application/json'})
    except:
        return Response('{"error": "权限验证失败"}', 401, {'Content-Type': 'application/json'})
    
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
            "ap_ip": wifi_config.get('ap_ip', '192.168.18.1')
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
def backup_import(request):
    """导入数据备份"""
    # 权限验证：管理员级别（通过URL参数验证，避免大JSON解析问题）
    try:
        operator_id = int(request.args.get('operator_id', 0))
        if operator_id:
            with open(db_members.filepath, 'r') as f:
                found = False
                for line in f:
                    try:
                        m = json.loads(line)
                        if m.get('id') == operator_id:
                            if m.get('role') not in ROLE_ADMIN:
                                return Response('{"error": "权限不足"}', 403, {'Content-Type': 'application/json'})
                            found = True
                            break
                    except:
                        pass
                if not found:
                    return Response('{"error": "操作者不存在"}', 401, {'Content-Type': 'application/json'})
        else:
            return Response('{"error": "未提供操作者身份"}', 401, {'Content-Type': 'application/json'})
    except Exception as e:
        debug(f"备份导入权限验证失败: {e}", "Backup")
        return Response('{"error": "权限验证失败"}', 401, {'Content-Type': 'application/json'})
    
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
            existing_config['ap_ip'] = new_config.get('ap_ip', '192.168.18.1')
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
