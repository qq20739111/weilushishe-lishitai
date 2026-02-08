# Token密钥与密码密钥分离方案

## 目标

将 Token 签名密钥与密码哈希盐值分离。密码盐值(`password_salt`)保持持久化存储不变，Token 签名密钥改为每次服务器启动时随机生成 128 位(16字节)。

## 影响

- 服务器重启后所有已登录用户的 Token 自动失效，需重新登录
- 密码哈希逻辑不受影响（继续使用 config.json 中的 `password_salt`）
- 前端无需修改（已有 401 错误处理和重新登录引导逻辑）

## 修改文件

仅修改 `src/main.py`

## 具体修改

### 1. 在第22行(`_system_start_time`)之后新增运行时密钥生成

```python
# 记录系统启动时间（用于计算uptime）
_system_start_time = time.time()

# 运行时Token签名密钥（每次启动随机生成128位，与密码盐值完全独立）
_RUNTIME_TOKEN_SECRET = ubinascii.hexlify(os.urandom(16)).decode('utf-8')
info(f"Token签名密钥已生成（128位随机）", "Security")
```

使用 `os.urandom(16)` 生成16字节随机数，`hexlify` 转为32字符十六进制字符串作为密钥。

### 2. 修改 `_get_token_secret()` 函数（第324-327行）

将：
```python
def _get_token_secret():
    """获取Token签名密钥（使用password_salt作为基础）"""
    settings = get_settings()
    return settings.get('password_salt', 'weilu2018') + '_token_key'
```

改为：
```python
def _get_token_secret():
    """获取Token签名密钥（运行时随机生成，与密码盐值独立，重启后失效）"""
    return _RUNTIME_TOKEN_SECRET
```

### 3. 更新区块注释（第309-314行）

将：
```python
# Token格式: user_id:expire_timestamp:signature
# signature = sha256(user_id:expire_timestamp:secret_key)[:32]
# 默认过期时间: 30天
```

改为：
```python
# Token格式: user_id:expire_timestamp:signature
# signature = sha256(user_id:expire_timestamp:secret_key)[:32]
# 签名密钥: 每次启动随机生成128位，与密码盐值(password_salt)完全独立
# 默认过期时间: 30天
```

## 不需要修改的代码

- `hash_password()` / `verify_password()` — 继续使用 config.json 中的 `password_salt`
- `generate_token()` / `verify_token()` — 内部调用 `_get_token_secret()`, 自动使用新密钥
- 前端 `app.js` — 已有 Token 失效时返回401并跳转登录页的逻辑

## 验证方式

1. 检查 main.py 语法正确性
2. 确认 `_get_token_secret()` 不再依赖 `password_salt`
3. 确认 `hash_password()` 仍然使用 `password_salt`
