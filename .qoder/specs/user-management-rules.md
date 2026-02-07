# 超级管理员权限保护实现计划

## 需求分析

用户需求：
1. 所有用户都不能通过用户管理（社员）来添加超级管理员
2. 禁止删除超级管理员
3. 超级管理员只有唯一的1个
4. 超级管理员的角色不能被变更
5. 有且仅有超级管理员自己能够通过社员编辑来修改自己除了角色以外的其它用户资料
6. 超级管理员不能删除自己
7. 超级管理员不能改变自己的角色

## 当前实现状态

| 需求 | 状态 | 说明 |
|------|------|------|
| 1. 禁止添加超管 | ✅ 已实现 | `can_assign_role` 函数已禁止 |
| 2. 禁止删除超管 | ✅ 已实现 | `delete_member_route` 中已检查 |
| 3. 超管唯一 | ✅ 已满足 | 通过 #1 保证 |
| 4. 超管角色不可变更 | ❌ 未实现 | 需在后端添加检查 |
| 5. 仅超管自己可编辑自己 | ❌ 未实现 | 需修改权限检查逻辑 |
| 6. 超管不能删除自己 | ⚠️ 部分实现 | 当前只检查目标，未检查操作者 |
| 7. 超管不能改自己角色 | ❌ 未实现 | 需在前后端添加检查 |

---

## 修改方案

### 一、后端修改 (`src/main.py`)

#### 1. 修改 `can_manage_member` 函数 (L577-594)

当前实现：
```python
def can_manage_member(operator_role, target_member_role):
    # 超级管理员可以管理所有用户
    if operator_role == 'super_admin':
        return True, None
    # 不能管理权限比自己高或相同的用户
    if target_level <= operator_level:
        return False, '无权管理此用户'
    return True, None
```

修改为（增加 operator_id 和 target_member_id 参数）：
```python
def can_manage_member(operator_id, operator_role, target_member_id, target_member_role):
    """检查操作者是否可以管理目标成员"""
    # 超级管理员只能由自己编辑
    if target_member_role == 'super_admin':
        if operator_id == target_member_id:
            return True, None
        return False, '超级管理员资料只能由其本人修改'
    
    # 超级管理员可以管理其他所有用户
    if operator_role == 'super_admin':
        return True, None
    
    # 不能管理权限比自己高或相同的用户
    operator_level = ROLE_LEVEL.get(operator_role, 3)
    target_level = ROLE_LEVEL.get(target_member_role, 3)
    if target_level <= operator_level:
        return False, '无权管理此用户'
    return True, None
```

#### 2. 修改 `update_member_route` 函数 (L1345-1412)

在 L1365-1368 的权限检查处修改调用方式，并添加角色保护：
```python
# 获取操作者ID和角色
operator_id, operator_role = get_operator_role(request)

# 检查是否有权限管理此成员（传入操作者ID和目标成员ID）
allowed, manage_err = can_manage_member(operator_id, operator_role, mid, target_member_role)
if not allowed:
    return Response(json.dumps({"error": manage_err}), 403, ...)

# 超级管理员角色不可变更
if target_member_role == 'super_admin' and 'role' in data:
    if data.get('role') != 'super_admin':
        return Response('{"error": "超级管理员角色不可变更"}', 400, ...)
```

#### 3. 修改 `delete_member_route` 函数 (L1455-1466)

在现有检查前添加自删除检查：
```python
# 获取操作者ID
operator_id, _ = get_operator_role(request)

# 不能删除自己
if member_id == operator_id:
    return Response('{"error": "不能删除自己的账号"}', 400, ...)

# 已有的超管保护检查保持不变
```

---

### 二、前端修改 (`src/static/app.js`)

#### 1. 修改 `canManageMember` 函数 (L1179-1188)

当前实现：
```javascript
function canManageMember(operatorRole, targetMemberRole) {
    if (operatorRole === 'super_admin') return true;
    return targetLevel > operatorLevel;
}
```

修改为（增加 operatorId 和 targetMemberId 参数）：
```javascript
function canManageMember(operatorId, operatorRole, targetMemberId, targetMemberRole) {
    // 超级管理员只能由自己编辑
    if (targetMemberRole === 'super_admin') {
        return operatorId === targetMemberId;
    }
    // 超级管理员可以管理其他所有用户
    if (operatorRole === 'super_admin') return true;
    // 不能管理权限比自己高或相同的用户
    const operatorLevel = ROLE_LEVEL[operatorRole] ?? 3;
    const targetLevel = ROLE_LEVEL[targetMemberRole] ?? 3;
    return targetLevel > operatorLevel;
}
```

#### 2. 修改 `fetchMembers` 函数中的调用 (L1253)

```javascript
// 当前：
const canEditThis = canEdit && canManageMember(currentUser?.role, m.role);

// 修改为：
const canEditThis = canEdit && canManageMember(currentUser?.id, currentUser?.role, m.id, m.role);
```

#### 3. 修改 `fetchMembers` 中删除按钮逻辑 (L1285)

```javascript
// 当前：
${canDelete ? `<button class="btn-remove" onclick="deleteMember(${m.id})">移除</button>` : ''}

// 修改为（超级管理员不显示删除按钮）：
${(canDelete && m.role !== 'super_admin') ? `<button class="btn-remove" onclick="deleteMember(${m.id})">移除</button>` : ''}
```

#### 4. 修改 `openMemberModal` 函数中的角色控制 (L1312)

```javascript
// 当前：
const canChangeRole = canManageMember(currentUser?.role, member.role);

// 修改为：
const canChangeRole = canManageMember(currentUser?.id, currentUser?.role, member.id, member.role);

// 超级管理员编辑自己时，角色下拉框禁用
if (member.role === 'super_admin') {
    roleSelect.innerHTML = `<option value="super_admin">超级管理员</option>`;
    roleSelect.disabled = true;
}
```

#### 5. 修改 `deleteMember` 函数 (L1450-1456)

```javascript
// 在现有超管检查后添加自删除检查
if (member && member.id === currentUser?.id) {
    alert('不能删除自己的账号');
    return;
}
```

---

## 关键文件清单

| 文件 | 修改位置 | 修改内容 |
|------|----------|----------|
| `src/main.py` | L577-594 | 重构 `can_manage_member` 函数 |
| `src/main.py` | L1365-1368 | 修改调用并添加角色保护 |
| `src/main.py` | L1457-1458 | 添加自删除检查 |
| `src/static/app.js` | L1179-1188 | 重构 `canManageMember` 函数 |
| `src/static/app.js` | L1253 | 修改函数调用 |
| `src/static/app.js` | L1285 | 隐藏超管删除按钮 |
| `src/static/app.js` | L1312 | 修改函数调用并禁用角色选择 |
| `src/static/app.js` | L1450-1456 | 添加自删除检查 |

---

## 验证方案

### 测试场景 1：添加超管
- 以任何角色登录 → 新增社员 → 角色选择框不应包含"超级管理员"选项

### 测试场景 2：编辑超管
- 以管理员登录 → 查看超管卡片 → 编辑按钮应禁用
- 以超管登录 → 编辑自己 → 可修改姓名/雅号等，角色下拉框禁用

### 测试场景 3：修改超管角色（API直接测试）
- POST `/api/members/update` 尝试将超管角色改为其他 → 应返回 400 错误

### 测试场景 4：删除超管
- 以超管登录 → 自己的卡片不显示"移除"按钮
- 以超管登录 → 尝试通过API删除自己 → 应返回 400 错误
- 以任何角色登录 → 超管卡片不显示"移除"按钮
