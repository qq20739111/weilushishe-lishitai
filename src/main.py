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

def get_current_time():
    """获取当前时间字符串 (ISO格式近似)"""
    t = time.localtime()
    return "{:04d}-{:02d}-{:02d}T{:02d}:{:02d}:{:02d}".format(
        t[0], t[1], t[2], t[3], t[4], t[5]
    )

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

@app.route('/api/tasks/complete', methods=['POST'])
def complete_task(request):
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
    
    # 如果更新密码，先进行哈希处理
    if 'password' in data and data['password']:
        data['password'] = hash_password(data['password'])
    
    def updater(m):
        for k in ['name', 'alias', 'phone', 'role', 'points', 'password', 'custom']:
            if k in data: m[k] = data[k]
    if db_members.update(data.get('id'), updater):
        return {"status": "success"}
    return Response("Not Found", 404)

@app.route('/api/members/delete', methods=['POST'])
def delete_member_route(request):
    if db_members.delete(request.json.get('id')): return {"status": "success"}
    return Response("Error", 500)

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
    """获取或更新系统设置（salt和积分名称）"""
    s = get_settings()
    if request.method == 'GET':
        return {
            "password_salt": s.get('password_salt', 'weilu2018'),
            "points_name": s.get('points_name', '围炉值')
        }
    else:
        data = request.json
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

@app.route('/api/system/info')
def sys_info(request):
    try:
        gc.collect()
        s = os.statvfs('/')
        return {
            "platform": "ESP32",
            "free_storage": s[0]*s[3],
            "total_storage": s[0]*s[2],
            "free_ram": gc.mem_free()
        }
    except: return {}

if __name__ == '__main__':
    try:
        print("[System] Starting Microdot App...")
        print_system_status()
        app.run(port=80, debug=True)
    except Exception as e:
        print(f"[Error] {e}")
