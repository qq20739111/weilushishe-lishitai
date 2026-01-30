# 围炉诗社·理事台 系统优化计划

## 概述

经过对项目代码的全面分析，发现系统核心功能已实现约95%，但存在以下需要优化的问题。

---

## 修改文件清单

| 文件 | 修改类型 | 说明 |
|------|---------|------|
| `src/data/config.json` | 修复 | 移除末尾多余逗号 |
| `src/data/login_logs.jsonl` | 新增 | 登录日志数据文件（空文件） |
| `src/main.py` | 修改 | 密码哈希、登录日志API |
| `src/static/index.html` | 修改 | 下拉菜单导航、财务分类、首页布局 |
| `src/static/style.css` | 修改 | 下拉菜单样式、加载动画、空状态 |
| `src/static/app.js` | 修改 | 修复completeTask、财务提交、登录日志UI、首页数据加载 |

---

## 实施步骤

### 第一阶段：紧急修复

#### 1. 修复 config.json 语法错误
- **文件**: `src/data/config.json:6`
- **问题**: 末尾有多余逗号，导致JSON解析失败
- **方案**: 移除第5行末尾逗号

#### 2. 修复事务完成功能的硬编码问题
- **文件**: `src/static/app.js:718`
- **问题**: `completeTask` 函数硬编码了 `'张社长'`
- **方案**: 改为 `currentUser.name || currentUser.alias`

---

### 第二阶段：安全增强

#### 3. 实现密码SHA256哈希存储
- **文件**: `src/main.py`
- **方案**:
  1. 新增 `hash_password(password)` 函数，使用 `uhashlib.sha256`
  2. 修改 `/api/members` POST 路由，创建成员时哈希密码
  3. 修改 `/api/members/update` POST 路由，更新密码时哈希
  4. 修改 `/api/login` 路由，验证时对比哈希值
  5. 新增 `/api/migrate_passwords` 一次性迁移接口（迁移现有明文密码）

**注意**: 迁移后旧密码将失效，需要管理员重置

---

### 第三阶段：功能完善

#### 4. 新增用户登录日志功能
- **后端** (`src/main.py`):
  1. 新增 `db_login_logs = JsonlDB('data/login_logs.jsonl')`
  2. 修改 `/api/login`，登录时记录日志
  3. 新增 `/api/login_logs` GET 接口

**数据结构**:
```json
{
  "id": 1,
  "member_id": 2,
  "member_name": "张三",
  "phone": "138****0001",
  "login_time": "2026-01-31T10:30:45",
  "status": "success"
}
```

- **前端** (`src/static/index.html`, `src/static/app.js`):
  1. 在管理后台新增"登录日志"卡片
  2. 显示最近20条登录记录

#### 5. 完善财务记账模态框
- **文件**: `src/static/index.html:200-208`
- **方案**:
  1. 在模态框添加 `<select id="f-category">` 分类选择器
  2. 预设选项: 会费、活动费用、物资采购、稿费、捐赠、其他
  3. 修改 `submitFinance()` 提交 `category` 字段

---

### 第四阶段：UI/UX优化

#### 6. 响应式导航优化
- **方案**: PC端顶部导航，移动端下拉菜单

**PC端** (保持现状):
- 顶部导航栏水平排列

**移动端** (≤600px):
- 顶部显示Logo + 汉堡菜单按钮
- 点击展开下拉菜单，包含所有导航项
- 下拉菜单垂直排列，点击后自动收起

**实现细节**:
- HTML: 新增汉堡按钮 `<button class="menu-toggle">☰</button>`
- CSS: 媒体查询隐藏/显示对应元素
- JS: 新增 `toggleMobileMenu()` 函数

#### 7. 首页布局优化
- **新增"最新诗作"卡片**:
  - 显示最近发布的3首诗词
  - 包含标题、作者、类型标签
  - 点击可查看详情

- **新增"积分排行榜"卡片**:
  - 显示积分前5名社员
  - 包含头像、姓名、积分数
  - 使用奖牌图标区分前三名

**实现细节**:
- HTML: 在首页section新增两个card容器
- JS: 新增 `loadLatestPoems()` 和 `loadPointsRanking()` 函数
- 在 `loadSystemInfo()` 中调用

#### 8. 统一加载状态指示
- **CSS**: 添加旋转加载动画 `.loading-spinner`
- **JS**: 
  - `showLoading(containerId)` - 在指定容器显示loading
  - `hideLoading(containerId)` - 隐藏loading
  - 在 `fetchPoems`、`fetchActivities` 等函数中调用

#### 9. 优化空状态提示
- 为各模块设计统一的空状态UI
- 包含图标 + 提示文字 + 操作按钮
- 样式: 居中显示，灰色图标，引导按钮

---

## 验证方案

1. **config.json修复**: 重启系统，检查串口日志无JSON解析错误
2. **密码哈希**: 创建新用户后检查members.jsonl，密码应为64位哈希字符串
3. **登录日志**: 登录后进入管理后台，查看登录日志记录
4. **财务分类**: 新增财务记录，确认分类字段正确保存和显示
5. **移动端导航**: 浏览器切换移动端模式，验证下拉菜单正常展开/收起
6. **首页优化**: 验证"最新诗作"和"积分排行榜"卡片正常显示数据
7. **加载状态**: 切换页面观察loading动画
8. **空状态**: 清空某模块数据，验证空状态提示显示

---

## 技术注意事项

### ESP32资源限制
- 密码哈希使用 `uhashlib.sha256`（MicroPython内置）
- 登录日志定期清理，保留最近100条
- 避免一次性加载大量数据，使用分页

### 兼容性
- CSS使用标准属性，添加-webkit前缀
- JavaScript使用ES5兼容语法
- 测试Chrome、Safari移动端浏览器
