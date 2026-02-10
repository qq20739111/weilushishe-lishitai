# 仪表盘设备状态栏 - 添加系统运行时间显示

## 概述
在后台管理仪表盘的"设备状态"卡片中新增"系统运行时间"显示，同时重构网格布局：第一行放3个文本信息项（设备、系统时间、运行时间），第二三行放4个进度条项。后端 API 已支持 `uptime_seconds`，仅需前端改动。

## 需修改的文件
1. `src/static/index.html` — 重排 HTML 元素顺序 + 新增运行时间项
2. `src/static/style.css` — 重构网格布局（6列方案）+ 更新移动端适配
3. `src/static/app.js` — 新增 `formatUptime` 函数 + 渲染逻辑

## 布局设计

### 当前布局（`auto 1fr 1fr` 3列 x 2行）
```
[设备]      [Flash ████] [RAM ████]
[系统时间]  [CPU温度 ██] [WiFi ███]
```

### 目标布局（6列网格，span 控制）
```
[设备 ·····] [系统时间 ···] [运行时间 ···]    ← 3个文本项，各占2列
[Flash ██████████████] [RAM █████████████]    ← 2个进度条，各占3列
[CPU温度 █████████████] [WiFi ████████████]   ← 2个进度条，各占3列
```

设计说明：
- 使用 `grid-template-columns: repeat(6, 1fr)` 6列网格
- 第1行：3个文本项各 `grid-column: span 2`，三等分
- 第2-3行：4个进度条各 `grid-column: span 3`，二等分
- 文本信息与资源监控形成清晰的视觉分区
- 移动端 (<768px) 回退为单列 `1fr`，所有 span 重置

## 实施步骤

### Step 1: HTML — 重排元素顺序 + 新增运行时间
**文件**: `src/static/index.html` (第176-221行)

将 `.system-status-grid` 内的子元素重新排列为以下顺序：

```html
<div class="system-status-grid">
    <!-- 第1行：文本信息 -->
    <div class="status-item status-text-item">
        <span class="status-label">设备</span>
        <span class="status-value" id="admin-platform">-</span>
    </div>
    <div class="status-item status-text-item">
        <span class="status-label">系统时间</span>
        <span class="status-value status-time" id="admin-system-time">-</span>
    </div>
    <div class="status-item status-text-item">
        <span class="status-label">系统运行时间</span>
        <span class="status-value" id="admin-uptime">-</span>
    </div>
    <!-- 第2行：存储 + 内存 -->
    <div class="status-item status-bar-item">
        <!-- Flash 进度条（保持不变） -->
    </div>
    <div class="status-item status-bar-item">
        <!-- RAM 进度条（保持不变） -->
    </div>
    <!-- 第3行：温度 + WiFi -->
    <div class="status-item status-bar-item">
        <!-- CPU温度 进度条（保持不变） -->
    </div>
    <div class="status-item status-bar-item">
        <!-- WiFi信号 进度条（保持不变） -->
    </div>
</div>
```

关键改动：
- 3个文本项（设备、系统时间、运行时间）移到最前面，添加 `.status-text-item` 类
- 4个进度条项紧随其后（Flash、RAM、CPU温度、WiFi）
- 各进度条内部结构不变

### Step 2: CSS — 重构网格布局
**文件**: `src/static/style.css`

#### 2a. 修改主网格（第226-231行）
```css
/* 改动前 */
.system-status-grid {
    display: grid;
    grid-template-columns: auto 1fr 1fr;
    gap: 20px;
    align-items: center;
}

/* 改动后 */
.system-status-grid {
    display: grid;
    grid-template-columns: repeat(6, 1fr);
    gap: 20px 16px;
    align-items: center;
}
```

#### 2b. 新增 span 规则（第231行后插入）
```css
/* 文本信息项：每项占2列（3项 x 2列 = 6列） */
.status-text-item {
    grid-column: span 2;
}

/* 进度条项：每项占3列（2项 x 3列 = 6列） */
.system-status-grid .status-bar-item {
    grid-column: span 3;
}
```

#### 2c. 更新移动端适配（第1166-1177行）
```css
/* 改动前 */
.system-status-grid {
    grid-template-columns: 1fr;
    gap: 15px;
}
.status-item:first-child {
    flex-direction: row;
    justify-content: space-between;
    align-items: center;
    padding-bottom: 12px;
    border-bottom: 1px solid var(--border);
}

/* 改动后 */
.system-status-grid {
    grid-template-columns: 1fr;
    gap: 15px;
}
.status-text-item,
.system-status-grid .status-bar-item {
    grid-column: span 1;
}
.status-item:first-child {
    flex-direction: row;
    justify-content: space-between;
    align-items: center;
    padding-bottom: 12px;
    border-bottom: 1px solid var(--border);
}
```

### Step 3: JS — 新增 formatUptime 工具函数
**文件**: `src/static/app.js`
**位置**: 在现有工具函数区域附近（如 `formatBytes` 函数附近）

```javascript
function formatUptime(seconds) {
    const days = Math.floor(seconds / 86400);
    const hours = Math.floor((seconds % 86400) / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    if (days > 0) return `${days}天${hours}小时${minutes}分`;
    if (hours > 0) return `${hours}小时${minutes}分${secs}秒`;
    if (minutes > 0) return `${minutes}分${secs}秒`;
    return `${secs}秒`;
}
```

### Step 4: JS — 在 loadSystemInfo() 中渲染运行时间
**文件**: `src/static/app.js`
**位置**: `loadSystemInfo()` 函数内，系统时间显示代码之后（约第3260行）

```javascript
// 系统运行时间显示
const uptimeEl = document.getElementById('admin-uptime');
if (uptimeEl && info.uptime_seconds !== undefined) {
    uptimeEl.innerText = formatUptime(info.uptime_seconds);
}
```

## 验证方案
1. 访问后台管理仪表盘，确认"设备状态"卡片布局：
   - 第1行：设备、系统时间、运行时间（3个文本项等宽排列）
   - 第2行：Flash存储、RAM使用（2个进度条等宽排列）
   - 第3行：CPU温度、WiFi信号（2个进度条等宽排列）
2. 确认运行时间格式正确（秒/分/时/天级别）
3. 浏览器缩至 <768px，确认移动端单列布局，所有 span 重置正常
4. 浏览器 768-1279px，确认平板端布局正常
5. 浏览器 >=1280px，确认PC端完整3行布局
