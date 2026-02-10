# 围炉诗社·理事台 (Weilushishe Lishitai)

![Version](https://img.shields.io/badge/version-v1.0.0-blue)
![Platform](https://img.shields.io/badge/platform-ESP32--S2-orange)
![Environment](https://img.shields.io/badge/environment-MicroPython_v1.25.0-green)

围炉诗社·理事台是一个专为诗社管理设计的嵌入式 Web 应用系统。基于 ESP32-S2 硬件平台和 MicroPython 开发环境，集成了诗歌管理、活动记录、成员管理及财务统计等核心功能，为诗社提供轻量级、便携式的数字化管理方案。

## 🌟 核心功能

- **藏诗阁 (Poetry Management)**: 诗歌的发布、搜索、分页浏览、随机推荐、诗文详情页展示及本地草稿保存。
- **活动大厅 (Activity Management)**: 诗社活动的规划、记录与状态追踪。
- **聊天室 (Chat Room)**: 实时聊天室，消息缓存于内存（可配置，默认128KB），支持登录用户和游客（天干命名，可配置最大人数）。
- **任务管理 (Task Management)**: 任务的创建、认领、提交、审批与驳回完整流程。
- **成员名单 (Member Management)**: 成员信息维护、自定义字段、权限角色管理及密码修改。
- **财务统计 (Finance Management)**: 简易的收支记录与财务透明化展示。
- **积分系统 (Points System)**: 围炉值积分记录与年度排行榜。
- **年度热力图 (Activity Heatmap)**: 首页年度诗词创作热力图（类似 GitHub 贡献图），直观展示创作与活动频率。
- **系统监控 (System Monitoring)**: 实时监控 ESP32 的内存、存储空间、运行时长及网络状态。
- **数据备份 (Data Backup)**: 支持全量备份导出/导入，以及单表数据的独立导出/导入。
- **WiFi 管理**: 支持 STA/AP 自动切换、静态 IP 配置、自动重连机制及 NTP 时间同步（阿里云 NTP 服务器）。
- **视觉反馈**: 通过呼吸灯 (BreathLED) 实时反馈系统工作状态。
- **登录日志 (Login Audit)**: 记录所有用户登录行为（成功/失败），包含 IP、时间戳等信息，支持安全审计追踪。
- **缓存统计 (Cache Monitoring)**: 实时监控内存缓存命中率、过期率与使用情况（超级管理员专属）。

## 🔐 安全特性

- **Token 认证**: 基于 SHA256 签名的令牌鉴权机制，支持自动过期检测。登录令牌密钥与密码盐值独立，服务器重启后令牌自动失效。
- **动态有效期**: 登录有效期可在管理后台动态配置（1-365 天）。
- **密码安全**: SHA256 加盐哈希存储，盐值可自定义配置。
- **角色权限**: 五级权限体系（超级管理员 > 管理员 > 理事/财务 > 社员），细粒度 API 访问控制。
- **维护模式**: 支持一键开启维护模式，仅管理员可访问系统。
- **游客访问**: 可配置是否允许未登录用户浏览公开内容（首页、诗歌、活动、成员等）。
- **XSS 防护**: 集成 DOMPurify 对 Markdown 渲染内容进行 XSS 过滤。
- **看门狗机制**: 自动喂狗定时器，防止系统死锁。
- **审计追踪**: 完整记录登录日志（IP、时间戳、成功/失败状态），支持安全事件回溯。

## 🔑 角色权限体系

系统采用五级角色权限体系，数字越小权限越高：

| 角色 | 标识符 | 权限级别 | 说明 |
|------|--------|:-------:|------|
| 超级管理员 | `super_admin` | 0 | 系统最高权限，仅一个 |
| 管理员 | `admin` | 1 | 除超管专属外的全部权限 |
| 理事 | `director` | 2 | 活动/事务/成员管理与系统设置 |
| 财务 | `finance` | 3 | 普通社员权限 + 财务记账 |
| 普通社员 | `member` | 4 | 基本使用权限 |

### 权限对照表

| 功能模块 | 超级管理员 | 管理员 | 理事 | 财务 | 普通社员 |
|---------|:---------:|:-----:|:----:|:----:|:-------:|
| **系统管理** | | | | | |
| Salt 与登录有效期设置 | ✓ | - | - | - | - |
| WiFi 与 AP 配置 | ✓ | ✓ | - | - | - |
| 数据备份与恢复 | ✓ | - | - | - | - |
| 系统基础设置 | ✓ | ✓ | ✓ | - | - |
| **成员管理** | | | | | |
| 创建/编辑成员 | ✓ | ✓ | ✓* | - | - |
| 删除成员 | ✓ | ✓ | - | - | - |
| 重置成员密码 | ✓ | ✓ | ✓* | - | - |
| **活动与事务** | | | | | |
| 创建/编辑/删除活动 | ✓ | ✓ | ✓ | - | - |
| 创建/编辑/删除事务 | ✓ | ✓ | ✓ | - | - |
| 审批/驳回任务 | ✓ | ✓ | ✓ | - | - |
| **诗词管理** | | | | | |
| 发布/编辑/删除个人诗词 | ✓ | ✓ | ✓ | ✓ | ✓ |
| 编辑/删除他人诗词 | ✓ | ✓ | - | - | - |
| **财务管理** | | | | | |
| 财务记账（增删改） | ✓ | ✓ | - | ✓ | - |
| 查看财务记录 | ✓ | ✓ | ✓ | ✓ | ✓ |
| **个人功能** | | | | | |
| 修改个人资料与密码 | ✓ | ✓ | ✓ | ✓ | ✓ |
| 领取/提交任务 | ✓ | ✓ | ✓ | ✓ | ✓ |

> \* 理事仅可管理普通社员，不可管理管理员及以上角色。

### 特殊规则

- **超级管理员**只能由本人编辑自己的资料，其角色不可变更。
- **理事**只能为新成员分配"普通社员"角色，不可分配"财务"及以上角色。
- 任何角色都不能删除自己的账号，也不能管理与自己同级或更高级别的用户。
- 不允许通过 API 添加超级管理员，超级管理员在系统初始化时设置。

## 🛠️ 硬件平台

- **主控**: WEMOS S2 mini (ESP32-S2FN4R2)
- **资源**: 240MHz CPU, 320KB SRAM, 2MB PSRAM, 4MB Flash (可用约 2MB)
- **外设**: 
  - GPIO 15: 蓝色状态指示灯 (高电平点亮)
  - GPIO 0: 系统复位/功能按键 (按下为低电平)
- **官方文档**: [WEMOS S2 mini](https://www.wemos.cc/en/latest/s2/s2_mini.html)

## 💻 运行环境

- **MicroPython**: v1.25.0 (2025-04-15)
- **固件标识**: LOLIN_S2_MINI with ESP32-S2FN4R2
- **推荐固件下载**: [MicroPython ESP32-S2 官方固件](https://micropython.org/download/ESP32_GENERIC_S2/)

## 🚀 软件架构

### 核心组件库 (src/lib/)

**网络与通信**
- **[Microdot](src/lib/microdot.py)** - 专为微控制器优化的轻量级 Web 框架（第三方）。
- **[WifiConnector](src/lib/WifiConnector.py)** - 增强型网络连接器，支持静态 IP、STA/AP 自动切换、断线重连及 NTP 时间同步。

**数据存储与缓存**
- **[JsonlDB](src/lib/JsonlDB.py)** - JSONL 流式数据库引擎，支持行偏移分页、搜索优化、原子更新，适配极低内存环境。
- **[CacheManager](src/lib/CacheManager.py)** - 统一内存缓存管理器，支持 dict/list/value/const 四种槽类型、TTL 过期及容量控制。

**安全与认证**
- **[Auth](src/lib/Auth.py)** - Token 认证与密码管理，SHA256 加盐哈希，运行时签名密钥（重启失效）。
- **[Validator](src/lib/Validator.py)** - 数据验证器，支持手机号、密码强度、姓名、生日、积分及自定义字段验证。

**系统管理**
- **[Settings](src/lib/Settings.py)** - 系统配置管理，提供缓存层减少 Flash 读写。
- **[Logger](src/lib/Logger.py)** - 分级日志系统（DEBUG/INFO/WARN/ERROR），支持开发/生产环境切换。
- **[Watchdog](src/lib/Watchdog.py)** - 看门狗机制，防系统锁死，可配置超时时间（10-600 秒）。

**硬件控制**
- **[BreathLED](src/lib/BreathLED.py)** - 呼吸灯控制器，正弦表预计算优化，支持 WS2812 和普通 LED，多状态指示。
- **[SystemStatus](src/lib/SystemStatus.py)** - LED 状态指示器，封装连接中/AP 模式/运行中/双模式等视觉反馈逻辑。

### 前端技术栈

- 原生 **HTML5 / CSS3 / JavaScript (ES6+)**，采用 **SPA (单页应用)** 架构，通过 `showSection()` 切换视图。
- **响应式设计**: 移动端 (<768px) / 平板端 (<1280px) / PC 端 (>=1280px) 三端适配。
- **CSS 变量主题系统**: 9 个全局 CSS 变量统一主题色与风格。
- **本地存储**: `localStorage`（用户状态）+ `IndexedDB`（诗歌草稿离线编辑）。
- **Markdown 渲染**: [marked.js](https://marked.js.org/) + **XSS 防护**: [DOMPurify](https://github.com/cure53/DOMPurify)。

## 📂 目录结构

根据 [技术开发规范 (rules.md)](.qoder/rules/rules.md) 的要求，项目采用以下结构：

```text
.
├── .qoder/                    # Qoder AI 开发助手配置
│   └── rules/
│       └── rules.md           # 技术开发规范
├── doc/                       # 项目参考资料与说明文档
│   └── sch_s2_mini_v1.0.0.pdf # 硬件原理图
├── src/                       # 源代码根目录
│   ├── boot.py                # 系统启动引导程序 (硬件初始化/网络连接)
│   ├── main.py                # 主应用程序入口 (路由定义/业务逻辑)
│   ├── lib/                   # 核心功能组件库 (11 个模块)
│   │   ├── Auth.py            # Token 认证与密码管理
│   │   ├── BreathLED.py       # 呼吸灯控制
│   │   ├── CacheManager.py    # 缓存管理器
│   │   ├── JsonlDB.py         # JSONL 数据库引擎
│   │   ├── Logger.py          # 日志系统
│   │   ├── Settings.py        # 系统设置管理
│   │   ├── SystemStatus.py    # LED 状态指示
│   │   ├── Validator.py       # 数据验证器
│   │   ├── Watchdog.py        # 看门狗机制
│   │   ├── WifiConnector.py   # WiFi 管理
│   │   └── microdot.py        # Web 框架 (第三方)
│   ├── data/                  # 持久化 JSON/JSONL 数据文件
│   │   ├── config.json        # 系统配置
│   │   ├── members.jsonl      # 成员信息
│   │   ├── poems.jsonl        # 诗歌数据
│   │   ├── activities.jsonl   # 活动记录
│   │   ├── tasks.jsonl        # 任务事务
│   │   ├── finance.jsonl      # 财务记录
│   │   ├── points_logs.jsonl  # 积分日志
│   │   └── login_logs.jsonl   # 登录日志 (审计追踪)
│   └── static/                # 前端 Web 资源 (HTML/CSS/JS)
│       ├── index.html         # 主页面
│       ├── style.css          # 全局样式
│       ├── app.js             # 应用逻辑
│       ├── logo.png           # 站点图标
│       ├── marked.umd.js      # Markdown 渲染库 (第三方)
│       └── purify.min.js      # DOMPurify XSS 防护库 (第三方)
├── .gitignore                 # Git 忽略规则
├── LICENSE                    # GPL V3 开源许可证
└── README.md                  # 本说明文档
```

## 📥 安装与部署

1. **环境准备**: 确保 ESP32-S2 已刷入 MicroPython v1.25.0 或更高版本固件。
   - 推荐固件: `ESP32_GENERIC_S2-20250415-v1.25.0.bin`
   - 刷写工具: `esptool.py` 或 Thonny IDE
2. **配置文件**: 修改 `data/config.json`，配置您的 WiFi SSID 和密码。
3. **上传代码**: 使用 Thonny、WebREPL 或 `ampy` 将所有文件上传至 ESP32 根目录。
4. **运行**: 重启开发板，系统将自动执行 `boot.py` 连接网络并启动 `main.py`。
5. **访问**: 在浏览器中输入 ESP32 的 IP 地址（可通过串口查看或使用默认 AP 地址 `192.168.4.1`）。

## 规范与原则

后续开发请严格遵守 [.qoder/rules/rules.md](.qoder/rules/rules.md) 中的定义：
- **内存优先**: 必须通过逐行读取和 `gc.collect()` 严格控制内存占用。
- **中文标准**: 代码注释、界面文字统一使用中文。
- **异步交互**: 前端必须使用 `async/await` 处理所有网络请求。

## 📄 许可证

本项目采用 [GPL V3 许可证](LICENSE)。

---
**版本**: v1.0.0  
**更新日期**: 2026年2月10日  
**维护者**: 围炉诗社理事会
