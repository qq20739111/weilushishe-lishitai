# 围炉诗社·理事台 (Weilushishe Lishitai)

![Version](https://img.shields.io/badge/version-v1.0.0-blue)
![Platform](https://img.shields.io/badge/platform-ESP32--S2-orange)
![Environment](https://img.shields.io/badge/environment-MicroPython-green)

围炉诗社·理事台是一个专为诗社管理设计的嵌入式 Web 应用系统。基于 ESP32-S2 硬件平台和 MicroPython 开发环境，集成了诗歌管理、活动记录、成员管理及财务统计等核心功能，为诗社提供轻量级、便携式的数字化管理方案。

## 🌟 核心功能

- **藏诗阁 (Poetry Management)**: 诗歌的发布、搜索、分页浏览及本地草稿保存。
- **活动大厅 (Activity Management)**: 诗社活动的规划、记录与状态追踪。
- **成员名单 (Member Management)**: 成员信息维护与权限角色管理。
- **财务统计 (Finance Management)**: 简易的收支记录与财务透明化展示。
- **系统监控 (System Monitoring)**: 实时监控 ESP32 的内存、存储空间及网络状态。
- **WiFi 管理**: 支持 STA/AP 自动切换、静态 IP 配置及自动重连机制。
- **视觉反馈**: 通过呼吸灯 (BreathLED) 实时反馈系统工作状态。

## 🛠️ 硬件平台

- **主控**: WEMOS S2 mini (ESP32-S2FN4R2)
- **资源**: 240MHz CPU, 320KB SRAM, 2MB PSRAM, 4MB Flash (可用约 2MB)
- **外设**: 
  - GPIO 15: 蓝色状态指示灯 (高电平点亮)
  - GPIO 0: 系统复位/功能按键 (按下为低电平)

## 🚀 软件架构

- **后端框架**: [Microdot](lib/microdot.py) - 专为微控制器优化的轻量级 Web 框架。
- **数据库**: **JSONL (JSON Lines)** - 流式数据库系统，支持在极低内存下处理大数据文件。
- **网络管理**: [WifiConnector](lib/WifiConnector.py) - 增强型网络连接器，支持静态 IP。
- **前端技术**: 原生 HTML5 / CSS3 / JavaScript (ES6+)，采用 SPA (单页应用) 架构。

## 📂 目录结构

根据 [技术开发规范 (rules.md)](rules.md) 的要求，项目采用以下结构：

```text
.
├── doc/                # 项目参考资料与说明文档
├── src/                # 源代码根目录
│   ├── boot.py         # 系统启动引导程序 (硬件初始化/网络连接)
│   ├── main.py         # 主应用程序入口 (路由定义/业务逻辑)
│   ├── lib/            # 核心功能组件库
│   ├── data/           # 持久化 JSON/JSONL 数据文件
│   └── static/         # 前端 Web 资源 (HTML/CSS/JS)
├── rules.md            # 技术开发规范
└── README.md           # 本说明文档
```
*注：当前部署中，源代码文件直接位于根目录下。*

## 📥 安装与部署

1. **环境准备**: 确保 ESP32-S2 已刷入最新的 MicroPython 固件。
2. **配置文件**: 修改 `data/config.json`，配置您的 WiFi SSID 和密码。
3. **上传代码**: 使用 Thonny、WebREPL 或 `ampy` 将所有文件上传至 ESP32 根目录。
4. **运行**: 重启开发板，系统将自动执行 `boot.py` 连接网络并启动 `main.py`。
5. **访问**: 在浏览器中输入 ESP32 的 IP 地址（可通过串口查看或使用默认 AP 地址 `192.168.4.1`）。

## 规范与原则

后续开发请严格遵守 [rules.md](rules.md) 中的定义：
- **内存优先**: 必须通过逐行读取和 `gc.collect()` 严格控制内存占用。
- **中文标准**: 代码注释、界面文字统一使用中文。
- **异步交互**: 前端必须使用 `async/await` 处理所有网络请求。

## 📄 许可证

本项目采用 [GPL V3 许可证](LICENSE)。

---
**版本**: v1.0.0  
**更新日期**: 2026年1月31日  
**维护者**: 围炉诗社理事会
