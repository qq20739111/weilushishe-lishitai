# 登录日志增强实施方案

## 需求
1. 后端记录登录IP地址
2. 前端优化PC端和移动端日志列表UI排版

## 修改文件清单
1. `src/lib/microdot.py` - 捕获客户端IP
2. `src/main.py` - 更新日志记录函数和调用点
3. `src/static/style.css` - 新增日志列表响应式样式
4. `src/static/app.js` - 重写日志渲染，移除内联样式
5. `src/static/index.html` - 清理容器内联样式

---

## 步骤1: 修改 microdot.py（最小化改动）

**文件**: `src/lib/microdot.py`

### 1.1 Request.__init__（第6行）添加 client_ip 属性
```python
def __init__(self, reader):
    self.reader = reader
    self.client_ip = ''  # 新增：客户端IP
    self.method = 'GET'
    ...
```

### 1.2 handle_request（第138行）提取IP并赋值
在 `req = Request(reader)` 之后添加：
```python
req = Request(reader)
# 提取客户端IP
try:
    peer = writer.get_extra_info('peername')
    if peer:
        req.client_ip = peer[0]
except:
    pass
```

---

## 步骤2: 更新后端业务逻辑

**文件**: `src/main.py`

### 2.1 record_login_log 函数（第930行）
- 签名添加 `ip=''` 参数
- log 字典添加 `'ip': ip` 字段

```python
def record_login_log(member_id, member_name, phone, status, ip=''):
    log = {
        'id': db_login_logs.get_max_id() + 1,
        'member_id': member_id,
        'member_name': member_name,
        'phone': phone[:3] + '****' + phone[-4:] if len(phone) >= 7 else phone,
        'login_time': get_current_time(),
        'status': status,
        'ip': ip
    }
    ...
```

### 2.2 login_route 中3处调用（第1848、1858、1866行）
每处添加 `request.client_ip` 参数：
- 第1848行: `record_login_log(m.get('id'), m.get('name', '未知'), p, 'failed', request.client_ip)`
- 第1858行: `record_login_log(m.get('id'), m.get('name', '未知'), p, 'success', request.client_ip)`
- 第1866行: `record_login_log(None, '未知', p or '', 'failed', request.client_ip)`

---

## 步骤3: 新增CSS样式

**文件**: `src/static/style.css`

在 `.points-badge` 规则（第513行）之后插入登录日志专用样式。

### PC端（默认样式，>=1280px）
- `.login-log-table`: 容器
- `.login-log-header`: 表头行，CSS Grid 5列（用户名 | 手机号 | IP地址 | 状态 | 时间）
- `.login-log-row`: 数据行，同表头Grid定义，hover效果
- `.log-status-success` / `.log-status-failed`: 状态颜色类

### 移动端（@media max-width: 767px）
- 隐藏表头 `.login-log-header`
- `.login-log-row` 改为卡片布局（flex column），展示全部字段
- 每个字段前添加标签文字（通过 `::before` 伪元素或 `data-label` 属性）

### 平板端（@media max-width: 1279px）
- 紧凑间距，保持表格布局

---

## 步骤4: 重写前端渲染逻辑

**文件**: `src/static/app.js`（第3901-3931行）

重写 `fetchLoginLogs()` 函数：

```javascript
async function fetchLoginLogs() {
    const container = document.getElementById('login-logs-list');
    if(!container) return;
    try {
        const res = await fetchWithAuth(`${API_BASE}/login_logs`);
        if(!res.ok) throw new Error('Failed');
        const logs = await res.json();
        if(logs.length === 0) {
            container.innerHTML = '<div class="empty-hint">暂无登录记录</div>';
            return;
        }
        const header = `<div class="login-log-header">
            <div>用户</div><div>手机号</div><div>IP地址</div><div>状态</div><div>时间</div>
        </div>`;
        const rows = logs.map(log => {
            const statusCls = log.status === 'success' ? 'log-status-success' : 'log-status-failed';
            const statusTxt = log.status === 'success' ? '成功' : '失败';
            const ip = log.ip || '-';
            const time = log.login_time ? log.login_time.replace('T', ' ') : '';
            return `<div class="login-log-row">
                <div data-label="用户">${log.member_name || '未知'}</div>
                <div data-label="手机号">${log.phone}</div>
                <div data-label="IP">${ip}</div>
                <div data-label="状态"><span class="points-badge ${statusCls}">${statusTxt}</span></div>
                <div data-label="时间">${time}</div>
            </div>`;
        }).join('');
        container.innerHTML = `<div class="login-log-table">${header}${rows}</div>`;
    } catch(e) {
        console.error(e);
        container.innerHTML = '<div class="empty-hint">加载失败，请刷新重试</div>';
    }
}
```

关键设计：
- PC端：Grid表格，表头+数据行
- 移动端：CSS隐藏表头，数据行变卡片，通过 `data-label` + `::before` 显示字段标签
- 兼容旧数据：`log.ip || '-'` 处理无IP字段的历史记录

---

## 步骤5: 清理HTML内联样式

**文件**: `src/static/index.html`（第515-518行）

将容器内联样式移至CSS类：
```html
<div class="card director-only-card" style="margin-top:20px;">
    <h3>登录日志</h3>
    <p style="color:#666; font-size:0.9em;">最近20条登录记录</p>
    <div id="login-logs-list" class="login-logs-container">加载中...</div>
</div>
```

在CSS中定义 `.login-logs-container`：
```css
.login-logs-container {
    max-height: 400px;
    overflow-y: auto;
}
```

---

## 验证方案

1. **后端验证**: 登录后检查 `data/login_logs.jsonl` 文件，确认新记录包含 `ip` 字段且值正确
2. **前端PC端**: 浏览器宽度 >=1280px，确认表格横向5列布局整齐
3. **前端移动端**: 浏览器宽度 <768px，确认卡片式布局，字段标签清晰
4. **向后兼容**: 旧日志（无ip字段）应正常显示，IP列显示 `-`
5. **回归测试**: 确认其他API接口（诗歌、成员等）正常工作，microdot改动无副作用
