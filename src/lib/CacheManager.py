"""
轻量级缓存管理器 - ESP32 MicroPython
统一管理所有后端内存缓存，支持 TTL、max_size 策略和统计监控。

缓存槽类型：
- dict: 内部字典，store(name) 返回可变引用
- list: 内部列表，store(name) 返回可变引用
- value: 单值（int/str/dict/None），get_val/set_val 读写
- const: 只读常量，get_val 读取，不可修改
"""

import time
import gc


class CacheManager:
    """ESP32 轻量级缓存管理器"""

    def __init__(self):
        self._data = {}    # {name: actual_data}
        self._cfg = {}     # {name: {type, ttl, max_size, ts, hits, misses}}

    def register(self, name, ctype='dict', ttl=None, max_size=None, initial=None):
        """
        注册缓存槽

        参数：
        - name: 缓存名称（唯一标识）
        - ctype: 类型 - 'dict'|'list'|'value'|'const'
        - ttl: 过期时间（秒），None=永不过期
        - max_size: 最大条目数（仅 dict），超限 FIFO 淘汰
        - initial: 初始值（dict/list 默认空容器，value/const 默认 None）
        """
        if ctype == 'dict':
            self._data[name] = initial if initial is not None else {}
        elif ctype == 'list':
            self._data[name] = initial if initial is not None else []
        elif ctype in ('value', 'const'):
            self._data[name] = initial
        self._cfg[name] = {
            'type': ctype,
            'ttl': ttl,
            'max_size': max_size,
            'ts': time.time(),
            'hits': 0,
            'misses': 0,
            'expires': 0
        }

    def store(self, name):
        """
        获取 dict/list 类型缓存的可变引用
        调用方可直接操作返回的 dict/list 对象
        若 TTL 过期则自动清空并返回空容器（记录为 expire）
        返回 None 表示缓存未注册
        """
        cfg = self._cfg.get(name)
        if not cfg:
            return None
        # TTL 过期检查
        if cfg['ttl'] and (time.time() - cfg['ts']) > cfg['ttl']:
            self._clear_slot(name)
            cfg['misses'] += 1
            cfg['expires'] += 1
            return self._data[name]
        cfg['hits'] += 1
        return self._data[name]

    def get_val(self, name):
        """
        获取 value/const 类型缓存的当前值
        若 TTL 过期（非 const）则清除并返回 None（记录为 expire）
        返回 None 可能是：缓存未注册、TTL 过期、或存储值本身为 None
        """
        cfg = self._cfg.get(name)
        if not cfg:
            return None
        # const 类型不检查 TTL
        if cfg['type'] != 'const' and cfg['ttl'] and (time.time() - cfg['ts']) > cfg['ttl']:
            self._clear_slot(name)
            cfg['misses'] += 1
            cfg['expires'] += 1
            return None
        cfg['hits'] += 1
        return self._data.get(name)

    def set_val(self, name, value):
        """设置 value 类型缓存的值（const 类型不可修改）"""
        cfg = self._cfg.get(name)
        if cfg and cfg['type'] != 'const':
            self._data[name] = value
            # 非 None 时更新时间戳（用于 TTL 计算）
            if value is not None:
                cfg['ts'] = time.time()

    def invalidate(self, name, key=None):
        """
        清除缓存
        - key=None: 清除整个槽（dict 清空、list 清空、value 置 None）
        - key!=None: 仅清除 dict 中的指定 key
        """
        cfg = self._cfg.get(name)
        if not cfg:
            return
        if key is not None and cfg['type'] == 'dict':
            self._data[name].pop(key, None)
        else:
            self._clear_slot(name)

    def enforce_max_size(self, name):
        """强制执行 dict 类型的 max_size 限制（FIFO 淘汰最早条目）"""
        cfg = self._cfg.get(name)
        if not cfg or not cfg['max_size'] or cfg['type'] != 'dict':
            return
        d = self._data[name]
        while len(d) > cfg['max_size']:
            first_key = next(iter(d))
            del d[first_key]

    def stats(self):
        """获取所有缓存的统计信息，用于监控接口"""
        result = {}
        for name, cfg in self._cfg.items():
            data = self._data[name]
            # 计算条目数
            if cfg['type'] in ('dict', 'list'):
                size = len(data) if data else 0
            else:
                size = 0 if data is None else 1
            # 计算命中率
            total = cfg['hits'] + cfg['misses']
            result[name] = {
                'type': cfg['type'],
                'size': size,
                'ttl': cfg['ttl'],
                'max_size': cfg['max_size'],
                'hits': cfg['hits'],
                'misses': cfg['misses'],
                'expires': cfg['expires'],
                'hit_rate': round(cfg['hits'] / total * 100) if total > 0 else 0
            }
        return result

    def flush_all(self):
        """紧急内存释放：清除所有非 const 缓存"""
        for name, cfg in self._cfg.items():
            if cfg['type'] != 'const':
                self._clear_slot(name)
        gc.collect()

    def _clear_slot(self, name):
        """内部：清除单个缓存槽"""
        cfg = self._cfg[name]
        if cfg['type'] == 'dict':
            self._data[name].clear()
        elif cfg['type'] == 'list':
            self._data[name].clear()
        elif cfg['type'] == 'value':
            self._data[name] = None
        # const 类型不清除
        cfg['ts'] = time.time()


# 全局单例
cache = CacheManager()
