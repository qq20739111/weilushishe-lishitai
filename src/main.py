import sys
print("[Init] main.py (Refactored) starting...")

try:
    import json
    import os
    import gc
    import network
    import time
    import uhashlib
    import ubinascii
    from lib.microdot import Microdot, Response, send_file
    # from lib.SystemStatus import status_led # Optional: Uncomment if available
    print("[Init] Imports successful")
except ImportError as e:
    print(f"\n[CRITICAL] Import failed: {e}")
    sys.exit()

app = Microdot()

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
        print(f"[Warn] Unquote error: {e}")
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
            print(f"[DB] Migrating {legacy_path} -> {self.filepath}")
            try:
                with open(legacy_path, 'r') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        with open(self.filepath, 'w') as out:
                            for item in data:
                                out.write(json.dumps(item) + "\n")
                # os.remove(legacy_path) # Optional: Delete old file
            except Exception as e:
                print(f"[DB] Migration failed: {e}")

    def append(self, record):
        """Append a new record to the end of file"""
        try:
            with open(self.filepath, 'a') as f:
                f.write(json.dumps(record) + "\n")
            return True
        except Exception as e:
            print(f"[DB] Append error: {e}")
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
                    except: pass
        except OSError: pass # File might not exist
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
            except: pass
            
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
                        except: pass
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
                        except: pass
            except: pass
            
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
                    except:
                        pass
            
            if found:
                os.remove(self.filepath)
                os.rename(tmp_path, self.filepath)
                return True
            else:
                os.remove(tmp_path)
                return False
        except Exception as e:
            print(f"[DB] Update error: {e}")
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
                    except: pass
            
            os.remove(self.filepath)
            os.rename(tmp_path, self.filepath)
            return found
        except Exception as e:
            print(f"[DB] Delete error: {e}")
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
                    except: pass
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
    except: pass

# Legacy for settings (kept as simple JSON for now)
def get_settings():
    try:
        with open('data/settings.json', 'r') as f: return json.load(f)
    except: return {}
    
def save_settings(data):
    try:
        with open('data/settings.json', 'w') as f: json.dump(data, f)
    except: pass

def print_system_status():
    print("-" * 50)
    print("🔥 围炉诗社运营管理系统 - 系统状态 (Refactored) 🔥")
    print("-" * 50)
    try:
        wlan_sta = network.WLAN(network.STA_IF)
        if wlan_sta.active() and wlan_sta.isconnected():
            ifconf = wlan_sta.ifconfig()
            print(f"[WiFi] {ifconf[0]}")
    except: pass
    try:
        gc.collect() 
        print(f"[MEM] Free: {gc.mem_free()/1024:.2f} KB")
    except: pass
    print("-" * 50)

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
@app.route('/api/poems', methods=['GET'])
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
        print(f"[API Error] list_poems: {e}")
        return []

@app.route('/api/poems', methods=['POST'])
def create_poem(request):
    if not request.json: return Response('Invalid JSON', 400)
    data = request.json
    
    new_id = db_poems.get_max_id() + 1
    data['id'] = new_id
    if 'date' not in data: data['date'] = '2026-01-01'
    
    if db_poems.append(data):
        return data
    return Response('Write Failed', 500)

@app.route('/api/poems/update', methods=['POST'])
def update_poem(request):
    if not request.json: return Response('Invalid', 400)
    data = request.json
    pid = data.get('id')
    
    def updater(record):
        if 'title' in data: record['title'] = data['title']
        if 'content' in data: record['content'] = data['content']
        if 'type' in data: record['type'] = data['type']
        if 'date' in data: record['date'] = data['date']
        
    if db_poems.update(pid, updater):
        return {"status": "success"}
    return Response("Poem not found", 404)

@app.route('/api/poems/delete', methods=['POST'])
def delete_poem(request):
    if not request.json: return Response('Invalid', 400)
    pid = request.json.get('id')
    if db_poems.delete(pid):
        return {"status": "success"}
    return Response("Poem not found", 404)

# --- Activities API ---
@app.route('/api/activities', methods=['GET'])
def list_activities(request):
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 50))
        q = request.args.get('q', None)
        if q: q = simple_unquote(q)
        items, _ = db_activities.fetch_page(page, limit, reverse=True, search_term=q)
        return items
    except: return []

@app.route('/api/activities', methods=['POST'])
def create_activity(request):
    if not request.json: return Response('Invalid', 400)
    data = request.json
    data['id'] = db_activities.get_max_id() + 1
    db_activities.append(data)
    return data

@app.route('/api/activities/update', methods=['POST'])
def update_activity(request):
    data = request.json
    if not data: return Response('Invalid', 400)
    
    def updater(r):
        for k in ['title', 'desc', 'date', 'location', 'status']:
            if k in data: r[k] = data[k]
            
    if db_activities.update(data.get('id'), updater):
        return {"status": "success"}
    return Response("Not Found", 404)

@app.route('/api/activities/delete', methods=['POST'])
def delete_activity(request):
    pid = request.json.get('id')
    if db_activities.delete(pid): return {"status": "success"}
    return Response("Not Found", 404)

# --- Tasks API ---
@app.route('/api/tasks', methods=['GET'])
def list_tasks(request):
    return db_tasks.get_all()

@app.route('/api/tasks', methods=['POST'])
def create_task(request):
    """创建新任务（仅理事、管理员、超级管理员可创建）"""
    data = request.json
    if not data: return Response('Invalid', 400)
    
    task = {
        'id': db_tasks.get_max_id() + 1,
        'title': data.get('title', ''),
        'description': data.get('description', ''),
        'reward': int(data.get('reward', 0)),
        'status': 'open',
        'creator': data.get('creator', ''),
        'assignee': None,
        'created_at': get_current_time(),
        'claimed_at': None,
        'submitted_at': None,
        'completed_at': None
    }
    db_tasks.append(task)
    return task

@app.route('/api/tasks/claim', methods=['POST'])
def claim_task(request):
    """领取任务"""
    data = request.json
    tid = data.get('task_id')
    u_name = data.get('member_name')
    
    task_found = False
    
    def task_updater(t):
        nonlocal task_found
        if t.get('status') == 'open':
            t['status'] = 'claimed'
            t['assignee'] = u_name
            t['claimed_at'] = get_current_time()
            task_found = True
            
    db_tasks.update(tid, task_updater)
    
    if not task_found: return Response('Task not available', 404)
    return {"status": "success"}

@app.route('/api/tasks/unclaim', methods=['POST'])
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

@app.route('/api/tasks/submit', methods=['POST'])
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

@app.route('/api/tasks/approve', methods=['POST'])
def approve_task(request):
    """审批任务（发布者审批，通过后发放奖励）"""
    data = request.json
    tid = data.get('task_id')
    
    reward = 0
    assignee_name = None
    task_status = None
    task_found = False
    
    def task_updater(t):
        nonlocal reward, assignee_name, task_status, task_found
        task_found = True
        task_status = t.get('status')
        if task_status == 'submitted':
            t['status'] = 'completed'
            t['completed_at'] = get_current_time()
            reward = t.get('reward', 0)
            assignee_name = t.get('assignee')
            
    db_tasks.update(tid, task_updater)
    
    # 任务不存在
    if not task_found:
        return Response('Task not found', 404)
    
    # 任务已完成（可能是重复请求）
    if task_status == 'completed':
        return {"status": "success", "gained": 0, "message": "已验收"}
    
    # 任务状态不是待验收
    if task_status != 'submitted':
        return Response('Task not in submitted status', 400)
    
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

@app.route('/api/tasks/reject', methods=['POST'])
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

@app.route('/api/tasks/delete', methods=['POST'])
def delete_task(request):
    """删除任务（仅发布者或管理员可删除）"""
    data = request.json
    tid = data.get('task_id')
    if db_tasks.delete(tid):
        return {"status": "success"}
    return Response("Error", 500)

@app.route('/api/tasks/complete', methods=['POST'])
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
@app.route('/api/members', methods=['GET'])
def list_members(request):
    return db_members.get_all()

@app.route('/api/members', methods=['POST'])
def create_member(request):
    data = request.json
    if not data: return Response('Invalid', 400)
    
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

@app.route('/api/members/update', methods=['POST'])
def update_member_route(request):
    data = request.json
    mid = data.get('id')
    
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

@app.route('/api/members/change_password', methods=['POST'])
def change_password_route(request):
    """用户修改自己的密码"""
    data = request.json
    member_id = data.get('id')
    old_password = data.get('old_password', '')
    new_password = data.get('new_password', '')
    
    if not member_id or not new_password:
        return Response('{"error": "参数不完整"}', 400, {'Content-Type': 'application/json'})
    
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

@app.route('/api/members/delete', methods=['POST'])
def delete_member_route(request):
    if db_members.delete(request.json.get('id')): return {"status": "success"}
    return Response("Error", 500)

@app.route('/api/points/yearly_ranking', methods=['GET'])
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

@app.route('/api/login', methods=['POST'])
def login_route(request):
    data = request.json
    p = data.get('phone')
    pw = data.get('password')
    
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
                except: pass
    except: pass
    
    # 记录登录失败日志
    record_login_log(None, '未知', p or '', 'failed')
    return Response('Invalid credentials', 401)

# --- Finance API ---
@app.route('/api/finance', methods=['GET'])
def list_finance(request):
    items, _ = db_finance.fetch_page(1, 100, reverse=True)
    return items

@app.route('/api/finance', methods=['POST'])
def add_finance(request):
    data = request.json
    data['id'] = db_finance.get_max_id() + 1
    db_finance.append(data)
    return data

# --- Login Logs API ---
@app.route('/api/login_logs', methods=['GET'])
def list_login_logs(request):
    """获取登录日志（最近20条）"""
    items, _ = db_login_logs.fetch_page(1, 20, reverse=True)
    return items

# --- Settings ---
@app.route('/api/settings/fields', methods=['GET', 'POST'])
def settings_fields(request):
    s = get_settings()
    if request.method == 'GET':
        return s.get('custom_member_fields', [])
    else:
        s['custom_member_fields'] = request.json
        save_settings(s)
        return {"status": "success"}

@app.route('/api/settings/system', methods=['GET', 'POST'])
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
        if 'system_name' in data:
            s['system_name'] = data['system_name']
        if 'password_salt' in data:
            s['password_salt'] = data['password_salt']
        if 'points_name' in data:
            s['points_name'] = data['points_name']
        save_settings(s)
        return {"status": "success"}

# --- 密码迁移接口 (一次性使用) ---
@app.route('/api/migrate_passwords', methods=['POST'])
def migrate_passwords(request):
    """将所有明文密码迁移为SHA256哈希值"""
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
            return json.load(f)
    except:
        return {}

def save_wifi_config(data):
    """保存WiFi配置"""
    try:
        with open('data/config.json', 'w') as f:
            json.dump(data, f)
        return True
    except:
        return False

@app.route('/api/wifi/config', methods=['GET', 'POST'])
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

@app.route('/api/system/info')
def sys_info(request):
    try:
        gc.collect()
        s = os.statvfs('/')
        free_ram = gc.mem_free()
        # 尝试获取总内存，若无法获取则默认2048KB
        try:
            total_ram = gc.mem_free() + gc.mem_alloc()
        except:
            total_ram = 2048 * 1024  # 默认2048KB
        return {
            "platform": "ESP32",
            "free_storage": s[0]*s[3],
            "total_storage": s[0]*s[2],
            "free_ram": free_ram,
            "total_ram": total_ram
        }
    except: return {}

@app.route('/api/system/stats')
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
        print(f"[Stats Error] {e}")
        return {}

@app.route('/api/backup/export')
def backup_export(request):
    """导出全站数据备份"""
    try:
        # 获取WiFi配置（密码不导出，安全考虑）
        wifi_config = get_wifi_config()
        wifi_backup = {
            "wifi_ssid": wifi_config.get('wifi_ssid', ''),
            "sta_use_static_ip": wifi_config.get('sta_use_static_ip', False),
            "sta_ip": wifi_config.get('sta_ip', ''),
            "sta_subnet": wifi_config.get('sta_subnet', '255.255.255.0'),
            "sta_gateway": wifi_config.get('sta_gateway', ''),
            "sta_dns": wifi_config.get('sta_dns', '8.8.8.8'),
            "ap_ssid": wifi_config.get('ap_ssid', ''),
            "ap_ip": wifi_config.get('ap_ip', '192.168.18.1')
        }
        
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
                "wifi_config": wifi_backup
            }
        }
        gc.collect()
        return backup_data
    except Exception as e:
        print(f"[Backup Export Error] {e}")
        return Response('{"error": "导出失败"}', 500, {'Content-Type': 'application/json'})

@app.route('/api/backup/import', methods=['POST'])
def backup_import(request):
    """导入数据备份"""
    try:
        backup = request.json
        if not backup or 'version' not in backup or 'data' not in backup:
            return Response('{"error": "无效的备份文件"}', 400, {'Content-Type': 'application/json'})
        
        data = backup['data']
        
        # 逐个恢复数据
        if 'members' in data:
            with open('data/members.jsonl', 'w') as f:
                for item in data['members']:
                    f.write(json.dumps(item) + "\n")
        
        if 'poems' in data:
            with open('data/poems.jsonl', 'w') as f:
                for item in data['poems']:
                    f.write(json.dumps(item) + "\n")
        
        if 'activities' in data:
            with open('data/activities.jsonl', 'w') as f:
                for item in data['activities']:
                    f.write(json.dumps(item) + "\n")
        
        if 'tasks' in data:
            with open('data/tasks.jsonl', 'w') as f:
                for item in data['tasks']:
                    f.write(json.dumps(item) + "\n")
        
        if 'finance' in data:
            with open('data/finance.jsonl', 'w') as f:
                for item in data['finance']:
                    f.write(json.dumps(item) + "\n")
        
        if 'points_logs' in data:
            with open('data/points_logs.jsonl', 'w') as f:
                for item in data['points_logs']:
                    f.write(json.dumps(item) + "\n")
        
        if 'login_logs' in data:
            with open('data/login_logs.jsonl', 'w') as f:
                for item in data['login_logs']:
                    f.write(json.dumps(item) + "\n")
        
        if 'settings' in data:
            with open('data/settings.json', 'w') as f:
                json.dump(data['settings'], f)
        
        # 恢复WiFi配置（保留原有密码）
        if 'wifi_config' in data:
            existing_config = get_wifi_config()
            new_config = data['wifi_config']
            # 保留原有密码，只更新非敏感配置
            existing_config['wifi_ssid'] = new_config.get('wifi_ssid', existing_config.get('wifi_ssid', ''))
            existing_config['sta_use_static_ip'] = new_config.get('sta_use_static_ip', False)
            existing_config['sta_ip'] = new_config.get('sta_ip', '')
            existing_config['sta_subnet'] = new_config.get('sta_subnet', '255.255.255.0')
            existing_config['sta_gateway'] = new_config.get('sta_gateway', '')
            existing_config['sta_dns'] = new_config.get('sta_dns', '8.8.8.8')
            existing_config['ap_ssid'] = new_config.get('ap_ssid', existing_config.get('ap_ssid', ''))
            existing_config['ap_ip'] = new_config.get('ap_ip', '192.168.18.1')
            save_wifi_config(existing_config)
        
        gc.collect()
        return {"status": "success", "message": "数据恢复成功"}
    except Exception as e:
        print(f"[Backup Import Error] {e}")
        return Response('{"error": "导入失败"}', 500, {'Content-Type': 'application/json'})

if __name__ == '__main__':
    try:
        print("[System] Starting Microdot App...")
        print_system_status()
        app.run(port=80, debug=True)
    except Exception as e:
        print(f"[Error] {e}")
