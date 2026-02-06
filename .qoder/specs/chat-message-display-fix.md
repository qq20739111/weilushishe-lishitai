# 聊天室用户状态切换Bug修复计划

## 问题描述

用户以游客模式访问聊天室（摆龙门阵），再以注册用户登陆后，发送的消息显示在左侧（别人的消息位置），而不是右侧（自己的消息位置）。

## 问题根源

1. **状态变量未更新**：聊天室状态变量 `_chatUserId` 在用户登录后仍保持游客ID（负数）
2. **守卫逻辑阻断**：`joinChat()` 函数中 `if (_chatJoined) return true;` 导致登录后无法重新获取新身份
3. **缺少状态重置**：`login()` 和 `logout()` 函数没有重置聊天室状态

**代码链路**：
- 游客访问聊天室 → `joinChat()` → `_chatUserId = -1`（游客ID），`_chatJoined = true`
- 用户登录 → `login()` → `checkLogin()` → `currentUser` 更新，但 `_chatUserId` 仍为 -1
- 用户发送消息 → 后端返回 `msg.user_id = 123`（登录用户ID）
- 判断 `isSelf = msg.user_id === _chatUserId` → `123 === -1` → `false`
- 消息显示在左侧（别人的位置）

## 修复方案

### 核心修改文件

**`src/static/app.js`**

### 修改内容

#### 1. 新增 `resetChatState()` 函数（约3453行，状态变量定义后）

```javascript
/**
 * 重置聊天室状态（用于登录/登出时重新获取身份）
 */
function resetChatState() {
    // 停止轮询
    stopChatPolling();
    
    // 重置状态变量
    _chatUserId = null;
    _chatUserName = null;
    _chatIsGuest = false;
    _chatJoined = false;
    _chatLastMsgId = 0;
}
```

#### 2. 修改 `login()` 函数（约371-381行）

在登录成功后、调用 `checkLogin()` 之前，添加聊天室状态重置：

```javascript
if (res.ok) {
    const user = await res.json();
    // ... 处理 token_expire ...
    localStorage.setItem('user', JSON.stringify(user));
    window._maintenanceLoginMode = false;
    resetChatState();  // 新增：重置聊天室状态
    checkLogin();
}
```

#### 3. 修改 `logout()` 函数（约399-404行）

在登出时先重置聊天室状态：

```javascript
function logout() {
    resetChatState();  // 新增：重置聊天室状态
    localStorage.removeItem('user');
    currentUser = null;
    checkLogin();
}
```

### 修改位置汇总

| 位置 | 修改内容 |
|------|----------|
| app.js ~3453行 | 新增 `resetChatState()` 函数 |
| app.js ~380行 | `login()` 中添加 `resetChatState()` 调用 |
| app.js ~400行 | `logout()` 开头添加 `resetChatState()` 调用 |

## 验证方案

### 测试场景

1. **游客→登录→发消息**
   - 以游客身份访问聊天室
   - 点击登录
   - 登录后发送消息
   - 预期：消息显示在右侧

2. **登录→登出→发消息**
   - 以登录用户访问聊天室
   - 登出
   - 发送消息
   - 预期：以新游客身份发送，消息显示在右侧

3. **游客→登录→切换页面→返回聊天**
   - 游客访问聊天室
   - 切换到其他页面并登录
   - 返回聊天室
   - 预期：自动以登录用户身份重新加入

### 验证步骤

1. 启动ESP32设备或本地开发服务器
2. 以游客模式访问聊天室
3. 登录注册账号
4. 发送消息，验证显示在右侧
5. 检查浏览器控制台无错误
