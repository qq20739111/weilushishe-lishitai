# 数据验证工具集
# 纯函数模块，无外部依赖


def validate_phone(phone):
    """
    验证手机号格式
    规则: 11位数字，以1开头，第二位为3-9
    返回: (valid: bool, error: str|None)
    """
    if not phone:
        return False, '手机号为必填项'
    if not isinstance(phone, str):
        phone = str(phone)
    # 简化正则：11位数字，1开头，第二位3-9
    if len(phone) != 11:
        return False, '请输入有效的手机号码（11位）'
    if phone[0] != '1' or phone[1] not in '3456789':
        return False, '请输入有效的手机号码'
    for c in phone:
        if c not in '0123456789':
            return False, '请输入有效的手机号码'
    return True, None


def validate_password_strength(password):
    """
    验证密码强度
    规则: 至少6位，包含至少两种字符类型（数字、小写字母、大写字母、特殊字符）
    返回: (valid: bool, error: str|None)
    """
    if not password:
        return False, '密码为必填项'
    if len(password) < 6:
        return False, '密码长度至少6位'
    if len(password) > 32:
        return False, '密码长度不能超过32位'
    
    # 检查字符类型
    type_count = 0
    has_digit = False
    has_lower = False
    has_upper = False
    has_special = False
    
    for c in password:
        if c.isdigit():
            has_digit = True
        elif c.islower():
            has_lower = True
        elif c.isupper():
            has_upper = True
        else:
            has_special = True
    
    type_count = sum([has_digit, has_lower, has_upper, has_special])
    if type_count < 2:
        return False, '密码需包含至少两种字符类型（数字、小写字母、大写字母、特殊字符）'
    
    return True, None


def validate_name(name, max_length=10):
    """
    验证姓名
    规则: 必填，1-10字符
    返回: (valid: bool, error: str|None)
    """
    if not name:
        return False, '姓名为必填项'
    if len(name) > max_length:
        return False, f'姓名不能超过{max_length}个字符'
    return True, None


def validate_alias(alias, max_length=10):
    """
    验证雅号
    规则: 可选，最长10字符
    返回: (valid: bool, error: str|None)
    """
    if alias and len(alias) > max_length:
        return False, f'雅号不能超过{max_length}个字符'
    return True, None


def validate_birthday(birthday):
    """
    验证生日
    规则: 可选，格式YYYY-MM-DD，只校验格式正确性
    返回: (valid: bool, error: str|None)
    """
    if not birthday:
        return True, None  # 可选字段
    
    # 简单格式检查
    if len(birthday) != 10 or birthday[4] != '-' or birthday[7] != '-':
        return False, '日期格式不正确，应为YYYY-MM-DD'
    
    try:
        year = int(birthday[:4])
        month = int(birthday[5:7])
        day = int(birthday[8:10])
        
        # 基本范围检查
        if month < 1 or month > 12:
            return False, '月份应在1-12之间'
        if day < 1 or day > 31:
            return False, '日期应在1-31之间'
        
    except (ValueError, TypeError):
        return False, '日期格式不正确'
    
    return True, None


def validate_points(points):
    """
    验证积分
    规则: 可选，数字，范围0-999999
    返回: (valid: bool, error: str|None)
    """
    if points is None or points == '':
        return True, None
    
    try:
        p = int(points)
        if p < 0:
            return False, '积分值不能小于0'
        if p > 999999:
            return False, '积分值不能超过999999'
    except (ValueError, TypeError):
        return False, '积分值必须是数字'
    
    return True, None


def validate_custom_fields(custom_data, custom_fields_config):
    """
    验证自定义字段
    custom_data: 用户提交的自定义字段数据 {field_id: value}
    custom_fields_config: 自定义字段配置列表 [{id, label, type, required}, ...]
    返回: (valid: bool, error: str|None)
    """
    if not custom_fields_config:
        return True, None
    
    for field in custom_fields_config:
        field_id = field.get('id')
        label = field.get('label', '自定义字段')
        field_type = field.get('type', 'text')
        required = field.get('required', False)
        
        value = custom_data.get(field_id, '') if custom_data else ''
        
        # 必填检查
        if required and not value:
            return False, f'{label}为必填项'
        
        # 空值跳过后续验证
        if not value:
            continue
        
        # 类型验证
        if field_type == 'number':
            try:
                float(value)
            except (ValueError, TypeError):
                return False, f'{label}必须是有效的数字'
        elif field_type == 'email':
            if '@' not in value or '.' not in value:
                return False, f'{label}格式不正确'
        elif field_type == 'date':
            valid, err = validate_birthday(value)  # 复用日期验证
            if not valid:
                return False, f'{label}格式不正确'
    
    return True, None
