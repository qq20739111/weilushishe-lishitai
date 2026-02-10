# JSON Lines (JSONL) 数据库引擎
# 支持流式读写，适用于 ESP32 内存受限环境

import json
import os
import gc
from lib.Logger import debug, error
from lib.CacheManager import cache


def file_exists(path):
    try:
        os.stat(path)
        return True
    except OSError:
        return False


class JsonlDB:
    def __init__(self, filepath, auto_migrate=True):
        self.filepath = filepath
        # 注册到缓存管理器（替代 self._max_id_cache / self._count_cache）
        self._ck_maxid = 'db:' + filepath + ':maxid'
        self._ck_count = 'db:' + filepath + ':count'
        cache.register(self._ck_maxid, ctype='value', initial=None)
        cache.register(self._ck_count, ctype='value', initial=None)
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
            # 维护缓存
            cnt = cache.get_val(self._ck_count)
            if cnt is not None:
                cache.set_val(self._ck_count, cnt + 1)
            if 'id' in record:
                mid = cache.get_val(self._ck_maxid)
                if mid is not None:
                    pid = int(record['id'])
                    if pid > mid:
                        cache.set_val(self._ck_maxid, pid)
            return True
        except Exception as e:
            error(f"追加记录失败: {e}", "DB")
            return False

    def get_max_id(self):
        """Scan file to find max numeric ID (with cache)"""
        cached = cache.get_val(self._ck_maxid)
        if cached is not None:
            return cached
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
        cache.set_val(self._ck_maxid, max_id)
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
            
            if not found:
                # 未找到目标记录，清理临时文件，跳过无意义的文件替换
                os.remove(tmp_path)
                return False
            os.remove(self.filepath)
            os.rename(tmp_path, self.filepath)
            # 删除成功，维护缓存
            cnt = cache.get_val(self._ck_count)
            if cnt is not None and cnt > 0:
                cache.set_val(self._ck_count, cnt - 1)
            cache.set_val(self._ck_maxid, None)  # 删除后 max_id 可能变化，置空重算
            return True
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
        """统计记录数量（带缓存，只计数，不解析JSON，内存友好）"""
        cached = cache.get_val(self._ck_count)
        if cached is not None:
            return cached
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
        cache.set_val(self._ck_count, count)
        return count


def cleanup_temp_files(data_dir='data'):
    """启动时清理残留的数据库临时文件"""
    cleaned = 0
    try:
        for f in os.listdir(data_dir):
            if f.endswith('.tmp'):
                path = data_dir + '/' + f
                try:
                    os.remove(path)
                    debug("清理临时文件: " + path, "DB")
                    cleaned += 1
                except Exception as e:
                    error("删除临时文件失败 " + path + ": " + str(e), "DB")
    except Exception as e:
        error("扫描临时文件失败: " + str(e), "DB")
    if cleaned:
        gc.collect()
    return cleaned
