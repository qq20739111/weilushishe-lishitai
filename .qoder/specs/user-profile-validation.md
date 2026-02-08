# 用户资料前端验证优化方案

## 概述

针对用户资料提交（包括成员录入、个人资料修改）的前端合规性验证进行分析和完善，重点解决：
1. 基础字段验证缺失（手机号格式、密码强度、姓名长度等）
2. 自定义字段无验证机制
3. 错误提示体验不佳（全局alert）

## 一、当前问题分析

### 高风险缺陷
| 问题 | 当前状态 | 影响 |
|------|----------|------|
| 手机号格式 | 仅检查非空 | 可输入任意字符 |
| 新建成员密码 | 无长度验证 | 可设置单字符密码 |
| 自定义字段 | 完全无验证 | 类型、必填均无校验 |
| 姓名长度 | 仅检查非空 | 可输入超长文本 |

### 中等风险缺陷
- 雅号/花名无长度限制
- 生日依赖HTML控件，后端无验证
- 积分值无范围检查
- 自定义字段配置无"必填"属性支持

## 二、实施方案

### 阶段1：添加验证基础设施

**文件**: `src/static/app.js`

1. 在第26行（`_customFields`声明后）添加验证规则配置：
```javascript
const VALIDATION_RULES = {
    name: { required: true, maxLength: 20, ... },
    phone: { required: true, pattern: /^1[3-9]\d{9}$/, ... },
    password: { required: true, minLength: 6, maxLength: 32, checkStrength: true, ... },
    // ...其他字段规则
};
```

2. 在全局工具函数区域添加：
   - `validateField(fieldName, value, rule, context)` - 单字段验证
   - `validateForm(formData, rules)` - 批量验证
   - `validateCustomFields(customFields, customData)` - 自定义字段验证
   - `showFieldError(inputElement, errorMsg)` - 显示字段错误
   - `clearFieldError(inputElement)` - 清除字段错误
   - `clearFormErrors(formSelector)` - 清除表单所有错误

**文件**: `src/static/style.css`

在文件末尾添加错误提示样式（约25行CSS）

### 阶段2：改造成员录入验证

**文件**: `src/static/app.js`

改造 `submitMember()` 函数（第1490-1566行）：
- 提交前清除旧错误
- 验证基础字段（name、phone、password强度：至少6位+两种字符类型）
- 验证自定义字段（类型匹配、必填检查）
- 验证失败时显示字段级错误，阻止提交

### 阶段3：改造个人资料验证

**文件**: `src/static/app.js`

1. 改造 `saveProfile()` 函数（第518-577行）：
   - 增加alias长度验证
   - 增加birthday日期有效性验证

2. 改造 `submitProfilePassword()` 函数（第579-637行）：
   - 将alert验证改为字段级错误提示

### 阶段4：自定义字段必填支持

**文件**: `src/static/app.js`

1. 修改 `openMemberModal()` 中的自定义字段渲染（第1420-1485行附近）：
   - 为必填字段label添加 `*` 标记

2. 修改自定义字段添加功能：
   - 增加"必填项"复选框

**文件**: `src/data/config.json`
- 自定义字段配置结构添加 `required` 属性支持

## 三、关键修改文件

| 文件 | 修改内容 |
|------|----------|
| `src/static/app.js` | 新增验证函数、改造3个提交函数 |
| `src/static/style.css` | 新增错误提示CSS样式 |
| `src/static/index.html` | 可选：自定义字段配置界面增强 |
| `src/data/config.json` | 自定义字段结构升级（required属性） |

## 四、验证规则详情

### 基础字段规则
```
姓名(name): 必填, 1-20字符
雅号(alias): 可选, 最长20字符
手机号(phone): 必填, 正则 /^1[3-9]\d{9}$/
密码(password): 必填(新建), 6-32字符, 至少包含两种字符类型
              字符类型: 数字、小写字母、大写字母、特殊字符
              验证函数: checkPasswordStrength(pwd)
生日(birthday): 可选, 不晚于今天
积分(points): 可选, 0-999999
```

### 自定义字段规则
```
text: 长度限制
number: 数值有效性
date: 日期格式(YYYY-MM-DD)
email: 邮箱正则验证
textarea: 长度限制
required: 支持配置必填
```

## 五、验证策略

1. **前端优先**: 减少无效API请求，提升用户体验
2. **后端保留**: 手机号唯一性、密码哈希等敏感验证仍依赖后端
3. **渐进增强**: 核心验证优先，实时验证可后续添加

## 六、测试验证

1. 成员录入测试：
   - 空手机号 -> 提示"手机号为必填项"
   - 手机号"12345" -> 提示"请输入有效的手机号码"
   - 密码"abc" -> 提示"密码长度至少6位"
   - 密码"123456" -> 提示"密码需包含至少两种字符类型"
   - 密码"abc123" -> 通过验证
   - 自定义必填字段为空 -> 提示"XX为必填项"

2. 个人资料测试：
   - 雅号超过20字符 -> 提示"雅号不能超过20个字符"
   - 生日为未来日期 -> 提示"生日不能晚于今天"

3. 密码修改测试：
   - 字段级错误提示替代全局alert
   - 新密码"12345" -> 提示"密码长度至少6位"
   - 新密码"aaaaaa" -> 提示"密码需包含至少两种字符类型"
   - 新密码"abc123" -> 通过强度验证
