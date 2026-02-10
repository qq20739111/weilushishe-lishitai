/**
 * 围炉诗社·理事台 - 前端应用脚本
 * 
 * 功能模块：
 * - 用户认证：登录、登出、个人资料管理
 * - 藏诗阁：诗歌管理（含本地草稿功能）
 * - 活动管理：社团活动的增删改查
 * - 事务与积分：任务认领、审批、积分记录
 * - 财务公示：收支记录管理
 * - 社员管理：成员信息维护
 * - 系统后台：WiFi配置、数据备份、系统设置
 * 
 * 技术特性：
 * - SPA单页应用架构
 * - IndexedDB本地草稿存储
 * - 响应式设计（移动端/平板/PC）
 * - 服务端分页加载
 */

// ============================================================================
// 全局常量和状态
// ============================================================================
const API_BASE = '/api';
let currentUser = null;
let _customFields = [];
let _systemSettings = { points_name: '围炉值' };
let _settingsLoaded = false; // 标记 /api/settings/system 是否已加载

// ============================================================================
// 表单验证规则配置
// ============================================================================
const VALIDATION_RULES = {
    name: {
        required: true,
        minLength: 1,
        maxLength: 10,
        errorMsg: {
            required: '姓名为必填项',
            minLength: '姓名不能为空',
            maxLength: '姓名不能超过10个字符'
        }
    },
    alias: {
        required: false,
        maxLength: 10,
        errorMsg: {
            maxLength: '雅号不能超过10个字符'
        }
    },
    phone: {
        required: true,
        pattern: /^1[3-9]\d{9}$/,
        errorMsg: {
            required: '手机号为必填项',
            pattern: '请输入有效的手机号码（11位，以1开头）'
        }
    },
    password: {
        required: true,
        minLength: 6,
        maxLength: 32,
        checkStrength: true,
        errorMsg: {
            required: '密码为必填项',
            minLength: '密码长度至少6位',
            maxLength: '密码长度不能超过32位',
            strength: '密码需包含至少两种字符类型（数字、小写字母、大写字母、特殊字符）'
        }
    },
    birthday: {
        required: false,
        type: 'date',
        errorMsg: {
            format: '日期格式不正确'
        }
    },
    points: {
        required: false,
        type: 'number',
        min: 0,
        max: 999999,
        errorMsg: {
            min: '积分值不能小于0',
            max: '积分值不能超过999999'
        }
    },
    wifi_ssid: {
        required: true,
        minLength: 1,
        maxLength: 32,
        errorMsg: {
            required: 'WiFi名称为必填项',
            minLength: 'WiFi名称不能为空',
            maxLength: 'WiFi名称不能超过32个字符'
        }
    },
    wifi_password: {
        required: false,
        minLength: 8,
        maxLength: 63,
        errorMsg: {
            minLength: 'WiFi密码长度必须为8-63个字符',
            maxLength: 'WiFi密码长度必须为8-63个字符'
        }
    },
    ap_ssid: {
        required: false,
        maxLength: 32,
        errorMsg: {
            maxLength: '热点名称不能超过32个字符'
        }
    },
    ap_password: {
        required: false,
        minLength: 8,
        maxLength: 63,
        errorMsg: {
            minLength: '热点密码长度必须为8-63个字符',
            maxLength: '热点密码长度必须为8-63个字符'
        }
    },
    ipv4: {
        required: false,
        type: 'ipv4',
        errorMsg: {
            format: '请输入有效的IPv4地址（如192.168.1.1）'
        }
    }
};

// Token过期时间（30天）
const TOKEN_EXPIRE_DAYS = 30;

// 角色权限层级（数字越小权限越高）
const ROLE_LEVEL = {
    'super_admin': 0,
    'admin': 1,
    'director': 2,
    'finance': 3,
    'member': 4
};

/**
 * 检查当前用户是否可以设置目标角色
 * @param {string} targetRole - 目标角色
 * @returns {object} { allowed: boolean, error: string|null }
 */
function canAssignRole(targetRole) {
    // 禁止任何人通过录入社员的方式添加超级管理员
    if (targetRole === 'super_admin') {
        return { allowed: false, error: '不能通过此方式添加超级管理员' };
    }
    
    if (!currentUser || !currentUser.role) {
        return { allowed: false, error: '未登录' };
    }
    
    // 理事只能添加社员，不能添加财务
    if (currentUser.role === 'director' && targetRole !== 'member') {
        return { allowed: false, error: '理事只能添加社员' };
    }
    
    const myLevel = ROLE_LEVEL[currentUser.role] ?? 4;
    const targetLevel = ROLE_LEVEL[targetRole] ?? 4;
    
    // 不能分配比自己权限高或相同的角色（超级管理员除外）
    if (currentUser.role !== 'super_admin' && targetLevel <= myLevel) {
        return { allowed: false, error: '不能添加与自己权限相同或更高的角色' };
    }
    
    return { allowed: true, error: null };
}

/**
 * 将token添加到请求数据中
 */
function withToken(data) {
    const token = getAuthToken();
    if (token) {
        return { ...data, token };
    }
    return data;
}

// ============================================================================
// 表单验证函数
// ============================================================================

/**
 * 检查密码强度（至少包含两种字符类型）
 * @param {string} password - 密码
 * @returns {boolean} 是否通过强度检查
 */
function checkPasswordStrength(password) {
    if (!password) return false;
    let typeCount = 0;
    if (/[0-9]/.test(password)) typeCount++;      // 数字
    if (/[a-z]/.test(password)) typeCount++;      // 小写字母
    if (/[A-Z]/.test(password)) typeCount++;      // 大写字母
    if (/[^0-9a-zA-Z]/.test(password)) typeCount++; // 特殊字符
    return typeCount >= 2;
}

/**
 * 验证单个字段
 * @param {string} fieldName - 字段名称
 * @param {*} value - 字段值
 * @param {Object} rule - 验证规则
 * @param {Object} context - 上下文数据（用于跨字段验证）
 * @returns {Object} { valid: boolean, error: string|null }
 */
function validateField(fieldName, value, rule, context = {}) {
    const isEmpty = value === null || value === undefined || value === '';
    
    // 必填检查
    if (rule.required && isEmpty) {
        return { valid: false, error: rule.errorMsg?.required || '此项为必填' };
    }
    
    // 空值且非必填，跳过后续验证
    if (isEmpty) {
        return { valid: true, error: null };
    }
    
    // 长度验证
    if (rule.minLength !== undefined && value.length < rule.minLength) {
        return { valid: false, error: rule.errorMsg?.minLength || `长度至少${rule.minLength}位` };
    }
    if (rule.maxLength !== undefined && value.length > rule.maxLength) {
        return { valid: false, error: rule.errorMsg?.maxLength || `长度不能超过${rule.maxLength}位` };
    }
    
    // 正则模式验证
    if (rule.pattern && !rule.pattern.test(value)) {
        return { valid: false, error: rule.errorMsg?.pattern || '格式不正确' };
    }
    
    // 密码强度验证
    if (rule.checkStrength && !checkPasswordStrength(value)) {
        return { valid: false, error: rule.errorMsg?.strength || '密码强度不足' };
    }
    
    // 数字范围验证
    if (rule.type === 'number') {
        const numValue = Number(value);
        if (isNaN(numValue)) {
            return { valid: false, error: '请输入有效的数字' };
        }
        if (rule.min !== undefined && numValue < rule.min) {
            return { valid: false, error: rule.errorMsg?.min || `不能小于${rule.min}` };
        }
        if (rule.max !== undefined && numValue > rule.max) {
            return { valid: false, error: rule.errorMsg?.max || `不能超过${rule.max}` };
        }
    }
    
    // 日期验证
    if (rule.type === 'date' && rule.maxDate === 'today') {
        const inputDate = new Date(value);
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        if (inputDate > today) {
            return { valid: false, error: rule.errorMsg?.maxDate || '日期不能晚于今天' };
        }
    }
    
    // IPv4地址验证
    if (rule.type === 'ipv4') {
        const ipv4Pattern = /^((25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(25[0-5]|2[0-4]\d|[01]?\d\d?)$/;
        if (!ipv4Pattern.test(value)) {
            return { valid: false, error: rule.errorMsg?.format || '请输入有效的IPv4地址' };
        }
    }
    
    // 密码确认匹配验证
    if (rule.mustMatch && context[rule.mustMatch] !== value) {
        return { valid: false, error: rule.errorMsg?.mustMatch || '两次输入不一致' };
    }
    
    return { valid: true, error: null };
}

/**
 * 批量验证表单字段
 * @param {Object} formData - 表单数据对象 { fieldName: value }
 * @param {Object} rules - 验证规则对象
 * @returns {Object} { valid: boolean, errors: Object, firstError: string|null }
 */
function validateForm(formData, rules) {
    const errors = {};
    let firstError = null;
    
    for (const [fieldName, rule] of Object.entries(rules)) {
        const result = validateField(fieldName, formData[fieldName], rule, formData);
        if (!result.valid) {
            errors[fieldName] = result.error;
            if (!firstError) {
                firstError = result.error;
            }
        }
    }
    
    return {
        valid: Object.keys(errors).length === 0,
        errors: errors,
        firstError: firstError
    };
}

/**
 * 验证自定义字段
 * @param {Array} customFields - 自定义字段配置数组
 * @param {Object} customData - 自定义字段值对象 { fieldId: value }
 * @returns {Object} { valid: boolean, errors: Object }
 */
function validateCustomFields(customFields, customData) {
    const errors = {};
    
    customFields.forEach(field => {
        const value = customData[field.id] || '';
        const isEmpty = value === null || value === undefined || value === '';
        
        // 必填验证
        if (field.required && isEmpty) {
            errors[field.id] = `${field.label}为必填项`;
            return;
        }
        
        // 空值且非必填，跳过后续验证
        if (isEmpty) return;
        
        // 类型特定验证
        switch (field.type) {
            case 'number':
                if (isNaN(Number(value))) {
                    errors[field.id] = `${field.label}必须是有效的数字`;
                }
                break;
            case 'email':
                const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
                if (!emailPattern.test(value)) {
                    errors[field.id] = '请输入有效的邮箱地址';
                }
                break;
            case 'date':
                const dateValue = new Date(value);
                if (isNaN(dateValue.getTime())) {
                    errors[field.id] = `${field.label}格式不正确`;
                }
                break;
        }
    });
    
    return {
        valid: Object.keys(errors).length === 0,
        errors: errors
    };
}

/**
 * 显示字段错误提示
 * @param {HTMLElement} inputElement - 输入框元素
 * @param {string} errorMsg - 错误消息
 */
function showFieldError(inputElement, errorMsg) {
    if (!inputElement) return;
    
    // 添加错误样式
    inputElement.classList.add('field-error');
    
    // 移除旧的错误提示
    const existingError = inputElement.parentNode.querySelector('.error-message');
    if (existingError) {
        existingError.remove();
    }
    
    // 插入新的错误提示
    const errorDiv = document.createElement('div');
    errorDiv.className = 'error-message';
    errorDiv.textContent = errorMsg;
    inputElement.parentNode.insertBefore(errorDiv, inputElement.nextSibling);
}

/**
 * 清除字段错误提示
 * @param {HTMLElement} inputElement - 输入框元素
 */
function clearFieldError(inputElement) {
    if (!inputElement) return;
    
    inputElement.classList.remove('field-error');
    const errorMsg = inputElement.parentNode.querySelector('.error-message');
    if (errorMsg) {
        errorMsg.remove();
    }
}

/**
 * 清除表单所有错误提示
 * @param {string} formSelector - 表单选择器
 */
function clearFormErrors(formSelector) {
    const form = document.querySelector(formSelector);
    if (!form) return;
    
    form.querySelectorAll('.field-error').forEach(el => {
        el.classList.remove('field-error');
    });
    form.querySelectorAll('.error-message').forEach(el => {
        el.remove();
    });
}

/**
 * 显示自定义字段错误
 * @param {Object} errors - 错误对象 { fieldId: errorMsg }
 */
function showCustomFieldErrors(errors) {
    Object.entries(errors).forEach(([fieldId, errorMsg]) => {
        const input = document.querySelector(`.custom-field-input[data-id="${fieldId}"]`);
        if (input) {
            showFieldError(input, errorMsg);
        }
    });
}

// --- 移动端菜单控制 ---
function toggleMobileMenu() {
    const navLinks = document.getElementById('nav-links');
    if(navLinks) {
        navLinks.classList.toggle('active');
    }
}

function closeMobileMenu() {
    const navLinks = document.getElementById('nav-links');
    if(navLinks) {
        navLinks.classList.remove('active');
    }
}

// --- 加载状态和空状态 ---
function showLoading(containerId) {
    const container = document.getElementById(containerId);
    if(container) {
        container.innerHTML = '<div class="loading-spinner"></div>';
    }
}

function showEmptyState(containerId, icon, text, btnText, btnAction) {
    const container = document.getElementById(containerId);
    if(container) {
        let html = `
            <div class="empty-state">
                <div class="empty-state-icon">${icon}</div>
                <div class="empty-state-text">${text}</div>
        `;
        if(btnText && btnAction) {
            html += `<button class="empty-state-btn" onclick="${btnAction}">${btnText}</button>`;
        }
        html += '</div>';
        container.innerHTML = html;
    }
}

// IndexedDB Helper for Local Drafts
const LocalDrafts = {
    dbName: 'PoetryDraftsDB',
    storeName: 'drafts',
    db: null,
    async init() {
        if (this.db) return;
        const self = this;
        return new Promise((resolve, reject) => {
            if (!window.indexedDB) {
                reject(new Error('浏览器不支持IndexedDB'));
                return;
            }
            const request = indexedDB.open(self.dbName, 1);
            request.onerror = e => reject(e.target.error || new Error('IndexedDB打开失败'));
            request.onblocked = () => reject(new Error('IndexedDB被阻塞，请关闭其他标签页'));
            request.onupgradeneeded = e => {
                const db = e.target.result;
                if (!db.objectStoreNames.contains(self.storeName)) {
                    db.createObjectStore(self.storeName, { keyPath: 'id' });
                }
            };
            request.onsuccess = e => {
                self.db = e.target.result;
                resolve();
            };
        });
    },
    async getAll() {
        await this.init();
        return new Promise((resolve, reject) => {
            const tx = this.db.transaction(this.storeName, 'readonly');
            const store = tx.objectStore(this.storeName);
            const request = store.getAll();
            request.onsuccess = () => resolve(request.result || []);
            request.onerror = () => reject(request.error);
        });
    },
    async save(poem) {
        await this.init();
        return new Promise((resolve, reject) => {
            const tx = this.db.transaction(this.storeName, 'readwrite');
            const store = tx.objectStore(this.storeName);
            const request = store.put(poem);
            request.onsuccess = () => resolve();
            request.onerror = () => reject(request.error);
        });
    },
    async delete(id) {
        await this.init();
        return new Promise((resolve, reject) => {
            const tx = this.db.transaction(this.storeName, 'readwrite');
            const store = tx.objectStore(this.storeName);
            const request = store.delete(id);
            request.onsuccess = () => resolve();
            request.onerror = () => reject(request.error);
        });
    }
};

// ============================================================================
// 用户认证模块
// ============================================================================

/**
 * 检查Token是否已过期
 * @returns {boolean} true表示已过期
 */
function isTokenExpired() {
    if (!currentUser || !currentUser.token_expire) {
        return true;
    }
    // token_expire 是时间戳（秒），与当前时间比较
    const now = Math.floor(Date.now() / 1000);
    return now > currentUser.token_expire;
}

/**
 * 获取当前用户的Token
 * @returns {string|null} Token字符串或null
 */
function getAuthToken() {
    if (!currentUser || !currentUser.token) {
        return null;
    }
    if (isTokenExpired()) {
        // Token已过期，清除登录状态
        handleTokenExpired();
        return null;
    }
    return currentUser.token;
}

/**
 * 处理Token过期的情况
 */
function handleTokenExpired() {
    localStorage.removeItem('user');
    currentUser = null;
    updateNavForLoginState();
    alert('登录已过期，请重新登录');
    showLoginPage();
}

/**
 * 检查用户登录状态
 * 从localStorage读取用户信息，验证Token是否过期
 * 未登录也允许访问部分页面
 */
async function checkLogin() {
    const user = localStorage.getItem('user');
    if (user) {
        currentUser = JSON.parse(user);
        // 验证用户数据完整性（必须有id字段）
        if (!currentUser.id) {
            // 老数据缺少id字段，需要重新登录
            localStorage.removeItem('user');
            currentUser = null;
        } else if (isTokenExpired()) {
            // Token已过期，清除登录状态
            localStorage.removeItem('user');
            currentUser = null;
        } else {
            // Token本地未过期，向服务器验证Token是否仍然有效（服务器重启会使Token失效）
            try {
                const token = currentUser.token;
                const res = await fetch(`${API_BASE}/check-token`, {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                if (res.status === 401) {
                    // 静默清除失效的登录状态，页面会自动显示登录界面
                    localStorage.removeItem('user');
                    currentUser = null;
                }
            } catch (e) {
                // 网络异常时保留本地登录状态，不阻塞页面加载
            }
        }
    } else {
        currentUser = null;
    }
    
    // 获取系统设置
    const settings = await checkSystemSettings();
    const isAdmin = currentUser && ['super_admin', 'admin'].includes(currentUser.role);
    
    // 检查维护模式
    if (!settings.site_open && !isAdmin) {
        // 网站未开放且非管理员，显示维护页面
        showMaintenancePage();
        return;
    }
    
    // 检查游客访问控制
    if (!settings.allow_guest && !currentUser) {
        // 禁止游客访问且未登录，显示登录页
        showLoginPage();
        return;
    }
    
    // 正常模式，显示主应用界面
    document.getElementById('maintenance-section').classList.add('hidden');
    document.getElementById('login-section').classList.add('hidden');
    document.getElementById('main-app').classList.remove('hidden');
    
    // 更新导航栏显示
    updateNavForLoginState();
    
    if (currentUser) {
        fetchCustomFields(); // Load custom fields schema
        fetchSystemSettings(); // Load system settings
        updateNavUser(); // Update nav user display
    }
    
    showSection('home');
}

/**
 * 根据登录状态更新导航栏显示
 */
function updateNavForLoginState() {
    const isLoggedIn = !!currentUser;
    
    // 需要登录才能看到的导航项
    document.querySelectorAll('.nav-login-required').forEach(el => {
        el.classList.toggle('hidden', !isLoggedIn);
    });
    
    // 仅游客可见的导航项
    document.querySelectorAll('.nav-guest-only').forEach(el => {
        el.classList.toggle('hidden', isLoggedIn);
    });
}

/**
 * 显示登录页面
 */
function showLoginPage() {
    document.getElementById('main-app').classList.add('hidden');
    document.getElementById('maintenance-section').classList.add('hidden');
    document.getElementById('login-section').classList.remove('hidden');
}

/**
 * 显示维护模式页面
 */
function showMaintenancePage() {
    document.getElementById('main-app').classList.add('hidden');
    document.getElementById('login-section').classList.add('hidden');
    document.getElementById('maintenance-section').classList.remove('hidden');
}

/**
 * 维护模式下的管理员登录入口
 */
function showMaintenanceLogin() {
    document.getElementById('maintenance-section').classList.add('hidden');
    document.getElementById('login-section').classList.remove('hidden');
    // 标记为维护模式登录
    window._maintenanceLoginMode = true;
}

/**
 * 检查维护模式状态
 * @returns {Promise<object>} 系统设置对象
 */
async function checkSystemSettings() {
    try {
        const res = await fetch(`${API_BASE}/settings/system`);
        if (res.ok) {
            const data = await res.json();
            // 缓存到全局，避免 fetchSystemSettings 重复请求
            _systemSettings = Object.assign(_systemSettings, data);
            _settingsLoaded = true;
            // 更新网页标题和页脚站名
            const name = data.system_name || '围炉诗社·理事台';
            document.title = name;
            const footerName = document.getElementById('footer-site-name');
            if (footerName) footerName.textContent = name;
            return data;
        }
    } catch(e) {
        console.error('检查系统设置失败:', e);
    }
    return { site_open: true, allow_guest: true };
}

/**
 * 更新导航栏用户显示
 * 优先显示雅号(alias)，没有则显示姓名(name)
 */
function updateNavUser() {
    const navUserEl = document.getElementById('nav-current-user');
    if(navUserEl && currentUser) {
        // 优先显示雅号(alias)，没有则显示姓名(name)
        const displayName = currentUser.alias || currentUser.name || '用户';
        navUserEl.innerText = displayName;
    }
}

async function login() {
    const phone = document.getElementById('login-phone').value;
    const password = document.getElementById('login-password').value;
    
    if(!phone || !password) { alert('请输入手机号和密码'); return; }

    try {
        const res = await fetch(`${API_BASE}/login`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ phone, password })
        });
        
        if (res.ok) {
            const user = await res.json();
            // 后端返回 expires_in（有效期秒数），前端计算本地过期时间戳
            // 这样避免不同硬件时间纪元差异问题
            if (user.expires_in) {
                user.token_expire = Math.floor(Date.now() / 1000) + user.expires_in;
                delete user.expires_in;  // 移除原字段，只保留计算后的时间戳
            }
            localStorage.setItem('user', JSON.stringify(user));
            window._maintenanceLoginMode = false;
            resetChatState();  // 重置聊天室状态，确保重新获取登录用户身份
            checkLogin();
        } else {
            const err = await res.json().catch(() => ({}));
            if (res.status === 503) {
                // 维护模式，非管理员登录被拒绝
                alert(err.error || '系统维护中，仅管理员可登录');
                if (window._maintenanceLoginMode) {
                    showMaintenancePage();
                }
            } else {
                alert('登录失败: ' + (err.error || '账号或密码错误'));
            }
        }
    } catch (e) {
        alert('登录出错: ' + e.message);
    }
}

function logout() {
    resetChatState();  // 重置聊天室状态，确保重新获取游客身份
    localStorage.removeItem('user');
    currentUser = null;
    // 重新检查登录状态和系统设置（allow_guest检查）
    checkLogin();
}

/**
 * 获取带Token的请求头（用于POST/PUT等请求）
 * @param {object} extraHeaders - 额外的请求头
 * @returns {object} 请求头对象
 */
function getAuthHeaders(extraHeaders = {}) {
    const headers = { 'Content-Type': 'application/json', ...extraHeaders };
    const token = getAuthToken();
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }
    return headers;
}

/**
 * 封装带认证的fetch请求
 * 统一通过 Authorization Header 传输Token（避免Token暴露在URL中）
 * @param {string} url - 请求URL
 * @param {object} options - fetch选项
 * @returns {Promise<Response>}
 */
async function fetchWithAuth(url, options = {}) {
    const token = getAuthToken();
    
    // 如果没有登录或Token过期，某些请求需要拒绝
    if (!token && options.requireAuth) {
        throw new Error('请先登录');
    }
    
    // 所有请求统一通过 Header 传输 Token
    options.headers = options.headers || {};
    if (!options.method || options.method.toUpperCase() === 'GET') {
        // GET 请求不需要 Content-Type
    } else {
        options.headers['Content-Type'] = options.headers['Content-Type'] || 'application/json';
    }
    if (token) {
        options.headers['Authorization'] = `Bearer ${token}`;
    }
    
    const response = await fetch(url, options);
    
    // 如果返回401，Token已失效（可能是服务器重启或Token过期）
    if (response.status === 401 && currentUser) {
        handleTokenExpired();
    }
    
    return response;
}

// --- 修改密码 ---
function openProfileModal() {
    if(!currentUser) return;
    
    // 显示用户信息
    const displayName = currentUser.alias || currentUser.name || '用户';
    document.getElementById('profile-display-name').innerText = displayName;
    document.getElementById('profile-role').innerText = getRoleName(currentUser.role);
    document.getElementById('profile-avatar').innerText = displayName.charAt(0).toUpperCase();
    
    // 填充表单
    document.getElementById('profile-alias').value = currentUser.alias || '';
    document.getElementById('profile-birthday').value = currentUser.birthday || '';
    
    // 清空密码字段
    document.getElementById('profile-old-password').value = '';
    document.getElementById('profile-new-password').value = '';
    document.getElementById('profile-confirm-password').value = '';
    
    toggleModal('modal-profile');
}

function getRoleName(role) {
    const roleMap = {
        'super_admin': '超级管理员',
        'admin': '管理员',
        'director': '理事',
        'finance': '财务',
        'member': '社员'
    };
    return roleMap[role] || '社员';
}

async function saveProfile() {
    const alias = document.getElementById('profile-alias').value.trim();
    const birthday = document.getElementById('profile-birthday').value;
    
    // 检查登录状态
    if(!getAuthToken()) {
        alert('操作失败：登录已过期，请重新登录后再试');
        return;
    }
    
    // 清除之前的错误提示
    clearFormErrors('#modal-profile');
    
    // 验证字段
    let hasError = false;
    
    // 雅号验证
    const aliasResult = validateField('alias', alias, VALIDATION_RULES.alias);
    if (!aliasResult.valid) {
        showFieldError(document.getElementById('profile-alias'), aliasResult.error);
        hasError = true;
    }
    
    // 生日验证
    if (birthday) {
        const birthdayResult = validateField('birthday', birthday, VALIDATION_RULES.birthday);
        if (!birthdayResult.valid) {
            showFieldError(document.getElementById('profile-birthday'), birthdayResult.error);
            hasError = true;
        }
    }
    
    if (hasError) {
        return;
    }
    
    // 获取保存按钮并禁用，防止重复提交
    const btn = document.querySelector('#modal-profile button[onclick*="saveProfile"]');
    const oldText = btn ? btn.innerText : '';
    if (btn) {
        btn.disabled = true;
        btn.innerText = '保存中...';
    }
    
    try {
        const res = await fetchWithAuth(`${API_BASE}/profile/update`, {
            method: 'POST',
            body: JSON.stringify({
                id: currentUser.id,
                alias: alias,
                birthday: birthday
            })
        });
        
        if (res.ok) {
            // 更新本地用户数据
            currentUser.alias = alias;
            currentUser.birthday = birthday;
            localStorage.setItem('user', JSON.stringify(currentUser));
            
            // 清空成员缓存，使其他页面能够加载最新的用户信息
            _cachedMembers = [];
            
            // 更新导航栏显示
            updateNavUser();
            
            // 更新模态框显示
            const displayName = alias || currentUser.name || '用户';
            document.getElementById('profile-display-name').innerText = displayName;
            document.getElementById('profile-avatar').innerText = displayName.charAt(0).toUpperCase();
            
            alert('资料保存成功');
        } else {
            const data = await res.json();
            alert('保存失败: ' + (data.error || '未知错误'));
        }
    } catch (e) {
        console.error(e);
        alert('网络错误，请重试');
    } finally {
        if (btn) {
            btn.innerText = oldText;
            btn.disabled = false;
        }
    }
}

async function submitProfilePassword() {
    const oldPwd = document.getElementById('profile-old-password').value;
    const newPwd = document.getElementById('profile-new-password').value;
    const confirmPwd = document.getElementById('profile-confirm-password').value;
    
    // 清除之前的错误提示（只清除密码相关字段）
    clearFieldError(document.getElementById('profile-old-password'));
    clearFieldError(document.getElementById('profile-new-password'));
    clearFieldError(document.getElementById('profile-confirm-password'));
    
    // 验证字段
    let hasError = false;
    
    if (!oldPwd) {
        showFieldError(document.getElementById('profile-old-password'), '请输入原密码');
        hasError = true;
    }
    
    if (!newPwd) {
        showFieldError(document.getElementById('profile-new-password'), '请输入新密码');
        hasError = true;
    } else {
        // 新密码验证（长度+强度）
        const pwdResult = validateField('password', newPwd, VALIDATION_RULES.password);
        if (!pwdResult.valid) {
            showFieldError(document.getElementById('profile-new-password'), pwdResult.error);
            hasError = true;
        }
    }
    
    if (!confirmPwd) {
        showFieldError(document.getElementById('profile-confirm-password'), '请确认新密码');
        hasError = true;
    } else if (newPwd && newPwd !== confirmPwd) {
        showFieldError(document.getElementById('profile-confirm-password'), '两次输入的新密码不一致');
        hasError = true;
    }
    
    if (hasError) {
        return;
    }
    
    // 获取修改密码按钮并禁用，防止重复提交
    const btn = document.querySelector('#modal-profile button[onclick*="submitProfilePassword"]');
    const oldText = btn ? btn.innerText : '';
    if (btn) {
        btn.disabled = true;
        btn.innerText = '修改中...';
    }
    
    try {
        const res = await fetch(`${API_BASE}/members/change_password`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(withToken({
                id: currentUser.id,
                old_password: oldPwd,
                new_password: newPwd
            }))
        });
        
        if (res.ok) {
            alert('密码修改成功');
            // 清空密码字段
            document.getElementById('profile-old-password').value = '';
            document.getElementById('profile-new-password').value = '';
            document.getElementById('profile-confirm-password').value = '';
        } else {
            const data = await res.json();
            alert('修改失败: ' + (data.error || '未知错误'));
        }
    } catch (e) {
        console.error(e);
        alert('网络错误，请重试');
    } finally {
        if (btn) {
            btn.innerText = oldText;
            btn.disabled = false;
        }
    }
}

// ============================================================================
// 页面导航模块
// ============================================================================
let _lastSection = 'home';

/**
 * 切换显示指定页面区块
 * @param {string} id - 要显示的区块ID (home/poems/activities/tasks/members/finance/settings)
 * 自动隐藏其他区块，并根据区块类型加载对应数据
 */
function showSection(id) {
    // 未登录用户只能访问特定页面
    const guestAllowedSections = ['home', 'activities', 'poems', 'members', 'chat'];
    if (!currentUser && !guestAllowedSections.includes(id)) {
        // 提示用户需要登录
        alert('请先登录后再访问此功能');
        showLoginPage();
        return;
    }
    
    // Track history (except for search results view)
    if (id !== 'search-results-section') {
        _lastSection = id;
    }

    document.querySelectorAll('main > section').forEach(el => el.classList.add('hidden'));
    document.getElementById(id).classList.remove('hidden');
    
    // Toggle Search Bar Visibility
    // Only show on: home, activities, poems, tasks
    const searchContainer = document.querySelector('.search-container');
    if (searchContainer) {
        // Keep visible if in search-results-section so user can clear/edit
        const visibleSections = ['home', 'activities', 'poems', 'tasks', 'search-results-section'];
        // 未登录时搜索框只在允许的页面显示
        const shouldShow = visibleSections.includes(id) && (currentUser || guestAllowedSections.includes(id));
        searchContainer.classList.toggle('hidden', !shouldShow);
    }
    // 热力图仅在首页可见
    const heatmapContainer = document.getElementById('weekly-heatmap-container');
    if (heatmapContainer) {
        heatmapContainer.classList.toggle('hidden', id !== 'home');
    }
    
    // Auto-fetch data based on section
    if(id === 'poems') fetchPoems();
    if(id === 'activities') fetchActivities();
    if(id === 'members') fetchMembers();
    if(id === 'finance') fetchFinance();
    if(id === 'tasks') fetchTasks();
    if(id === 'chat') initChat();
    if(id === 'home' || id === 'admin') {
        loadSystemInfo();
        // 首页也加载聊天预览（需要先检查chat_enabled设置）
        if(id === 'home') {
            checkChatEnabledAndLoad();
            loadWeeklyHeatmap();
        } else {
            stopHomeChatPolling();   // 离开首页时停止
        }
        if(id === 'admin') {
            renderAdminSettings();
            // 系统页权限控制
            const role = currentUser?.role;
            const isSuperAdmin = role === 'super_admin';
            const isAdmin = ['super_admin', 'admin'].includes(role);
            const isDirector = ['super_admin', 'admin', 'director'].includes(role);
            
            // 超级管理员级别栏目（安全设置、数据备份）
            document.querySelectorAll('.super-admin-only-card').forEach(card => {
                card.classList.toggle('hidden', !isSuperAdmin);
            });
            // 管理员级别栏目（WiFi设置）
            document.querySelectorAll('.admin-only-card').forEach(card => {
                card.classList.toggle('hidden', !isAdmin);
            });
            // 理事级别栏目（系统设置、日志、备份、自定义字段）
            document.querySelectorAll('.director-only-card').forEach(card => {
                card.classList.toggle('hidden', !isDirector);
            });
        }
    } else {
        stopHomeChatPolling();  // 切换到其他页面时停止首页聊天刷新
    }

    // Check permissions
    const btnAddMember = document.getElementById('btn-add-member');
    const btnAddActivity = document.getElementById('btn-add-activity');
    const btnAddPoem = document.getElementById('btn-add-poem');
    const isManager = currentUser && ['super_admin', 'admin', 'director'].includes(currentUser.role);
    const isLoggedIn = !!currentUser;

    if (btnAddMember) btnAddMember.classList.toggle('hidden', !isManager);
    if (btnAddActivity) btnAddActivity.classList.toggle('hidden', !isManager);
    if (btnAddPoem) btnAddPoem.classList.toggle('hidden', !isLoggedIn);
}

// ============================================================================
// 模态框交互增强
// ============================================================================

// 当前打开的模态框ID（用于ESC关闭）
let _currentOpenModal = null;

/**
 * 切换模态框显示状态
 * @param {string} id - 模态框元素ID
 * 支持：ESC键关闭、打开时禁止背景滚动
 */
function toggleModal(id) {
    const el = document.getElementById(id);
    const isOpening = el.classList.contains('hidden');
    
    if (isOpening) {
        // 打开模态框
        el.classList.remove('hidden');
        _currentOpenModal = id;
        document.body.style.overflow = 'hidden'; // 禁止背景滚动
    } else {
        // 关闭模态框
        el.classList.add('hidden');
        _currentOpenModal = null;
        document.body.style.overflow = ''; // 恢复滚动
    }
}

/**
 * 关闭指定模态框
 * @param {string} id - 模态框元素ID
 */
function closeModal(id) {
    const el = document.getElementById(id);
    if (el) {
        el.classList.add('hidden');
        if (_currentOpenModal === id) {
            _currentOpenModal = null;
            document.body.style.overflow = '';
        }
    }
}

// ESC键关闭模态框
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape' && _currentOpenModal) {
        closeModal(_currentOpenModal);
    }
});

// 点击模态框背景关闭（需要模态框结构支持）
document.addEventListener('click', function(e) {
    if (_currentOpenModal && e.target.classList.contains('modal')) {
        closeModal(_currentOpenModal);
    }
});

// ============================================================================
// 藏诗阁模块 - 诗歌管理
// ============================================================================
let _cachedPoems = [];
let _poemPage = 1;         // 分页：当前页码
let _poemHasMore = true;   // 分页：是否还有下一页
let _showingAllPoems = false;
let _poemSearchTerm = '';
let editingPoemId = null;
let editingPoemIsLocal = false;

/**
 * 获取诗歌列表（支持分页和本地草稿）
 * @param {boolean} isLoadMore - 是否为加载更多（true时保留现有数据）
 * 首次加载会同时获取IndexedDB中的本地草稿
 */
async function fetchPoems(isLoadMore = false) {
    // 确保成员缓存已加载（用于显示作者名称）
    await ensureMembersCached();
    
    try {
        if (!isLoadMore) {
            _poemPage = 1;
            _poemHasMore = true;
            _cachedPoems = [];
            showLoading('poem-list');
        }
        
        if (isLoadMore && !_poemHasMore) return;

        // 1. Fetch Server Poems
        const limit = 10;
        let url = `${API_BASE}/poems?page=${_poemPage}&limit=${limit}`;
        // If we have a specific poem search term active
        if (_poemSearchTerm) {
            url += `&q=${encodeURIComponent(_poemSearchTerm)}`;
        }

        const res = await fetch(url);
        let serverPoems = [];
        if (res.ok) serverPoems = await res.json();
        
        // Determine if more exists
        if (serverPoems.length < limit) _poemHasMore = false;
        else _poemPage++; 

        // 2. Fetch Local Drafts (Show only on first page, not when loading more or searching)
        let localDrafts = [];
        if (!isLoadMore && !_poemSearchTerm) { 
            try {
                localDrafts = await LocalDrafts.getAll();
            } catch(e) { console.warn('IndexedDB not available:', e); }
        }

        // 3. Merge
        if (isLoadMore) {
            _cachedPoems = [..._cachedPoems, ...serverPoems];
        } else {
            _cachedPoems = [...localDrafts, ...serverPoems];
        }
        
        renderPoems();

    } catch(e) { console.error(e); }
}

function loadMorePoems() {
    fetchPoems(true);
}

function renderPoems() {
    const container = document.getElementById('poem-list');
    const isPoemAdmin = currentUser && ['super_admin', 'admin'].includes(currentUser.role);
    
    // Default Server Sort is assumed correct (Newest First).
    // But we might want to re-sort if we mixed in drafts?
    // Drafts usually have new dates. 
    // Let's rely on list order for performance, or simple sort.
    let displayList = _cachedPoems;
    
    // Update "Load More" button visibility
    // If we have "loadMore" button in DOM
    let loadMoreBtn = document.getElementById('poem-load-more');
    if (!loadMoreBtn) {
        // Create if missing (it might be static html, but let's check)
        loadMoreBtn = document.createElement('button');
        loadMoreBtn.id = 'poem-load-more';
        loadMoreBtn.className = 'load-more-btn hidden';
        loadMoreBtn.innerText = '加载更多';
        loadMoreBtn.onclick = loadMorePoems;
        container.parentElement.appendChild(loadMoreBtn);
    }
    
    if (_poemHasMore) {
        loadMoreBtn.classList.remove('hidden');
        loadMoreBtn.innerText = '加载更多...';
    } else {
        loadMoreBtn.classList.add('hidden');
    }

    // 空数据时显示友好提示
    if (displayList.length === 0) {
        if (currentUser) {
            showEmptyState('poem-list', '📜', '诗阁暂无收藏，快来创作第一首诗吧！', '开始创作', 'openPoemModal()');
        } else {
            showEmptyState('poem-list', '📜', '诗阁暂无收藏');
        }
        return;
    }

    // Render
    container.innerHTML = displayList.map(p => {
        const isAuthor = currentUser && (p.author_id === currentUser.id || p.author === currentUser.name || p.author === currentUser.alias);
        const canManage = isPoemAdmin || p.isLocal || isAuthor;
        
        // Generate ID string for function calls
        const idParam = typeof p.id === 'string' ? `'${p.id}'` : p.id;
        const isLocalParam = p.isLocal ? 'true' : 'false';
        
        const displayDate = p.date ? p.date.replace('T', ' ') : '';

        return `
        <div class="card poem-card" style="${p.isLocal ? 'border-left: 4px solid #FFA000;' : ''}">
            <div style="display:flex; justify-content:space-between; align-items:start;">
                <h3>${escapeHtml(p.title)}</h3>
                ${p.isLocal ? '<span style="background:#FFA000; color:white; padding:2px 6px; border-radius:4px; font-size:0.7em;">草稿 (存储在本地)</span>' : ''}
            </div>
            <div class="poem-body markdown-content">${renderMarkdown(p.content)}</div>
            <div class="poem-meta" style="align-items:center;">
                <div style="display:flex; align-items:center; flex-wrap:wrap; gap:10px;">
                    <span style="${getPoemTypeStyle(p.type)} padding:2px 8px; border-radius:4px; font-size:0.85em;">${p.type}</span>
                    <span style="color:#555;">${getSmartDisplayName(p.author_id, p.author)}</span>
                    <span style="color:#999; font-size:0.9em;">${displayDate}</span>
                </div>
                ${ canManage ? `
                    <div style="margin-left:auto;">
                        <button onclick="openPoemModal(_cachedPoems.find(x => x.id == '${p.id}' || x.id == ${p.id}))" style="background:#4CAF50; padding:6px 14px; font-size:0.9em; margin-right:8px;">${p.isLocal ? '编辑' : '修订'}</button>
                        <button onclick="deletePoemWrapper(${idParam}, ${isLocalParam}, event)" style="background:#e74c3c; padding:6px 14px; font-size:0.9em;">删除</button>
                    </div>
                ` : ''}
            </div>
        </div>
        `;
    }).join('');
}
function toLocalISOString(dateStrOrObj) {
    const d = dateStrOrObj ? new Date(dateStrOrObj) : new Date();
    if (isNaN(d.getTime())) return ''; // Invalid date
    const pad = (n) => n < 10 ? '0' + n : n;
    return d.getFullYear() +
        '-' + pad(d.getMonth() + 1) +
        '-' + pad(d.getDate()) +
        'T' + pad(d.getHours()) +
        ':' + pad(d.getMinutes());
}

function openPoemModal(poem = null) {
    const actionContainer = document.getElementById('poem-modal-actions');
    actionContainer.innerHTML = ''; // Clear previous buttons

    if (poem) {
        editingPoemId = poem.id;
        editingPoemIsLocal = !!poem.isLocal;
        document.querySelector('#modal-poem h3').innerText = editingPoemIsLocal ? '编辑草稿' : '修订作品';
        document.getElementById('p-title').value = poem.title;
        document.getElementById('p-type').value = poem.type;
        document.getElementById('p-date').value = toLocalISOString(poem.date);
        document.getElementById('p-content').value = poem.content;

        if (editingPoemIsLocal) {
            // Edit Draft: Save Draft, Publish
            actionContainer.innerHTML = `
                <button onclick="saveDraft()" style="background:#FFA000; color:white;">暂存草稿</button>
                <button onclick="publishPoem()">发布到藏诗阁</button>
            `;
        } else {
            // Edit Published: Update, Withdraw
            actionContainer.innerHTML = `
                <button onclick="submitPoemUpdate()" style="background:#4CAF50; color:white;">更新作品</button>
                <button onclick="withdrawPoem()" style="background:#607D8B; color:white; margin-left: 10px;">从藏诗阁撤回</button>
            `;
        }
    } else {
        editingPoemId = null;
        editingPoemIsLocal = false;
        document.querySelector('#modal-poem h3').innerText = '撰写新作品';
        document.getElementById('p-title').value = '';
        document.getElementById('p-type').value = '古体诗';
        document.getElementById('p-date').value = toLocalISOString(new Date());
        document.getElementById('p-content').value = '';
        
        // New Poem: Save Draft, Publish
        actionContainer.innerHTML = `
            <button onclick="saveDraft()" style="background:#FFA000; color:white;">暂存草稿</button>
            <button onclick="publishPoem()">发布到藏诗阁</button>
        `;
    }
    toggleModal('modal-poem');
}

function openPoemDetailView(poem) {
    if (!poem) return;

    // 标题
    document.getElementById('view-poem-title').innerText = poem.title || '';

    // 类型徽章
    const typeEl = document.getElementById('view-poem-type');
    typeEl.innerText = poem.type || '';
    typeEl.setAttribute('style', getPoemTypeStyle(poem.type) + 'padding:2px 8px; border-radius:4px; font-size:0.85em; flex-shrink:0;');

    // 元信息卡片 + 正文
    const displayDate = poem.date ? poem.date.replace('T', ' ') : '';
    const draftBadge = poem.isLocal
        ? '<span style="background:#FFA000; color:white; padding:2px 6px; border-radius:4px; font-size:0.8em; margin-left:8px;">草稿 (本地)</span>'
        : '';

    const container = document.getElementById('view-poem-container');
    container.innerHTML = `
        <div class="poem-detail-meta">
            <div style="margin-bottom:8px; display:flex;">
                <span style="color:#666; width:80px; flex-shrink:0;">作者</span>
                <span>${escapeHtml(getSmartDisplayName(poem.author_id, poem.author) || '佚名')}${draftBadge}</span>
            </div>
            <div style="display:flex;">
                <span style="color:#666; width:80px; flex-shrink:0;">发布时间</span>
                <span>${escapeHtml(displayDate) || '未知'}</span>
            </div>
        </div>
        <div class="poem-body markdown-content">${renderMarkdown(poem.content || '')}</div>
    `;

    // 权限判定
    const isAuthor = currentUser && (poem.author_id === currentUser.id || poem.author === currentUser.name || poem.author === currentUser.alias);
    const isPoemAdmin = currentUser && ['super_admin', 'admin'].includes(currentUser.role);
    const canManage = isPoemAdmin || poem.isLocal || isAuthor;

    const actionsEl = document.getElementById('view-poem-actions');
    if (canManage) {
        const idParam = typeof poem.id === 'string' ? `'${poem.id}'` : poem.id;
        const btnLabel = poem.isLocal ? '编辑草稿' : '修订';
        actionsEl.innerHTML = `<button onclick="editPoemFromView(${idParam})" style="background:#4CAF50; padding:6px 14px; font-size:0.9em;">${btnLabel}</button>`;
    } else {
        actionsEl.innerHTML = '';
    }

    toggleModal('modal-poem-view');
}

function editPoemFromView(poemId) {
    toggleModal('modal-poem-view');
    let poem = _cachedPoems.find(p => p.id == poemId);
    if (!poem && _searchCache.poems) {
        poem = _searchCache.poems.find(p => p.id == poemId);
    }
    if (poem) openPoemModal(poem);
}

async function saveDraft() {
    const title = document.getElementById('p-title').value;
    const type = document.getElementById('p-type').value;
    const content = document.getElementById('p-content').value;
    const date = document.getElementById('p-date').value;
    
    if(!title || !content) { alert('请填写标题和正文'); return; }

    const draft = {
        id: editingPoemIsLocal ? editingPoemId : `draft_${Date.now()}`,
        title, type, content,
        author: currentUser.alias || currentUser.name,
        date: date || toLocalISOString(new Date()),
        isLocal: true
    };
    
    try {
        await LocalDrafts.save(draft);
        alert('草稿已保存');
        toggleModal('modal-poem');
        fetchPoems();
    } catch(e) {
        alert('保存失败: ' + e);
    }
}

async function publishPoem() {
    const title = document.getElementById('p-title').value;
    const type = document.getElementById('p-type').value;
    const content = document.getElementById('p-content').value;
    const date = document.getElementById('p-date').value;
    
    if(!title || !content) { alert('请填写标题和正文'); return; }

    // 获取发布按钮并禁用，防止重复提交
    const btns = document.querySelectorAll('#poem-modal-actions button');
    const btn = Array.from(btns).find(b => b.textContent.includes('发布'));
    const oldText = btn ? btn.innerText : '';
    if (btn) {
        btn.disabled = true;
        btn.innerText = '发布中...';
    }

    const poemData = {
        title, type, content,
        author: currentUser.alias || currentUser.name,
        author_id: currentUser.id,  // 保存作者ID用于动态显示
        date: date || toLocalISOString(new Date())
    };

    try {
        const res = await fetch(`${API_BASE}/poems`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(withToken(poemData))
        });
        
        if(res.ok) {
            // If it was a draft, remove it from local db
            if (editingPoemIsLocal && editingPoemId) {
                await LocalDrafts.delete(editingPoemId);
            }
            alert('发布成功！');
            toggleModal('modal-poem');
            fetchPoems();
        } else {
            alert('发布失败');
        }
    } catch(e) { console.error(e); alert('网络错误'); }
    finally {
        if (btn) {
            btn.innerText = oldText;
            btn.disabled = false;
        }
    }
}

async function submitPoemUpdate() {
   // Existing logic for updating server poem
   const title = document.getElementById('p-title').value;
   const content = document.getElementById('p-content').value;
   const type = document.getElementById('p-type').value;
   const date = document.getElementById('p-date').value;
   
   // 获取更新按钮并禁用，防止重复提交
   const btns = document.querySelectorAll('#poem-modal-actions button');
   const btn = Array.from(btns).find(b => b.textContent.includes('更新'));
   const oldText = btn ? btn.innerText : '';
   if (btn) {
       btn.disabled = true;
       btn.innerText = '更新中...';
   }
   
   try {
       const res = await fetch(`${API_BASE}/poems/update`, {
           method: 'POST',
           headers: {'Content-Type': 'application/json'},
           body: JSON.stringify(withToken({
               id: editingPoemId,
               title, content, type, date
           }))
       });
       if(res.ok) {
           alert('更新成功');
           toggleModal('modal-poem');
           fetchPoems();
       } else { alert('更新失败'); }
   } catch(e) { console.error(e); }
   finally {
       if (btn) {
           btn.innerText = oldText;
           btn.disabled = false;
       }
   }
}

async function withdrawPoem() {
    if(!confirm('撤回后，该作品将仅保存在您的本地草稿箱中。继续？')) return;
    
    // 获取撤回按钮并禁用，防止重复提交
    const btns = document.querySelectorAll('#poem-modal-actions button');
    const btn = Array.from(btns).find(b => b.textContent.includes('撤回'));
    const oldText = btn ? btn.innerText : '';
    if (btn) {
        btn.disabled = true;
        btn.innerText = '撤回中...';
    }
    
    // 1. Get current content
    const title = document.getElementById('p-title').value;
    const type = document.getElementById('p-type').value;
    const content = document.getElementById('p-content').value;
    const date = document.getElementById('p-date').value;
    
    // 2. Save to Local Draft
    const draft = {
        id: `draft_${Date.now()}`,
        title, type, content,
        author: currentUser.alias || currentUser.name,
        date: date || toLocalISOString(new Date()),
        isLocal: true
    };
    
    try {
        await LocalDrafts.save(draft);
        
        // 3. Delete from Server
        const res = await fetch(`${API_BASE}/poems/delete`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(withToken({id: editingPoemId}))
        });
        
        if(res.ok) {
            alert('已撤回至本地草稿');
            toggleModal('modal-poem');
            fetchPoems();
        } else {
            alert('撤回失败(服务器删除失败)');
        }
    } catch(e) { alert('操作失败: ' + e); }
    finally {
        if (btn) {
            btn.innerText = oldText;
            btn.disabled = false;
        }
    }
}

async function deletePoemWrapper(id, isLocal, event) {
    if(!confirm('确定永久删除这篇作品吗？(无法恢复)')) return;
    
    // 获取按钮并禁用，防止重复提交
    const btn = event?.target;
    const oldText = btn ? btn.innerText : '';
    const oldStyle = btn ? btn.style.cssText : '';
    if (btn) {
        btn.disabled = true;
        btn.innerText = '删除中...';
        btn.style.background = '#999';
        btn.style.color = '#fff';
        btn.style.borderColor = '#999';
    }
    
    try {
        if (isLocal) {
            await LocalDrafts.delete(id);
            fetchPoems();
        } else {
            const res = await fetch(`${API_BASE}/poems/delete`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(withToken({id: id}))
            });
            if(res.ok) fetchPoems();
            else alert('删除失败');
        }
    } catch(e) { console.error(e); }
    finally {
        if (btn) {
            btn.style.cssText = oldStyle;
            btn.innerText = oldText;
            btn.disabled = false;
        }
    }
}

// Data Fetching


let _cachedMembers = [];

/**
 * 确保成员缓存已加载（用于动态显示用户名称）
 * 如果缓存为空，则从服务器加载
 */
async function ensureMembersCached() {
    if (_cachedMembers.length === 0) {
        try {
            const res = currentUser
                ? await fetchWithAuth(`${API_BASE}/members`)
                : await fetch(`${API_BASE}/members?public=1`);
            if (res.ok) _cachedMembers = await res.json();
        } catch (e) {
            console.warn('加载成员缓存失败:', e);
        }
    }
}

/**
 * 根据member_id获取显示名称（优先雅号）
 * @param {number} memberId - 成员ID
 * @returns {string} 显示名称
 */
function getDisplayNameById(memberId) {
    if (!memberId) return '';
    const member = _cachedMembers.find(m => m.id === memberId);
    return member ? (member.alias || member.name) : '';
}

/**
 * 智能获取显示名称：优先通过ID查找，回退到名称字符串
 * @param {number|null} memberId - 成员ID（可选）
 * @param {string|null} fallbackName - 回退名称（当ID查不到时使用）
 * @returns {string} 显示名称
 */
function getSmartDisplayName(memberId, fallbackName) {
    let result = '';
    if (memberId) {
        const name = getDisplayNameById(memberId);
        if (name) result = name;
    }
    // 回退：尝试通过名称查找成员（可能是老数据存储的是alias）
    if (!result && fallbackName) {
        const member = _cachedMembers.find(m => m.name === fallbackName || m.alias === fallbackName);
        if (member) result = member.alias || member.name;
    }
    if (!result) result = fallbackName || '';
    return escapeHtml(result);
}

function editMemberClick(id) {
    const member = _memberDisplayList.find(m => m.id === id) || _cachedMembers.find(m => m.id === id);
    if (member) openMemberModal(member);
}

function formatRole(role) {
    const roleMap = {
        'super_admin': '超级管理员',
        'admin': '管理员',
        'director': '理事',
        'finance': '财务',
        'member': '社员'
    };
    return roleMap[role] || role || '社员';
}

/**
 * 检查操作者是否可以管理目标成员
 * 规则：
 * - 超级管理员只能由自己编辑
 * - 不能管理权限比自己高或相同的用户（超管除外）
 */
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

/**
 * 获取当前用户可分配的角色列表
 * 规则：只能分配比自己权限低的角色，理事只能添加社员
 */
function getAssignableRoles(operatorRole) {
    const operatorLevel = ROLE_LEVEL[operatorRole] ?? 4;
    const allRoles = [
        { value: 'admin', label: '管理员', level: 1 },
        { value: 'director', label: '理事', level: 2 },
        { value: 'finance', label: '财务', level: 3 },
        { value: 'member', label: '社员', level: 4 }
    ];
    
    // 超级管理员可以分配所有角色（除了超管）
    if (operatorRole === 'super_admin') return allRoles;
    
    // 理事只能添加社员
    if (operatorRole === 'director') {
        return allRoles.filter(r => r.value === 'member');
    }
    
    // 其他角色只能分配比自己权限低的角色
    return allRoles.filter(r => r.level > operatorLevel);
}

// ============================================================================
// 社员管理模块
// ============================================================================
let _memberDisplayList = [];   // 分页展示列表（与_cachedMembers全局缓存分离）
let _memberPage = 1;           // 分页：当前页码
let _memberHasMore = true;     // 分页：是否还有下一页

/**
 * 获取社员列表（支持分页）
 * _cachedMembers 由 ensureMembersCached() 管理，用于全局名称查找
 * _memberDisplayList 用于分页展示
 * @param {boolean} isLoadMore - 是否为加载更多
 */
async function fetchMembers(isLoadMore = false) {
    if (!isLoadMore) {
        _memberPage = 1;
        _memberHasMore = true;
        _memberDisplayList = [];
        // 清空全局缓存，以便下次 ensureMembersCached() 重新加载
        _cachedMembers = [];
        showLoading('member-list');
    }
    
    if (isLoadMore && !_memberHasMore) return;
    
    try {
        const isLoggedIn = !!currentUser;
        const limit = 12;
        let url = `${API_BASE}/members?page=${_memberPage}&limit=${limit}`;
        if (!isLoggedIn) url += '&public=1';
        
        const res = isLoggedIn ? await fetchWithAuth(url) : await fetch(url);
        if (!res.ok) throw new Error('Failed to fetch members');
        const items = await res.json();
        
        if (items.length < limit) _memberHasMore = false;
        else _memberPage++;
        
        if (isLoadMore) {
            _memberDisplayList = [..._memberDisplayList, ...items];
        } else {
            _memberDisplayList = items;
        }
        
        renderMembers();
    } catch (e) {
        console.error(e);
        if (!isLoadMore) showEmptyState('member-list', '😕', '加载失败，请刷新重试');
    }
}

function loadMoreMembers() {
    fetchMembers(true);
}

function renderMembers() {
    const container = document.getElementById('member-list');
    const isLoggedIn = !!currentUser;
    const canEdit = isLoggedIn && ['super_admin', 'admin', 'director'].includes(currentUser?.role);
    const canDelete = isLoggedIn && ['super_admin', 'admin'].includes(currentUser?.role);
    
    // 管理"加载更多"按钮
    let loadMoreBtn = document.getElementById('member-load-more');
    if (loadMoreBtn) {
        if (_memberHasMore) {
            loadMoreBtn.classList.remove('hidden');
        } else {
            loadMoreBtn.classList.add('hidden');
        }
    }
    
    if (_memberDisplayList.length === 0) {
        if (isLoggedIn) {
            showEmptyState('member-list', '👥', '暂无社员，快来录入第一位社员吧！', '录入社员', 'openMemberModal()');
        } else {
            showEmptyState('member-list', '👥', '暂无社员');
        }
        return;
    }

    container.innerHTML = _memberDisplayList.map(m => {
        const displayName = m.alias || (isLoggedIn ? m.name : '社员');
        const canEditThis = canEdit && canManageMember(currentUser?.id, currentUser?.role, m.id, m.role);
        const canDeleteThis = canDelete && m.role !== 'super_admin' && m.id !== currentUser?.id && canManageMember(currentUser?.id, currentUser?.role, m.id, m.role);
        
        if (!isLoggedIn) {
            return `
            <div class="member-card">
                <div class="member-avatar">${escapeHtml(displayName.charAt(0))}</div>
                <h4>${escapeHtml(displayName)}</h4>
                <div style="margin: 10px 0;">
                    <span class="points-badge">${m.points || 0} ${getPointsName()}</span>
                </div>
            </div>
            `;
        }
        
        return `
        <div class="member-card">
            <div class="member-avatar">${escapeHtml(displayName.charAt(0))}</div>
            <h4>${escapeHtml(displayName)}</h4>
            <div class="member-role">
                ${m.alias ? escapeHtml(m.name) : ''}<br>
                <small>${formatRole(m.role)}</small>
            </div>
            <div style="margin: 10px 0;">
                <span class="points-badge">${m.points || 0} ${getPointsName()}</span>
            </div>
            ${(canEdit || canDelete) ? `
            <div class="member-actions">
                ${canEdit ? (canEditThis 
                    ? `<button class="btn-edit" onclick="editMemberClick(${m.id})">编辑</button>` 
                    : `<button class="btn-edit" style="color:#aaa; border-color:#ccc; cursor:not-allowed;" disabled title="无权编辑此用户">编辑</button>`) : ''}
                ${canDeleteThis ? `<button class="btn-remove" onclick="deleteMember(${m.id}, event)">移除</button>` : ''}
            </div>
            ` : ''}
        </div>
    `}).join('');
}

let editingMemberId = null;
let editingMemberOriginalRole = null;  // 保存编辑时的原始角色

async function openMemberModal(member = null) {
    // 动态设置可选角色（根据当前用户权限）
    const roleSelect = document.getElementById('m-role');
    const assignableRoles = getAssignableRoles(currentUser?.role);
    
    if (member) {
        editingMemberId = member.id;
        editingMemberOriginalRole = member.role;  // 保存原始角色
        document.querySelector('#modal-member h3').innerText = '编辑社员资料';
        document.getElementById('m-name').value = member.name;
        document.getElementById('m-alias').value = member.alias || '';
        document.getElementById('m-phone').value = member.phone || '';
        document.getElementById('m-password').value = ''; // 编辑时不显示原密码 
        document.getElementById('m-points').value = member.points || 0;
        document.getElementById('m-points').placeholder = `${getPointsName()} (留空则保持不变)`;
        document.getElementById('m-birthday').value = member.birthday || '';
        // 编辑时密码非必填
        document.getElementById('m-password').placeholder = "留空则不修改密码";
        
        // 超级管理员角色不可变更（包括自己编辑自己）
        if (member.role === 'super_admin') {
            roleSelect.innerHTML = `<option value="super_admin">超级管理员</option>`;
            roleSelect.value = 'super_admin';
            roleSelect.disabled = true;
        } else {
            // 编辑时：检查是否有权修改此成员的角色
            const canChangeRole = canManageMember(currentUser?.id, currentUser?.role, member.id, member.role);
            if (canChangeRole) {
                // 可以修改角色，但只能选择可分配的角色
                roleSelect.innerHTML = assignableRoles.map(r => 
                    `<option value="${r.value}">${r.label}</option>`
                ).join('');
                // 如果当前角色在可选列表中，保持选中
                if (assignableRoles.some(r => r.value === member.role)) {
                    roleSelect.value = member.role;
                } else {
                    // 当前角色不在可选列表中（比如正在编辑一个权限更低的用户），添加当前角色作为选项
                    roleSelect.innerHTML = `<option value="${member.role}">${formatRole(member.role)}</option>` + roleSelect.innerHTML;
                    roleSelect.value = member.role;
                }
                roleSelect.disabled = false;
            } else {
                // 不能修改角色，显示当前角色但禁用
                roleSelect.innerHTML = `<option value="${member.role}">${formatRole(member.role)}</option>`;
                roleSelect.value = member.role;
                roleSelect.disabled = true;
            }
        }
    } else {
        editingMemberId = null;
        editingMemberOriginalRole = null;  // 新建时重置原始角色
        document.querySelector('#modal-member h3').innerText = '录入新社员';
        document.getElementById('m-name').value = '';
        document.getElementById('m-alias').value = '';
        document.getElementById('m-phone').value = '';
        document.getElementById('m-password').value = '';
        document.getElementById('m-points').value = '';
        document.getElementById('m-birthday').value = '';
        // 新建时密码必填
        document.getElementById('m-password').placeholder = "初始密码 *";
        document.getElementById('m-points').placeholder = `初始${getPointsName()} (默认0)`;
        
        // 新建时：只能选择可分配的角色
        roleSelect.innerHTML = assignableRoles.map(r => 
            `<option value="${r.value}">${r.label}</option>`
        ).join('');
        roleSelect.value = 'member'; // 默认选择社员
        roleSelect.disabled = false;
    }

    // Render Custom Fields
    const customContainer = document.getElementById('m-custom-fields-container');
    if (customContainer) {
        customContainer.innerHTML = _customFields.map(f => {
            const val = (member && member.custom && member.custom[f.id]) ? member.custom[f.id] : '';
            const requiredMark = f.required ? ' *' : '';
            if (f.type === 'textarea') {
                return `<textarea class="custom-field-input" data-id="${f.id}" placeholder="${f.label}${requiredMark}" rows="2" style="width:100%; box-sizing:border-box; margin-bottom:8px;">${val}</textarea>`;
            } else if (f.type === 'date') {
                return `<div style="margin-bottom:8px;"><label class="date-label">${f.label}${requiredMark}</label><input type="date" class="custom-field-input" data-id="${f.id}" value="${val}" style="width:100%; box-sizing:border-box;"></div>`;
            } else {
                return `<input type="${f.type || 'text'}" class="custom-field-input" data-id="${f.id}" placeholder="${f.label}${requiredMark}" value="${val}" style="width:100%; box-sizing:border-box; margin-bottom:8px;">`;
            }
        }).join('');
    }

    toggleModal('modal-member');
}

async function submitMember() {
    const submitBtn = document.querySelector('#modal-member button');
    const originalText = submitBtn.innerText;
    submitBtn.innerText = '保存中...';
    submitBtn.disabled = true;

    try {
        // 清除之前的错误提示
        clearFormErrors('#modal-member');
        
        const data = {
            name: document.getElementById('m-name').value.trim(),
            alias: document.getElementById('m-alias').value.trim(),
            phone: document.getElementById('m-phone').value.trim(),
            role: document.getElementById('m-role').value,
            points: parseInt(document.getElementById('m-points').value || 0),
            birthday: document.getElementById('m-birthday').value
        };
        
        // 基础字段验证
        let hasError = false;
        
        // 姓名验证
        const nameResult = validateField('name', data.name, VALIDATION_RULES.name);
        if (!nameResult.valid) {
            showFieldError(document.getElementById('m-name'), nameResult.error);
            hasError = true;
        }
        
        // 雅号验证
        const aliasResult = validateField('alias', data.alias, VALIDATION_RULES.alias);
        if (!aliasResult.valid) {
            showFieldError(document.getElementById('m-alias'), aliasResult.error);
            hasError = true;
        }
        
        // 手机号验证
        const phoneResult = validateField('phone', data.phone, VALIDATION_RULES.phone);
        if (!phoneResult.valid) {
            showFieldError(document.getElementById('m-phone'), phoneResult.error);
            hasError = true;
        }
        
        // 积分验证
        const pointsResult = validateField('points', data.points, VALIDATION_RULES.points);
        if (!pointsResult.valid) {
            showFieldError(document.getElementById('m-points'), pointsResult.error);
            hasError = true;
        }
        
        // 生日验证
        if (data.birthday) {
            const birthdayResult = validateField('birthday', data.birthday, VALIDATION_RULES.birthday);
            if (!birthdayResult.valid) {
                showFieldError(document.getElementById('m-birthday'), birthdayResult.error);
                hasError = true;
            }
        }
        
        if (hasError) {
            return;
        }
        
        // 前端角色权限验证：只在新增或角色变更时验证
        // 编辑时如果角色没变，不需要验证（允许超管编辑自己的其他资料）
        const isRoleChanged = editingMemberId ? (data.role !== editingMemberOriginalRole) : true;
        if (isRoleChanged) {
            const roleCheck = canAssignRole(data.role);
            if (!roleCheck.allowed) {
                alert(roleCheck.error);
                return;
            }
        }
        
        // 收集自定义字段
        const customData = {};
        document.querySelectorAll('.custom-field-input').forEach(input => {
            customData[input.dataset.id] = input.value;
        });
        data.custom = customData;
        
        // 验证自定义字段
        const customValidation = validateCustomFields(_customFields, customData);
        if (!customValidation.valid) {
            showCustomFieldErrors(customValidation.errors);
            return;
        }

        const pwd = document.getElementById('m-password').value;
        if (pwd) data.password = pwd;

        if(!editingMemberId) {
            // 新建成员：验证密码
            if (!pwd) {
                showFieldError(document.getElementById('m-password'), '密码为必填项');
                return;
            }
            const pwdResult = validateField('password', pwd, VALIDATION_RULES.password);
            if (!pwdResult.valid) {
                showFieldError(document.getElementById('m-password'), pwdResult.error);
                return;
            }
            
            data.joined_at = new Date().toISOString().split('T')[0];
            
            const response = await fetch(`${API_BASE}/members`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(withToken(data))
            });
            if (!response.ok) {
                const err = await response.json().catch(() => ({}));
                throw new Error(err.error || '添加失败');
            }
        } else {
            // 编辑成员：如果填写了密码，验证密码强度
            if (pwd) {
                const pwdResult = validateField('password', pwd, VALIDATION_RULES.password);
                if (!pwdResult.valid) {
                    showFieldError(document.getElementById('m-password'), pwdResult.error);
                    return;
                }
            }
            
            data.id = editingMemberId;
            const response = await fetch(`${API_BASE}/members/update`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(withToken(data))
            });
            if (!response.ok) {
                const err = await response.json().catch(() => ({}));
                throw new Error(err.error || '更新失败');
            }
        }

        toggleModal('modal-member');
        fetchMembers();
    } catch(err) {
        alert('操作失败: ' + err.message);
    } finally {
        submitBtn.innerText = originalText;
        submitBtn.disabled = false;
    }
}

/**
 * 删除社员
 * @param {number} id - 社员ID
 */
async function deleteMember(id, event) {
    // 前端检测：不能删除自己
    if (id === currentUser?.id) {
        alert('不能删除自己的账号');
        return;
    }
    
    // 前端检测：超级管理员不能被删除
    const member = _memberDisplayList.find(m => m.id === id) || _cachedMembers.find(m => m.id === id);
    if (member && member.role === 'super_admin') {
        alert('超级管理员不能被删除');
        return;
    }
    
    // 前端检测：只能删除比自己权限低的用户
    if (member && !canManageMember(currentUser?.id, currentUser?.role, member.id, member.role)) {
        alert('无权删除此用户');
        return;
    }
    
    if(!confirm('确定要移除该社员吗？此操作无法撤销。')) return;
    
    // 获取按钮并禁用，防止重复提交
    const btn = event?.target;
    const oldText = btn ? btn.innerText : '';
    const oldStyle = btn ? btn.style.cssText : '';
    if (btn) {
        btn.disabled = true;
        btn.innerText = '删除中...';
        btn.style.background = '#999';
        btn.style.color = '#fff';
        btn.style.borderColor = '#999';
    }
    
    try {
        const res = await fetch(`${API_BASE}/members/delete`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(withToken({id: id}))
        });
        if(res.ok) {
            alert('社员已移除');
            fetchMembers();
        } else {
            const error = await res.json().catch(() => ({}));
            alert('删除失败: ' + (error.error || '权限不足'));
        }
    } catch(e) {
        console.error('删除社员失败:', e);
        alert('网络错误，请重试');
    } finally {
        if (btn) {
            btn.style.cssText = oldStyle;
            btn.innerText = oldText;
            btn.disabled = false;
        }
    }
}

let _cachedFinance = [];
let _financePage = 1;         // 分页：当前页码
let _financeHasMore = true;   // 分页：是否还有下一页
let editingFinanceId = null;

/**
 * 获取财务记录（支持分页）
 * 首次加载时同步获取统计数据
 * @param {boolean} isLoadMore - 是否为加载更多
 */
async function fetchFinance(isLoadMore = false) {
    // 权限控制：只有财务、管理员、超级管理员可以记账
    const addFinanceBtn = document.getElementById('btn-add-finance');
    if(addFinanceBtn && currentUser) {
        const canRecord = ['super_admin', 'admin', 'finance'].includes(currentUser.role);
        addFinanceBtn.classList.toggle('hidden', !canRecord);
    }
    
    if (!isLoadMore) {
        _financePage = 1;
        _financeHasMore = true;
        _cachedFinance = [];
    }
    
    if (isLoadMore && !_financeHasMore) return;
    
    try {
        const limit = 20;
        
        // 并行请求：首次加载时同时获取统计数据和列表数据
        const fetchList = fetchWithAuth(`${API_BASE}/finance?page=${_financePage}&limit=${limit}`);
        
        if (!isLoadMore) {
            // 首次加载：同时获取统计和列表
            const fetchStats = fetchWithAuth(`${API_BASE}/finance/stats`);
            const [listRes, statsRes] = await Promise.all([fetchList, fetchStats]);
            
            if (!listRes.ok) {
                const err = await listRes.json().catch(() => ({}));
                throw new Error(err.error || '获取失败');
            }
            
            const items = await listRes.json();
            if (items.length < limit) _financeHasMore = false;
            else _financePage++;
            _cachedFinance = items;
            
            // 更新统计数据
            if (statsRes.ok) {
                const stats = await statsRes.json();
                document.getElementById('total-income').innerText = (stats.year_income || 0).toLocaleString();
                document.getElementById('total-expense').innerText = (stats.year_expense || 0).toLocaleString();
                document.getElementById('balance').innerText = (stats.balance || 0).toLocaleString();
            }
        } else {
            // 加载更多：只获取列表
            const listRes = await fetchList;
            if (!listRes.ok) {
                const err = await listRes.json().catch(() => ({}));
                throw new Error(err.error || '获取失败');
            }
            const items = await listRes.json();
            if (items.length < limit) _financeHasMore = false;
            else _financePage++;
            _cachedFinance = [..._cachedFinance, ...items];
        }
        
        renderFinance();
    } catch(e) {
        console.error('获取财务记录失败:', e);
        if (!isLoadMore) alert('获取财务记录失败: ' + e.message);
    }
}

function loadMoreFinance() {
    fetchFinance(true);
}

function renderFinance() {
    // 编辑/删除权限：仅超级管理员
    const canEditFinance = currentUser && currentUser.role === 'super_admin';
    
    const tbody = document.getElementById('finance-list');
    tbody.innerHTML = _cachedFinance.map(r => `
    <tr>
        <td>${r.date}</td>
        <td>${escapeHtml(r.summary)}<br><small>${escapeHtml(r.category)}</small></td>
        <td class="money ${r.type === 'income' ? 'plus' : 'minus'}">
            ${r.type === 'income' ? '+' : '-'}${r.amount}
        </td>
        <td>${escapeHtml(r.handler)}</td>
        ${canEditFinance ? `<td><button class="btn-edit-sm" onclick="openFinanceModal(${r.id})">编辑</button><button class="btn-del-sm" onclick="deleteFinance(${r.id}, event)">删除</button></td>` : ''}
    </tr>
`).join('');

    // 动态控制表头操作列
    const financeOpTh = document.getElementById('finance-op-th');
    if (financeOpTh) financeOpTh.classList.toggle('hidden', !canEditFinance);
    
    // 管理"加载更多"按钮
    let loadMoreBtn = document.getElementById('finance-load-more');
    if (loadMoreBtn) {
        if (_financeHasMore) {
            loadMoreBtn.classList.remove('hidden');
        } else {
            loadMoreBtn.classList.add('hidden');
        }
    }
}

// ============================================================================
// 事务与积分模块
// ============================================================================
let _cachedTasks = [];
let _taskPage = 1;         // 分页：当前页码
let _taskHasMore = true;   // 分页：是否还有下一页

/**
 * 获取任务列表（支持分页）
 * @param {boolean} isLoadMore - 是否为加载更多
 */
async function fetchTasks(isLoadMore = false) {
    await ensureMembersCached();
    
    // 动态更新标题
    const titleEl = document.getElementById('tasks-section-title');
    if(titleEl) {
        titleEl.innerText = `事务与${getPointsName()}`;
    }
    
    // 显示/隐藏发布按钮（仅理事以上可见）
    const addTaskBtn = document.getElementById('btn-add-task');
    if(addTaskBtn && currentUser) {
        const canCreate = ['super_admin', 'admin', 'director'].includes(currentUser.role);
        addTaskBtn.classList.toggle('hidden', !canCreate);
    }
    
    if (!isLoadMore) {
        _taskPage = 1;
        _taskHasMore = true;
        _cachedTasks = [];
        showLoading('task-list');
    }
    
    if (isLoadMore && !_taskHasMore) return;
    
    try {
        const limit = 10;
        const res = await fetchWithAuth(`${API_BASE}/tasks?page=${_taskPage}&limit=${limit}`);
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.error || '获取失败');
        }
        const items = await res.json();
        
        if (items.length < limit) _taskHasMore = false;
        else _taskPage++;
        
        if (isLoadMore) {
            _cachedTasks = [..._cachedTasks, ...items];
        } else {
            _cachedTasks = items;
        }
        
        renderTasks();
    } catch(e) { 
        console.error(e);
        if (!isLoadMore) showEmptyState('task-list', '😕', '加载失败，请刷新重试');
    }
}

function loadMoreTasks() {
    fetchTasks(true);
}

function renderTasks() {
    const container = document.getElementById('task-list');
    
    // 管理"加载更多"按钮
    let loadMoreBtn = document.getElementById('task-load-more');
    if (loadMoreBtn) {
        if (_taskHasMore) {
            loadMoreBtn.classList.remove('hidden');
        } else {
            loadMoreBtn.classList.add('hidden');
        }
    }
    
    if (_cachedTasks.length === 0) {
        showEmptyState('task-list', '📋', '暂无待办事务，一切顺利！');
        return;
    }
    
    const pointsName = getPointsName();
    const userName = currentUser ? currentUser.name : '';
    const isManager = currentUser && ['super_admin', 'admin', 'director'].includes(currentUser.role);
    
    container.innerHTML = _cachedTasks.map(t => {
        const statusInfo = getTaskStatusInfo(t.status);
        const isCreator = t.creator === userName;
        const isAssignee = t.assignee === userName;
        
        let actionButtons = '';
        
        if(t.status === 'open') {
            actionButtons = `<button onclick="claimTask(${t.id}, event)" class="btn-claim">领取任务</button>`;
        } else if(t.status === 'claimed') {
            if(isAssignee) {
                actionButtons = `
                    <button onclick="submitTaskComplete(${t.id}, event)" class="btn-submit">提交完成</button>
                    <button onclick="unclaimTask(${t.id}, event)" class="btn-unclaim" style="margin-left:8px;">撤销领取</button>
                `;
                if(isManager) {
                    actionButtons += `<button onclick="forceApproveTask(${t.id}, event)" class="btn-approve" style="margin-left:8px;">直接验收</button>`;
                }
            } else if(isManager) {
                actionButtons = `
                    <button onclick="forceApproveTask(${t.id}, event)" class="btn-approve">直接验收</button>
                    <button onclick="unclaimTask(${t.id}, event)" class="btn-unclaim" style="margin-left:8px;">撤销领取</button>
                `;
            }
        } else if(t.status === 'submitted' && (isCreator || isManager)) {
            actionButtons = `
                <button onclick="approveTask(${t.id}, event)" class="btn-approve">通过</button>
                <button onclick="rejectTask(${t.id}, event)" class="btn-reject">退回</button>
            `;
        }
        
        let deleteBtn = '';
        if(isManager || (isCreator && t.status !== 'completed')) {
            deleteBtn = `<button onclick="deleteTask(${t.id}, event)" class="btn-delete" style="margin-left:10px;">删除</button>`;
        }
        
        let editBtn = '';
        if(isManager) {
            editBtn = `<button onclick="openTaskModal(${t.id})" class="btn-edit" style="margin-left:10px; background:#2196F3;">编辑</button>`;
        }
        
        return `
        <div class="card task-item">
            <h4>${escapeHtml(t.title)} <span class="task-status ${statusInfo.className}">${statusInfo.label}</span></h4>
            <div class="markdown-content">${renderMarkdown(t.description || '')}</div>
            <div class="task-meta">
                <div style="display:flex; align-items:center; flex-wrap:wrap; gap:8px;">
                    <small>
                        奖励: <span class="task-reward">${t.reward}</span> ${pointsName}
                        ${t.creator ? `&nbsp;|&nbsp;发布者: ${getSmartDisplayName(t.creator_id, t.creator)}` : ''}
                        ${t.assignee ? `&nbsp;|&nbsp;领取者: ${getSmartDisplayName(t.assignee_id, t.assignee)}` : ''}
                    </small>
                </div>
                <div style="margin-left:auto; display:flex; align-items:center;">
                    ${actionButtons}
                    ${editBtn}
                    ${deleteBtn}
                </div>
            </div>
        </div>
        `;
    }).join('');
}

function getTaskStatusInfo(status) {
    const statusMap = {
        'open': { label: '待领取', className: 'status-open' },
        'claimed': { label: '进行中', className: 'status-claimed' },
        'submitted': { label: '待验收', className: 'status-submitted' },
        'completed': { label: '已完成', className: 'status-completed' }
    };
    return statusMap[status] || { label: status, className: '' };
}

// 编辑任务时存储任务ID
let _editingTaskId = null;

async function openTaskModal(taskId = null) {
    _editingTaskId = taskId;
    
    // 加载社员列表到指派下拉框
    const assigneeSelect = document.getElementById('t-assignee');
    if(assigneeSelect) {
        if(_cachedMembers.length === 0) {
            try {
                const res = await fetch(`${API_BASE}/members`);
                if(res.ok) _cachedMembers = await res.json();
            } catch(e) { console.error(e); }
        }
        
        assigneeSelect.innerHTML = '<option value="">不指派，等待领取</option>' +
            _cachedMembers.map(m => `<option value="${m.name}">${m.alias || m.name}</option>`).join('');
    }
    
    if(taskId) {
        // 编辑模式：从缓存中查找任务并填充表单
        document.getElementById('task-modal-title').innerText = '编辑事务';
        const task = _cachedTasks.find(t => t.id === taskId);
        if(task) {
            document.getElementById('t-title').value = task.title || '';
            document.getElementById('t-description').value = task.description || '';
            document.getElementById('t-reward').value = task.reward || '';
            // 编辑模式下隐藏指派选择（已有状态不应修改指派）
            if(assigneeSelect) assigneeSelect.style.display = 'none';
        }
    } else {
        // 新建模式
        document.getElementById('task-modal-title').innerText = '发布事务';
        document.getElementById('t-title').value = '';
        document.getElementById('t-description').value = '';
        document.getElementById('t-reward').value = '';
        if(assigneeSelect) assigneeSelect.style.display = '';
    }
    
    document.getElementById('t-reward').placeholder = `奖励${getPointsName()}`;
    toggleModal('modal-task');
}

async function submitTask() {
    const title = document.getElementById('t-title').value.trim();
    const description = document.getElementById('t-description').value.trim();
    const reward = parseInt(document.getElementById('t-reward').value) || 0;
    
    if(!title) { alert('请填写事务标题'); return; }
    
    // 获取提交按钮并禁用，防止重复提交
    const btn = document.querySelector('#modal-task button');
    const oldText = btn ? btn.innerText : '';
    if (btn) {
        btn.disabled = true;
        btn.innerText = '提交中...';
    }
    
    try {
        if(_editingTaskId) {
            // 更新模式
            const res = await fetch(`${API_BASE}/tasks/update`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(withToken({
                    id: _editingTaskId,
                    title,
                    description,
                    reward
                }))
            });
            
            if(res.ok) {
                toggleModal('modal-task');
                fetchTasks();
                alert('事务更新成功！');
            } else {
                alert('更新失败');
            }
        } else {
            // 新建模式
            const assignee = document.getElementById('t-assignee')?.value || '';
            let assigneeId = null;
            if (assignee) {
                const assigneeMember = _cachedMembers.find(m => m.name === assignee);
                assigneeId = assigneeMember ? assigneeMember.id : null;
            }
            
            const res = await fetch(`${API_BASE}/tasks`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(withToken({
                    title,
                    description,
                    reward,
                    creator: currentUser.alias || currentUser.name,
                    creator_id: currentUser.id,
                    assignee: assignee || null,
                    assignee_id: assigneeId
                }))
            });
            
            if(res.ok) {
                toggleModal('modal-task');
                fetchTasks();
                if(assignee) {
                    alert(`事务已派发给 ${assignee}！`);
                } else {
                    alert('事务发布成功！');
                }
            } else {
                alert('发布失败');
            }
        }
    } catch(e) {
        console.error(e);
        alert('网络错误');
    } finally {
        if (btn) {
            btn.innerText = oldText;
            btn.disabled = false;
        }
    }
}

async function claimTask(taskId, event) {
    if(!confirm('确认领取此任务？')) return;
    
    // 获取按钮并禁用，防止重复提交
    const btn = event?.target;
    const oldText = btn ? btn.innerText : '';
    if (btn) {
        btn.disabled = true;
        btn.innerText = '领取中...';
    }
    
    try {
        const res = await fetch(`${API_BASE}/tasks/claim`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(withToken({ task_id: taskId, member_name: currentUser.name, member_id: currentUser.id }))
        });
        
        if(res.ok) {
            fetchTasks();
            alert('任务领取成功，请尽快完成！');
        } else {
            alert('领取失败，任务可能已被他人领取');
        }
    } catch(e) {
        console.error(e);
        alert('网络错误');
    } finally {
        if (btn) {
            btn.innerText = oldText;
            btn.disabled = false;
        }
    }
}

async function unclaimTask(taskId, event) {
    if(!confirm('确认撤销领取？任务将重新变为待领取状态。')) return;
    
    // 获取按钮并禁用，防止重复提交
    const btn = event?.target;
    const oldText = btn ? btn.innerText : '';
    if (btn) {
        btn.disabled = true;
        btn.innerText = '撤销中...';
    }
    
    try {
        const res = await fetch(`${API_BASE}/tasks/unclaim`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(withToken({ task_id: taskId }))
        });
        
        if(res.ok) {
            fetchTasks();
            alert('已撤销领取');
        } else {
            alert('撤销失败');
        }
    } catch(e) {
        console.error(e);
        alert('网络错误');
    } finally {
        if (btn) {
            btn.innerText = oldText;
            btn.disabled = false;
        }
    }
}

async function submitTaskComplete(taskId, event) {
    if(!confirm('确认提交任务？提交后将等待发布者验收。')) return;
    
    // 获取按钮并禁用，防止重复提交
    const btn = event?.target;
    const oldText = btn ? btn.innerText : '';
    if (btn) {
        btn.disabled = true;
        btn.innerText = '提交中...';
    }
    
    try {
        const res = await fetch(`${API_BASE}/tasks/submit`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(withToken({ task_id: taskId }))
        });
        
        if(res.ok) {
            fetchTasks();
            alert('任务已提交，等待验收！');
        } else {
            alert('提交失败');
        }
    } catch(e) {
        console.error(e);
        alert('网络错误');
    } finally {
        if (btn) {
            btn.innerText = oldText;
            btn.disabled = false;
        }
    }
}

async function approveTask(taskId, event) {
    if(!confirm(`确认验收通过？通过后将发放${getPointsName()}奖励。`)) return;
    
    // 获取按钮并禁用，防止重复提交
    const btn = event?.target;
    const oldText = btn ? btn.innerText : '';
    if (btn) {
        btn.disabled = true;
        btn.innerText = '验收中...';
    }
    
    try {
        const res = await fetch(`${API_BASE}/tasks/approve`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(withToken({ task_id: taskId }))
        });
        
        if(res.ok) {
            const data = await res.json();
            fetchTasks();
            if(data.gained > 0) {
                alert(`验收通过！已发放 ${data.gained} ${getPointsName()}`);
            } else {
                alert('验收通过！');
            }
        } else {
            const status = res.status;
            if(status === 404) {
                alert('任务不存在');
            } else if(status === 400) {
                alert('任务状态不正确，无法验收');
            } else {
                alert('验收失败');
            }
            fetchTasks();
        }
    } catch(e) {
        console.error(e);
        alert('网络错误');
    } finally {
        if (btn) {
            btn.innerText = oldText;
            btn.disabled = false;
        }
    }
}

async function forceApproveTask(taskId, event) {
    if(!confirm(`确认直接验收此任务？\n此操作将跳过用户提交步骤，直接完成任务并发放${getPointsName()}奖励。`)) return;
    
    // 获取按钮并禁用，防止重复提交
    const btn = event?.target;
    const oldText = btn ? btn.innerText : '';
    if (btn) {
        btn.disabled = true;
        btn.innerText = '验收中...';
    }
    
    try {
        const res = await fetch(`${API_BASE}/tasks/approve`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(withToken({ task_id: taskId, force: true }))
        });
        
        if(res.ok) {
            const data = await res.json();
            fetchTasks();
            if(data.gained > 0) {
                alert(`验收完成！已发放 ${data.gained} ${getPointsName()}`);
            } else {
                alert('验收完成！');
            }
        } else {
            alert('验收失败');
            fetchTasks();
        }
    } catch(e) {
        console.error(e);
        alert('网络错误');
    } finally {
        if (btn) {
            btn.innerText = oldText;
            btn.disabled = false;
        }
    }
}

async function rejectTask(taskId, event) {
    if(!confirm('确认退回任务？任务将退回给领取者重做。')) return;
    
    // 获取按钮并禁用，防止重复提交
    const btn = event?.target;
    const oldText = btn ? btn.innerText : '';
    if (btn) {
        btn.disabled = true;
        btn.innerText = '退回中...';
    }
    
    try {
        const res = await fetch(`${API_BASE}/tasks/reject`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(withToken({ task_id: taskId }))
        });
        
        if(res.ok) {
            fetchTasks();
            alert('任务已退回');
        } else {
            alert('操作失败');
        }
    } catch(e) {
        console.error(e);
        alert('网络错误');
    } finally {
        if (btn) {
            btn.innerText = oldText;
            btn.disabled = false;
        }
    }
}

async function deleteTask(taskId, event) {
    if(!confirm('确认删除此任务？此操作不可恢复。')) return;
    
    // 获取按钮并禁用，防止重复提交
    const btn = event?.target;
    const oldText = btn ? btn.innerText : '';
    const oldStyle = btn ? btn.style.cssText : '';
    if (btn) {
        btn.disabled = true;
        btn.innerText = '删除中...';
        btn.style.background = '#999';
        btn.style.color = '#fff';
        btn.style.borderColor = '#999';
    }
    
    try {
        const res = await fetch(`${API_BASE}/tasks/delete`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(withToken({ task_id: taskId }))
        });
        
        if(res.ok) {
            fetchTasks();
            alert('任务已删除');
        } else {
            alert('删除失败');
        }
    } catch(e) {
        console.error(e);
        alert('网络错误');
    } finally {
        if (btn) {
            btn.style.cssText = oldStyle;
            btn.innerText = oldText;
            btn.disabled = false;
        }
    }
}

// ============================================================================
// 活动管理模块
// ============================================================================
let _cachedActivities = [];
let _activityPage = 1;         // 分页：当前页码
let _activityHasMore = true;   // 分页：是否还有下一页
let editingActivityId = null;

/**
 * 获取活动列表（支持分页）
 * @param {boolean} isLoadMore - 是否为加载更多
 */
async function fetchActivities(isLoadMore = false) {
    await ensureMembersCached();
    
    if (!isLoadMore) {
        _activityPage = 1;
        _activityHasMore = true;
        _cachedActivities = [];
        showLoading('activity-list');
    }
    
    if (isLoadMore && !_activityHasMore) return;
    
    try {
        const limit = 10;
        const res = await fetch(`${API_BASE}/activities?page=${_activityPage}&limit=${limit}`);
        const items = await res.json();
        
        if (items.length < limit) _activityHasMore = false;
        else _activityPage++;
        
        if (isLoadMore) {
            _cachedActivities = [..._cachedActivities, ...items];
        } else {
            _cachedActivities = items;
        }
        
        renderActivities();
    } catch(e) { console.error(e); }
}

function loadMoreActivities() {
    fetchActivities(true);
}

function renderActivities() {
    const container = document.getElementById('activity-list');
    
    // 管理"加载更多"按钮
    let loadMoreBtn = document.getElementById('activity-load-more');
    if (loadMoreBtn) {
        if (_activityHasMore) {
            loadMoreBtn.classList.remove('hidden');
        } else {
            loadMoreBtn.classList.add('hidden');
        }
    }
    
    if (_cachedActivities.length === 0) {
        showEmptyState('activity-list', '📅', '暂无活动，快来发起一个吧！', '发起活动', 'openActivityModal()');
        return;
    }

    container.innerHTML = _cachedActivities.map(a => `
        <div class="card" onclick="openActivityDetailView(${a.id})" style="cursor:pointer; margin-bottom:20px; transition:all 0.2s;">
            <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:10px;">
                 <h3 style="margin:0; font-size:1.2rem; line-height:1.4; flex:1; padding-right:12px;">${escapeHtml(a.title)}</h3>
                 <span class="points-badge" style="${getStatusStyle(a.status)}; margin-top:2px; float:none; flex-shrink:0; white-space:nowrap;">${a.status}</span>
            </div>
            <div style="color:#444; margin-bottom:15px; line-height:1.6; max-height:4.8em; overflow:hidden; display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical;">
                ${escapeHtml(a.desc || '')}
            </div>
            <div style="font-size:0.9em; color:#999; border-top:1px solid #eee; padding-top:10px; display:flex; justify-content:space-between; align-items:center;">
                <span style="flex-shrink:0; margin-right:10px;">${formatDate(a.date)}</span>
                <span style="flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; text-align:right;">${escapeHtml(a.location || '线上')}</span>
            </div>
        </div>
    `).join('');
}

function getPoemTypeStyle(type) {
    if(type === '绝句') return 'background:#E3F2FD; color:#1565C0;'; // Blue
    if(type === '律诗') return 'background:#E8F5E9; color:#2E7D32;'; // Green
    if(type === '词') return 'background:#F3E5F5; color:#7B1FA2;'; // Purple
    if(type === '现代诗') return 'background:#FFF3E0; color:#E65100;'; // Orange
    if(type === '文章') return 'background:#ECEFF1; color:#546E7A;'; // Grey
    return 'background:#F5F5F5; color:#616161;';
}

function getStatusStyle(status) {
    if(status === '筹备中') return 'background:#FFF3E0; color:#E65100; float:right;'; // Orange
    if(status === '报名中') return 'background:#E3F2FD; color:#1565C0; float:right;'; // Blue
    if(status === '进行中') return 'background:#E8F5E9; color:#2E7D32; float:right;'; // Green
    if(status === '已结束') return 'background:#F5F5F5; color:#757575; float:right;'; // Grey
    return 'background:#f5f5f5; color:#333; float:right;';
}

function formatDate(dateStr) {
    if(!dateStr) return '待定';
    return dateStr.replace('T', ' ');
}

function openActivityModal(activity = null) {
    if (activity) {
        editingActivityId = activity.id;
        document.querySelector('#modal-activity h3').innerText = '编辑活动';
        document.getElementById('act-title').value = activity.title;
        document.getElementById('act-desc').value = activity.desc || '';
        document.getElementById('act-date').value = activity.date || '';
        document.getElementById('act-location').value = activity.location || '';
        document.getElementById('act-status').value = activity.status || '筹备中';
    } else {
        editingActivityId = null;
        document.querySelector('#modal-activity h3').innerText = '发起活动';
        document.getElementById('act-title').value = '';
        document.getElementById('act-desc').value = '';
        document.getElementById('act-date').value = '';
        document.getElementById('act-location').value = '';
        document.getElementById('act-status').value = '筹备中';
    }
    toggleModal('modal-activity');
}

async function submitActivity() {
    const btn = document.querySelector('#modal-activity button');
    const oldText = btn.innerText;
    btn.innerText = '提交中...';
    btn.disabled = true;

    try {
        const data = {
            title: document.getElementById('act-title').value,
            desc: document.getElementById('act-desc').value,
            date: document.getElementById('act-date').value,
            location: document.getElementById('act-location').value,
            status: document.getElementById('act-status').value,
            publisher: currentUser ? (currentUser.alias || currentUser.name) : 'Unknown',
            publisher_id: currentUser ? currentUser.id : null  // 存储发布者ID用于动态查找
        };

        if(!data.title || !data.date) { alert('活动主题和时间为必填项'); throw new Error('Required fields missing'); }

        let url = `${API_BASE}/activities`;
        if(editingActivityId) {
            url = `${API_BASE}/activities/update`;
            data.id = editingActivityId;
        }

        const res = await fetchWithAuth(url, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(data)
        });
        
        if(!res.ok) throw new Error('Failed');
        
        toggleModal('modal-activity');
        fetchActivities();
        loadSystemInfo(); // Refresh Home list too
    } catch(e) {
        console.error(e);
        alert('提交失败');
    } finally {
        btn.innerText = oldText;
        btn.disabled = false;
    }
}

async function deleteActivity(id, event) {
    if(!confirm('确定删除此活动？')) return;
    
    // 获取按钮并禁用，防止重复提交
    const btn = event?.target;
    const oldText = btn ? btn.innerText : '';
    const oldStyle = btn ? btn.style.cssText : '';
    if (btn) {
        btn.disabled = true;
        btn.innerText = '删除中...';
        btn.style.background = '#999';
        btn.style.color = '#fff';
        btn.style.borderColor = '#999';
    }
    
    try {
        await fetch(`${API_BASE}/activities/delete`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(withToken({id}))
        });
        fetchActivities();
        loadSystemInfo(); // Refresh Home list too
    } finally {
        if (btn) {
            btn.style.cssText = oldStyle;
            btn.innerText = oldText;
            btn.disabled = false;
        }
    }
}

// Submissions
async function submitPoem() {
    const submitBtn = document.querySelector('#modal-poem button');
    const originalText = submitBtn.innerText;
    submitBtn.innerText = '提交中...';
    submitBtn.disabled = true;

    try {
        const data = {
            title: document.getElementById('p-title').value,
            // Automatically use current user alias or name
            author: (currentUser.alias && currentUser.alias.trim()) ? currentUser.alias : currentUser.name,
            author_id: currentUser.id,  // 存储作者ID用于动态查找
            type: document.getElementById('p-type').value,
            content: document.getElementById('p-content').value,
            date: new Date().toISOString().split('T')[0]
        };

        if (!data.title || !data.content) {
            alert("请填写完整的诗词/文章信息");
            return;
        }
        
        let url = `${API_BASE}/poems`;
        if (editingPoemId) {
            url = `${API_BASE}/poems/update`;
            data.id = editingPoemId;
            // keep original date or author? Backend updates title/content/type only.
        }

        const response = await fetch(url, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(data)
        });

        if (!response.ok) {
            throw new Error(`Server Error: ${response.status}`);
        }
        
        // Clear inputs
        document.getElementById('p-title').value = '';
        document.getElementById('p-content').value = '';

        toggleModal('modal-poem');
        showSection('poems'); // This triggers fetchPoems()
    } catch (error) {
        console.error('Submission failed:', error);
        alert('提交失败: ' + error.message);
    } finally {
        submitBtn.innerText = originalText;
        submitBtn.disabled = false;
    }
}

function openFinanceModal(id = null) {
    if (id) {
        // 编辑模式：从缓存查找记录填充表单
        const record = _cachedFinance.find(r => r.id === id);
        if (!record) return;
        editingFinanceId = id;
        document.querySelector('#modal-finance h3').innerText = '编辑财务记录';
        document.getElementById('f-type').value = record.type || 'income';
        document.getElementById('f-category').value = record.category || '会费';
        document.getElementById('f-amount').value = record.amount;
        document.getElementById('f-summary').value = record.summary || '';
        document.getElementById('f-handler').value = record.handler || '';
        document.getElementById('f-date').value = record.date || '';
    } else {
        // 新建模式：清空表单，日期默认今天
        editingFinanceId = null;
        document.querySelector('#modal-finance h3').innerText = '财务记账';
        document.getElementById('f-type').value = 'income';
        document.getElementById('f-category').value = '会费';
        document.getElementById('f-amount').value = '';
        document.getElementById('f-summary').value = '';
        document.getElementById('f-handler').value = '';
        document.getElementById('f-date').value = new Date().toISOString().split('T')[0];
    }
    toggleModal('modal-finance');
}

async function submitFinance() {
    const submitBtn = document.querySelector('#modal-finance button');
    const originalText = submitBtn.innerText;
    submitBtn.innerText = '提交中...';
    submitBtn.disabled = true;

    try {
        const data = {
            type: document.getElementById('f-type').value,
            category: document.getElementById('f-category').value,
            amount: parseFloat(document.getElementById('f-amount').value),
            summary: document.getElementById('f-summary').value,
            handler: document.getElementById('f-handler').value,
            date: document.getElementById('f-date').value
        };

        if (isNaN(data.amount) || !data.summary || !data.handler || !data.date) {
            alert('金额、摘要、经办人和记账日期为必填项');
            return;
        }

        // 区分新建vs编辑
        let url = `${API_BASE}/finance`;
        if (editingFinanceId) {
            url = `${API_BASE}/finance/update`;
            data.id = editingFinanceId;
        }

        const response = await fetchWithAuth(url, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(data)
        });

        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.error || `Server Error: ${response.status}`);
        }

        toggleModal('modal-finance');
        showSection('finance');
    } catch(err) {
        alert('提交失败: ' + err.message);
    } finally {
        submitBtn.innerText = originalText;
        submitBtn.disabled = false;
    }
}

async function deleteFinance(id, event) {
    if (!confirm('确定删除此财务记录？此操作不可撤销。')) return;
    
    const btn = event?.target;
    const oldText = btn ? btn.innerText : '';
    const oldStyle = btn ? btn.style.cssText : '';
    if (btn) {
        btn.disabled = true;
        btn.innerText = '删除中...';
        btn.style.background = '#999';
        btn.style.color = '#fff';
        btn.style.borderColor = '#999';
    }
    
    try {
        const res = await fetchWithAuth(`${API_BASE}/finance/delete`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({id})
        });
        if (res.ok) {
            fetchFinance();
        } else {
            const err = await res.json().catch(() => ({}));
            alert('删除失败: ' + (err.error || '未知错误'));
        }
    } catch(e) {
        alert('网络错误，请重试');
    } finally {
        if (btn) {
            btn.style.cssText = oldStyle;
            btn.innerText = oldText;
            btn.disabled = false;
        }
    }
}

let _homeActivities = []; // Store for home usage

async function openActivityDetailView(id) {
    // 确保成员缓存已加载（用于显示发布者名称）
    await ensureMembersCached();
    
    // Search in caches - prefer _cachedActivities (fresher if visited/edited) over _homeActivities
    let act = null;
    if(typeof _cachedActivities !== 'undefined' && _cachedActivities.length > 0) {
        act = _cachedActivities.find(a => a.id === id);
    }
    if(!act) {
        act = _homeActivities.find(a => a.id === id);
    }
    
    if(act) {
        // Read-only view
        document.getElementById('view-act-title').innerText = act.title;
        
        // Integrated render
        const container = document.getElementById('view-act-container');
        container.innerHTML = `
            <div style="background:#f8f9fa; padding:15px; border-radius:8px; margin-bottom:20px; font-size:0.95rem;">
                <div style="margin-bottom:8px; display:flex;">
                    <span style="color:#666; width:80px; flex-shrink:0;">活动时间</span>
                    <span>${formatDate(act.date)}</span>
                </div>
                <div style="margin-bottom:8px; display:flex;">
                    <span style="color:#666; width:80px; flex-shrink:0;">活动地点</span>
                    <span>${escapeHtml(act.location || '线上')}</span>
                </div>
                <div style="display:flex;">
                    <span style="color:#666; width:80px; flex-shrink:0;">发布人</span>
                    <span>${getSmartDisplayName(act.publisher_id, act.publisher) || '未知'}</span>
                </div>
            </div>
            <div class="markdown-content">${renderMarkdown((act.desc || '（暂无详情）').trim())}</div>
        `;
        
        const statusEl = document.getElementById('view-act-status');
        statusEl.innerText = act.status;
        statusEl.style = getStatusStyle(act.status).replace('float:right;', '');
        
        // Action Buttons (Edit/Delete)
        const actionsEl = document.getElementById('view-act-actions');
        const isManager = currentUser && ['super_admin', 'admin', 'director'].includes(currentUser.role);
        
        if(isManager) {
            // pass id to onclick to find it again or we can use global var
            // simplify: just onclick calls a function that finds it by id
            actionsEl.innerHTML = `
                <button onclick="editActivityFromView(${act.id})" style="background:#4CAF50; padding:6px 14px; font-size:0.9em;">编辑</button>
                <button onclick="deleteActivityInView(${act.id}, event)" style="background:#e74c3c; padding:6px 14px; font-size:0.9em;">删除</button>
            `;
        } else {
            actionsEl.innerHTML = '';
        }

        toggleModal('modal-activity-view');
    }
}

function editActivityFromView(id) {
    toggleModal('modal-activity-view'); // Close view
    const act = (typeof _cachedActivities !== 'undefined' ? _cachedActivities : []).find(a => a.id === id) || _homeActivities.find(a => a.id === id);
    if(act) openActivityModal(act);
}

async function deleteActivityInView(id, event) {
    toggleModal('modal-activity-view'); // Close view first
    await deleteActivity(id, event); // deleteActivity has its own confirm
}

/* ============================================================================
   年度诗词周报热力图
   ============================================================================ */

let _heatmapYearInited = false;

async function loadWeeklyHeatmap() {
    const sel = document.getElementById('heatmap-year-select');
    const year = sel && sel.value ? sel.value : new Date().getFullYear();
    try {
        const res = await fetch(`${API_BASE}/poems/weekly-stats?year=${year}`);
        if (!res.ok) throw new Error('请求失败');
        const data = await res.json();
        renderWeeklyHeatmap(data);
    } catch (e) {
        console.error('热力图加载失败:', e);
        const grid = document.getElementById('weekly-heatmap');
        if (grid) grid.innerHTML = '<div class="empty-hint">加载失败</div>';
    }
}

function renderWeeklyHeatmap(data) {
    const sel = document.getElementById('heatmap-year-select');
    if (!_heatmapYearInited && sel) {
        const cur = new Date().getFullYear();
        sel.innerHTML = '';
        for (let y = cur; y >= cur - 4; y--) {
            const opt = document.createElement('option');
            opt.value = y;
            opt.textContent = y + '年';
            sel.appendChild(opt);
        }
        sel.value = data.year;
        _heatmapYearInited = true;
    }

    const actSet = new Set(data.act_weeks || []);
    const grid = document.getElementById('weekly-heatmap');
    if (!grid) return;

    const cells = [];
    for (let i = 0; i < 52; i++) {
        const count = data.weeks[i] || 0;
        const isAct = actSet.has(i);
        let cls, tip;
        if (isAct) {
            cls = 'activity';
            tip = '第' + (i + 1) + '周: ' + count + '篇诗文 【活动周】';
        } else {
            let lvl = 0;
            if (count >= 11) lvl = 4;
            else if (count >= 6) lvl = 3;
            else if (count >= 3) lvl = 2;
            else if (count >= 1) lvl = 1;
            cls = 'level-' + lvl;
            tip = '第' + (i + 1) + '周: ' + count + '篇诗文';
        }
        cells.push('<div class="week-cell ' + cls + '" data-tooltip="' + tip + '"></div>');
    }
    grid.innerHTML = cells.join('');
    // 移动端点击显示周信息
    grid.onclick = function(e) {
        const cell = e.target.closest('.week-cell');
        const info = document.getElementById('heatmap-info');
        if (info) info.textContent = cell ? (cell.getAttribute('data-tooltip') || '') : '';
    };
}

async function loadSystemInfo() {
    // 确保成员缓存已加载（用于首页显示诗作作者）
    await ensureMembersCached();
    
    // 系统信息仅登录用户可查看
    if (currentUser) {
        try {
            const res = await fetchWithAuth(`${API_BASE}/system/info`);
            const info = await res.json();
        
        // Convert bytes to KB
        const free = Math.round(info.free_storage / 1024);
        const total = Math.round(info.total_storage / 1024);
        const freeRam = Math.round((info.free_ram || 0) / 1024);
        const totalRam = Math.round((info.total_ram || 2048 * 1024) / 1024);
        
        // 1. Front-end Simple Info (Home)
        const simpleEl = document.getElementById('simple-storage-info');
        if(simpleEl) {
            simpleEl.innerText = `存储空间: 剩余 ${free}KB / 总共 ${total}KB`;
        }

        // 2. Back-end Admin Info (Admin Page) - Progress Bar Style
        const adminPlatform = document.getElementById('admin-platform');
        if(adminPlatform) {
            adminPlatform.innerText = info.platform;
            
            // Storage progress bar
            const usedStorage = total - free;
            const storagePercent = Math.round((usedStorage / total) * 100);
            document.getElementById('admin-storage-text').innerText = `${free} KB 可用 / ${total} KB`;
            const storageBar = document.getElementById('admin-storage-bar');
            storageBar.style.width = `${storagePercent}%`;
            if(storagePercent > 90) storageBar.className = 'status-bar-fill danger';
            else if(storagePercent > 70) storageBar.className = 'status-bar-fill warning';
            else storageBar.className = 'status-bar-fill';
            
            // RAM progress bar
            const usedRam = totalRam - freeRam;
            const ramPercent = Math.round((usedRam / totalRam) * 100);
            document.getElementById('admin-ram-text').innerText = `${freeRam} KB 可用 / ${totalRam} KB`;
            const ramBar = document.getElementById('admin-ram-bar');
            ramBar.style.width = `${ramPercent}%`;
            if(ramPercent > 90) ramBar.className = 'status-bar-fill danger';
            else if(ramPercent > 70) ramBar.className = 'status-bar-fill warning';
            else ramBar.className = 'status-bar-fill';
            
            // 系统时间显示
            const sysTimeEl = document.getElementById('admin-system-time');
            if(sysTimeEl && info.system_time) {
                sysTimeEl.innerText = info.system_time;
            }
            
            // CPU温度显示 (进度条风格)
            const cpuTempTextEl = document.getElementById('admin-cpu-temp-text');
            const cpuTempBarEl = document.getElementById('admin-cpu-temp-bar');
            if(cpuTempTextEl && cpuTempBarEl) {
                if(info.cpu_temp !== null && info.cpu_temp !== undefined) {
                    const temp = info.cpu_temp;
                    cpuTempTextEl.innerText = `${temp.toFixed(1)}°C`;
                    // 温度范围: 0-100°C，映射为百分比
                    const percent = Math.min(100, Math.max(0, temp));
                    cpuTempBarEl.style.width = `${percent}%`;
                    // 根据温度设置进度条颜色
                    cpuTempBarEl.classList.remove('warm', 'hot');
                    if(temp > 80) cpuTempBarEl.classList.add('hot');
                    else if(temp > 60) cpuTempBarEl.classList.add('warm');
                } else {
                    cpuTempTextEl.innerText = '不支持';
                    cpuTempBarEl.style.width = '0%';
                }
            }
            
            // WiFi信号强度显示 (进度条风格)
            const wifiTextEl = document.getElementById('admin-wifi-signal-text');
            const wifiBarEl = document.getElementById('admin-wifi-signal-bar');
            if(wifiTextEl && wifiBarEl && info.wifi_rssi !== undefined) {
                const rssi = info.wifi_rssi;
                const ssid = info.wifi_ssid || 'Unknown';
                let signalText = '';
                
                // 根据RSSI值判断信号质量
                // RSSI范围通常 -100dBm(差) 到 -30dBm(极好)
                // 映射为百分比: (-100 - rssi) / -70 * 100
                const percent = Math.min(100, Math.max(0, (rssi + 100) / 70 * 100));
                
                wifiBarEl.classList.remove('weak', 'poor');
                if(rssi >= -50) {
                    signalText = '极好';
                } else if(rssi >= -60) {
                    signalText = '良好';
                } else if(rssi >= -70) {
                    signalText = '一般';
                    wifiBarEl.classList.add('weak');
                } else {
                    signalText = '较弱';
                    wifiBarEl.classList.add('poor');
                }
                
                wifiTextEl.innerText = `${ssid} (${rssi}dBm ${signalText})`;
                wifiBarEl.style.width = `${percent}%`;
            }
            
            // 更新WiFi模式指示（编号颜色）
            // 使用独立的激活状态，支持同时显示两种模式
            const staBadge = document.getElementById('wifi-mode-sta-badge');
            const apBadge = document.getElementById('wifi-mode-ap-badge');
            if (staBadge && apBadge) {
                const activeColor = 'var(--accent)';
                const inactiveColor = '#6c757d';
                // STA模式：已连接时显示绿色
                staBadge.style.background = info.sta_active ? activeColor : inactiveColor;
                // AP模式：已激活时显示绿色
                apBadge.style.background = info.ap_active ? activeColor : inactiveColor;
            }
        }
        } catch(e) {
            console.error('加载系统信息失败:', e);
        }
    }
    
    // 以下为首页公开内容，所有用户可见
    try {
        // Load Daily Recommendation (Random from all poems)
        const pRes = await fetch(`${API_BASE}/poems/random`);
        const p = await pRes.json();
        if(p && p.title) {
            document.getElementById('daily-poem').innerHTML = `
                <h4>${escapeHtml(p.title)}</h4>
                <div class="markdown-content">${renderMarkdown(p.content)}</div>
                <small>—— ${getSmartDisplayName(p.author_id, p.author)}</small>
            `;
        } else {
            document.getElementById('daily-poem').innerHTML = '<div class="empty-hint">暂无诗词，快去藏诗阁发布吧！</div>';
        }

        // Load Home Activities (Recent 3 unfinished)
        const homeActList = document.getElementById('home-activities-list');
        if (homeActList) {
            try {
                const aRes = await fetch(`${API_BASE}/activities`);
                let activities = await aRes.json();
                _homeActivities = activities; // Cache for click handler
                
                // Filter not '已结束', Sort by date ASC (soonest first), Take 3
                const upcoming = activities
                    .sort((a, b) => new Date(b.date) - new Date(a.date))
                    .slice(0, 3);
                
                if(upcoming.length === 0) {
                    homeActList.innerHTML = '<div class="empty-hint">暂无近期活动</div>';
                } else {
                    homeActList.innerHTML = upcoming.map(a => `
                        <div onclick="openActivityDetailView(${a.id})" style="border-bottom: 1px solid #eee; padding: 12px 0; display:flex; justify-content:space-between; align-items:center; cursor:pointer;" class="clickable-item">
                            <div style="flex: 1; min-width: 0; padding-right: 10px;">
                                <strong style="font-size:1.1em; display:block; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${escapeHtml(a.title)}</strong>
                                <div style="font-size:0.85em; color:#999; margin-top:6px;">
                                    <span style="margin-right:12px;">${formatDate(a.date)}</span>
                                    <span>${escapeHtml(a.location || '线上')}</span>
                                </div>
                            </div>
                            <span class="points-badge" style="${getStatusStyle(a.status)}; margin:0; float:none; flex-shrink:0;">${a.status}</span>
                        </div>
                    `).join('');
                }
            } catch(e) {
                homeActList.innerHTML = '<div class="empty-hint">加载失败，请刷新重试</div>';
                console.error(e);
            }
        }
        
        // 加载最新诗作
        loadLatestPoems();
        
        // 加载积分排行榜
        loadPointsRanking();
        
    } catch(e) {
        console.error(e);
    }
}

// --- 最新诗作 ---
let _homeLatestPoems = [];

async function loadLatestPoems() {
    // 确保成员缓存已加载（用于显示作者名称）
    await ensureMembersCached();
    
    const container = document.getElementById('latest-poems-list');
    if(!container) return;
    
    try {
        const res = await fetch(`${API_BASE}/poems?page=1&limit=3`);
        const poems = await res.json();
        _homeLatestPoems = poems;
        
        if(poems.length === 0) {
            container.innerHTML = '<div class="empty-hint">暂无诗作</div>';
            return;
        }
        
        container.innerHTML = poems.map(p => `
            <div style="border-bottom:1px solid #eee; padding:10px 0; cursor:pointer;" onclick="openHomePoemDetail(${p.id})">
                <div style="display:flex; justify-content:space-between; align-items:center; gap:8px;">
                    <strong style="font-size:1em; flex:1; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${escapeHtml(p.title)}</strong>
                    <span style="${getPoemTypeStyle(p.type)} padding:2px 6px; border-radius:4px; font-size:0.75em; flex-shrink:0;">${escapeHtml(p.type)}</span>
                </div>
                <div style="font-size:0.85em; color:#888; margin-top:4px;">${getSmartDisplayName(p.author_id, p.author)}</div>
            </div>
        `).join('');
    } catch(e) {
        console.error(e);
        container.innerHTML = '<div class="empty-hint">加载失败，请刷新重试</div>';
    }
}

function openHomePoemDetail(id) {
    const p = _homeLatestPoems.find(x => x.id == id);
    if (p) openPoemDetailView(p);
}

// --- 积分排行榜 ---
async function loadPointsRanking() {
    const container = document.getElementById('points-ranking-list');
    if(!container) return;
    
    // 动态更新标题为年度排行榜
    const titleEl = document.getElementById('points-ranking-title');
    if(titleEl) {
        titleEl.innerText = `${getPointsName()} · 年度排行`;
    }
    
    try {
        const res = await fetch(`${API_BASE}/points/yearly_ranking`);
        const ranking = await res.json();
        
        if(ranking.length === 0) {
            container.innerHTML = '<div class="empty-hint">暂无年度数据</div>';
            return;
        }
        
        const medals = ['🥇', '🥈', '🥉', '4', '5'];
        const pointsName = getPointsName();
        
        // 只显示前5名
        const top5 = ranking.slice(0, 5);
        
        container.innerHTML = top5.map((m, i) => `
            <div style="display:flex; justify-content:space-between; align-items:center; padding:8px 0; border-bottom:1px solid #eee;">
                <div style="display:flex; align-items:center; gap:10px;">
                    <span style="font-size:${i < 3 ? '1.2em' : '0.9em'}; min-width:24px; text-align:center;">${medals[i]}</span>
                    <span style="font-weight:${i < 3 ? '600' : '400'};">${escapeHtml(m.alias || m.name)}</span>
                </div>
                <span class="points-badge" title="年度新增${pointsName}">❤️‍🔥 +${m.yearly_points || 0}</span>
            </div>
        `).join('');
    } catch(e) {
        console.error(e);
        container.innerHTML = '<div class="empty-hint">加载失败，请刷新重试</div>';
    }
}

// --- Global Search Logic ---
let _globalSearchTerm = '';
let _searchCache = { poems: [], activities: [] };
let _debounceTimer = null;
let _currentSearchReq = 0; // To track latest request

function openPoemFromSearch(id) {
    const p = _searchCache.poems.find(x => x.id == id);
    if(p) openPoemDetailView(p);
}

function openActivityFromSearch(id) {
    openActivityDetailView(id);
}

// This is called when user types in global search input
async function handleGlobalSearch(term) {
    // 确保成员缓存已加载（用于搜索结果显示作者名称）
    await ensureMembersCached();
    
    if (!term) {
        clearGlobalSearch();
        return;
    }
    
    // Switch to search results section immediately
    document.querySelectorAll('main > section').forEach(el => el.classList.add('hidden'));
    document.getElementById('search-results-section').classList.remove('hidden');
    // 隐藏首页专用的热力图
    const hmc = document.getElementById('weekly-heatmap-container');
    if (hmc) hmc.classList.add('hidden');
    
    // Optimistic UI for immediate feedback
    const resultsContainer = document.getElementById('search-results-container');
    resultsContainer.innerHTML = '<div style="text-align:center; padding:20px; color:#666;">正在搜索...</div>';
    
    const t = term.toLowerCase(); 
    const thisReqId = ++_currentSearchReq;

    try {
        // SERVER SIDE SEARCH for Scalability
        // 事务搜索仅对已登录用户开放，使用 fetchWithAuth 自动带上 token
        const tasksPromise = currentUser 
            ? fetchWithAuth(`${API_BASE}/tasks?page=1&limit=20&q=${encodeURIComponent(term)}`).then(r => r.ok ? r.json() : {data:[]}).catch(()=>({data:[]}))
            : Promise.resolve({data: []});
        
        const [poems, activities, tasksRes] = await Promise.all([
            fetch(`${API_BASE}/poems?limit=20&q=${encodeURIComponent(term)}`).then(r=>r.json()).catch(()=>[]),
            fetch(`${API_BASE}/activities?limit=20&q=${encodeURIComponent(term)}`).then(r=>r.json()).catch(()=>[]),
            tasksPromise
        ]);
        
        // Race Condition Check: If a newer request has started, ignore this result
        if (thisReqId !== _currentSearchReq) return;
        
        _searchCache = { poems, activities };

        // Tasks 从分页响应中提取数据
        const matchedTasks = tasksRes.data || tasksRes || [];

        // Render Results
        let html = '';
        const highlight = (text) => text ? String(text).replace(new RegExp(t, 'gi'), match => `<span style="background:#ffeb3b; color:#000;">${match}</span>`) : '';

        if (activities.length > 0) {
            html += `<h4>活动 (${activities.length})</h4>`;
            html += activities.map(a => `<div class="card" onclick="openActivityFromSearch(${a.id})" style="cursor:pointer; margin-bottom:10px;"><b>[活动] ${highlight(a.title)}</b><br><small>${highlight(a.date)} ${highlight(a.location)}</small></div>`).join('');
        }
        
        if (poems.length > 0) {
            html += `<h4>藏诗阁 (${poems.length})</h4>`;
            html += poems.map(p => `
                <div class="card" onclick="openPoemFromSearch(${p.id})" style="cursor:pointer; margin-bottom:10px;">
                    <b>[作品] ${highlight(p.title)}</b> - ${highlight(getSmartDisplayName(p.author_id, p.author))}
                    <br><small style="color:#666; font-size:0.8em;">${highlight(p.content ? p.content.substring(0, 30) : '')}...</small>
                </div>`).join('');
        }
        
        if (matchedTasks.length > 0) {
            html += `<h4>事务 (${matchedTasks.length})</h4>`;
            html += matchedTasks.map(tk => `<div class="card task-item" style="margin-bottom:10px;"><b>[任务] ${highlight(tk.title)}</b><br><small>${highlight(tk.description)}</small></div>`).join('');
        }
        
        if (!html) {
            html = '<div style="text-align:center; color:#999; padding:20px;">没有找到相关内容</div>';
        }
        
        resultsContainer.innerHTML = html;

    } catch(e) {
        if (thisReqId === _currentSearchReq) {
            console.error(e);
            resultsContainer.innerHTML = '<div style="text-align:center; color:red;">搜索失败</div>';
        }
    }
}


function clearGlobalSearch() {
    document.getElementById('global-search-input').value = '';
    _globalSearchTerm = '';
    document.getElementById('search-results-section').classList.add('hidden');
    
    // Restore the section the user was on before searching
    if (_lastSection) {
        showSection(_lastSection);
    } else {
        showSection('home');
    }
}

// Init
window.onload = function() {
    try {
        checkLogin();

        // Hook up Global Search
        const searchInput = document.getElementById('global-search-input');
        if (searchInput) {
            searchInput.addEventListener('input', (e) => {
                _globalSearchTerm = e.target.value;
                
                // Debounce
                if (_debounceTimer) clearTimeout(_debounceTimer);
                _debounceTimer = setTimeout(() => {
                    if(typeof handleGlobalSearch === 'function') {
                        handleGlobalSearch(_globalSearchTerm);
                    }
                }, 500); // 500ms delay
            });
        }
    } catch(e) {
        console.error("Init Error:", e);
        // Fallback: Ensure login screen is visible if something crashes
        document.getElementById('login-section').classList.remove('hidden');
    }
}

// --- Custom Fields Management ---

async function fetchCustomFields() {
    try {
        const res = await fetchWithAuth(`${API_BASE}/settings/fields`);
        if(res.ok) _customFields = await res.json();
    } catch(e) { console.error('Failed to load custom fields', e); }
}

// --- 系统设置管理 ---
async function fetchSystemSettings() {
    try {
        // 如果 checkSystemSettings 已加载基础设置，跳过重复请求
        if (!_settingsLoaded) {
            const res = await fetch(`${API_BASE}/settings/system`);
            if(res.ok) {
                _systemSettings = await res.json();
                _settingsLoaded = true;
                // 更新网页标题和页脚站名
                const name = _systemSettings.system_name || '围炉诗社·理事台';
                document.title = name;
                const footerName = document.getElementById('footer-site-name');
                if (footerName) footerName.textContent = name;
            }
        }
        
        // 管理员额外获取salt和登录有效期（需要鉴权）
        if(currentUser && (currentUser.role === 'super_admin' || currentUser.role === 'admin')) {
            const saltRes = await fetchWithAuth(`${API_BASE}/settings/salt`);
            if(saltRes.ok) {
                const saltData = await saltRes.json();
                _systemSettings.password_salt = saltData.password_salt;
            }
            const tokenExpireRes = await fetchWithAuth(`${API_BASE}/settings/token_expire`);
            if(tokenExpireRes.ok) {
                const expireData = await tokenExpireRes.json();
                _systemSettings.token_expire_days = expireData.token_expire_days;
            }
        }
    } catch(e) { console.error('Failed to load system settings', e); }
}

function loadSystemSettingsUI() {
    const systemNameInput = document.getElementById('setting-system-name');
    const saltInput = document.getElementById('setting-password-salt');
    const pointsInput = document.getElementById('setting-points-name');
    const tokenExpireInput = document.getElementById('setting-token-expire-days');
    if(systemNameInput) systemNameInput.value = _systemSettings.system_name || '围炉诗社·理事台';
    // salt 只有管理员能获取，非管理员显示占位符
    if(saltInput) saltInput.value = _systemSettings.password_salt || '(需管理员权限查看)';
    if(pointsInput) pointsInput.value = _systemSettings.points_name || '围炉值';
    // 登录有效期只有管理员能获取
    if(tokenExpireInput) tokenExpireInput.value = _systemSettings.token_expire_days || 30;
}

async function saveSystemName() {
    const input = document.getElementById('setting-system-name');
    const value = input.value.trim();
    if(!value) { alert('系统名称不能为空'); return; }
    if(value.length > 32) { alert('系统名称不能超过32个字符'); return; }
    
    try {
        const res = await fetch(`${API_BASE}/settings/system`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(withToken({ system_name: value }))
        });
        if(res.ok) {
            _systemSettings.system_name = value;
            document.title = value;
            const footerName = document.getElementById('footer-site-name');
            if (footerName) footerName.textContent = value;
            alert('系统名称已更新');
        } else {
            const err = await res.json().catch(() => ({}));
            alert('保存失败: ' + (err.error || '权限不足'));
        }
    } catch(e) { console.error(e); alert('网络错误'); }
}

async function savePointsName() {
    const input = document.getElementById('setting-points-name');
    const value = input.value.trim();
    if(!value) { alert('积分名称不能为空'); return; }
    if(value.length > 10) { alert('积分名称不能超过10个字符'); return; }
    
    try {
        const res = await fetch(`${API_BASE}/settings/system`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(withToken({ points_name: value }))
        });
        if(res.ok) {
            _systemSettings.points_name = value;
            alert('积分名称已更新');
            // 刷新页面以更新所有积分显示
            if(confirm('是否刷新页面以应用新名称？')) {
                location.reload();
            }
        } else {
            const err = await res.json().catch(() => ({}));
            alert('保存失败: ' + (err.error || '权限不足'));
        }
    } catch(e) {
        console.error(e);
        alert('网络错误');
    }
}

async function savePasswordSalt() {
    const input = document.getElementById('setting-password-salt');
    const value = input.value.trim();
    if(!value) { alert('Salt不能为空'); return; }
    if(value.length < 32 || value.length > 1024) { alert('Salt长度必须为32-1024个字符'); return; }
    
    // 要求输入新的超级管理员密码
    const newPwd = prompt('修改Salt后所有现有密码将失效！\n请输入新的超级管理员密码（至少6位）：');
    if(newPwd === null) return;  // 用户取消
    if(!newPwd || newPwd.length < 6 || newPwd.length > 32) {
        alert('超级管理员密码长度必须为6-32位');
        return;
    }
    
    if(!confirm('确认修改Salt并重置超级管理员密码？\n其他所有用户密码将失效，需由管理员重新设置。')) return;
    
    try {
        const res = await fetchWithAuth(`${API_BASE}/settings/salt`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ password_salt: value, super_admin_password: newPwd })
        });
        if(res.ok) {
            _systemSettings.password_salt = value;
            alert('Salt已更新，超级管理员密码已重置。\n其他用户需由管理员重新设置密码。');
            // Salt变更后当前token可能失效，强制重新登录
            localStorage.removeItem('user');
            location.reload();
        } else {
            const err = await res.json().catch(() => ({}));
            alert('保存失败: ' + (err.error || '权限不足'));
        }
    } catch(e) {
        console.error(e);
        alert('网络错误');
    }
}

async function saveTokenExpireDays() {
    const input = document.getElementById('setting-token-expire-days');
    const value = parseInt(input.value);
    if(isNaN(value) || value < 1 || value > 365) {
        alert('登录有效期必须在1-365天之间');
        return;
    }
    
    try {
        const res = await fetchWithAuth(`${API_BASE}/settings/token_expire`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ token_expire_days: value })
        });
        if(res.ok) {
            _systemSettings.token_expire_days = value;
            alert('登录有效期已更新为 ' + value + ' 天');
        } else {
            const err = await res.json().catch(() => ({}));
            alert('保存失败: ' + (err.error || '权限不足'));
        }
    } catch(e) {
        console.error(e);
        alert('网络错误');
    }
}

// 加载站点功能设置
async function loadSiteSettings() {
    try {
        const res = await fetch(`${API_BASE}/settings/system`);
        if(res.ok) {
            const data = await res.json();
            const siteOpenEl = document.getElementById('setting-site-open');
            const allowGuestEl = document.getElementById('setting-allow-guest');
            const chatEnabledEl = document.getElementById('setting-chat-enabled');
            const chatGuestMaxEl = document.getElementById('setting-chat-guest-max');
            const chatMaxUsersEl = document.getElementById('setting-chat-max-users');
            const chatCacheSizeEl = document.getElementById('setting-chat-cache-size');
            if(siteOpenEl) siteOpenEl.checked = data.site_open !== false;
            if(allowGuestEl) allowGuestEl.checked = data.allow_guest !== false;
            if(chatEnabledEl) chatEnabledEl.checked = data.chat_enabled !== false;
            if(chatGuestMaxEl) chatGuestMaxEl.value = data.chat_guest_max ?? 10;
            if(chatMaxUsersEl) chatMaxUsersEl.value = data.chat_max_users || 20;
            if(chatCacheSizeEl) chatCacheSizeEl.value = data.chat_cache_size || 128;
        }
    } catch(e) {
        console.error('加载站点设置失败:', e);
    }
}

// 保存站点功能设置
async function saveSiteSettings() {
    const siteOpenEl = document.getElementById('setting-site-open');
    const allowGuestEl = document.getElementById('setting-allow-guest');
    const chatEnabledEl = document.getElementById('setting-chat-enabled');
    const chatGuestMaxEl = document.getElementById('setting-chat-guest-max');
    const chatMaxUsersEl = document.getElementById('setting-chat-max-users');
    const chatCacheSizeEl = document.getElementById('setting-chat-cache-size');
    
    const settings = {};
    if(siteOpenEl) settings.site_open = siteOpenEl.checked;
    if(allowGuestEl) settings.allow_guest = allowGuestEl.checked;
    if(chatEnabledEl) settings.chat_enabled = chatEnabledEl.checked;
    
    // 校验龙门阵游客上限 (0-10)
    if(chatGuestMaxEl && chatGuestMaxEl.value !== '') {
        const guestMax = parseInt(chatGuestMaxEl.value);
        if(isNaN(guestMax) || guestMax < 0 || guestMax > 10) {
            alert('龙门阵游客上限必须为0-10之间的整数');
            chatGuestMaxEl.focus();
            return;
        }
        settings.chat_guest_max = guestMax;
    }
    
    // 校验龙门阵人数上限 (5-100)
    if(chatMaxUsersEl && chatMaxUsersEl.value !== '') {
        const maxUsers = parseInt(chatMaxUsersEl.value);
        if(isNaN(maxUsers) || maxUsers < 5 || maxUsers > 100) {
            alert('龙门阵人数上限必须为5-100之间的整数');
            chatMaxUsersEl.focus();
            return;
        }
        settings.chat_max_users = maxUsers;
    }
    
    // 校验聊天室缓存大小 (16-1024 KB)
    if(chatCacheSizeEl && chatCacheSizeEl.value !== '') {
        const cacheSize = parseInt(chatCacheSizeEl.value);
        if(isNaN(cacheSize) || cacheSize < 16 || cacheSize > 1024) {
            alert('聊天室缓存大小必须为16-1024之间的整数');
            chatCacheSizeEl.focus();
            return;
        }
        settings.chat_cache_size = cacheSize;
    }
    
    try {
        const res = await fetchWithAuth(`${API_BASE}/settings/system`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(settings)
        });
        if(res.ok) {
            alert('功能设置已保存');
        } else {
            const err = await res.json().catch(() => ({}));
            alert('保存失败: ' + (err.error || '权限不足'));
        }
    } catch(e) {
        console.error(e);
        alert('网络错误');
    }
}

// 获取积分名称
function getPointsName() {
    return _systemSettings.points_name || '围炉值';
}

async function addCustomFieldInput() {
    const input = document.getElementById('new-field-label');
    const typeSelect = document.getElementById('new-field-type');
    const requiredCheckbox = document.getElementById('new-field-required');
    const label = input.value.trim();
    const type = typeSelect ? typeSelect.value : 'text';
    const required = requiredCheckbox ? requiredCheckbox.checked : false;

    if(!label) return;
    if(label.length > 10) return alert('字段名称不能超过10个字符');
    
    // Check dupe
    if(_customFields.find(f => f.label === label)) return alert('字段名已存在');
    
    const newField = { id: 'cf_' + Date.now(), label: label, type: type, required: required };
    const newFields = [..._customFields, newField];
    
    await saveCustomFields(newFields);
    input.value = '';
    if (requiredCheckbox) requiredCheckbox.checked = false;
}

async function deleteCustomField(id) {
    if(!confirm('确定删除此字段？此操作仅移除字段定义，不会删除已有数据。')) return;
    const newFields = _customFields.filter(f => f.id !== id);
    await saveCustomFields(newFields);
}

async function saveCustomFields(fields) {
     try {
         const res = await fetch(`${API_BASE}/settings/fields`, {
             method: 'POST',
             headers: {'Content-Type': 'application/json'},
             body: JSON.stringify(withToken({fields: fields}))
         });
         if(res.ok) {
             _customFields = fields;
             renderCustomFieldsList(); 
             alert('设置已保存');
         } else {
             const err = await res.json().catch(() => ({}));
             alert('保存失败: ' + (err.error || '权限不足'));
         }
     } catch(e) { console.error(e); alert('网络错误'); }
}

function renderAdminSettings() {
    // 加载系统设置UI
    loadSystemSettingsUI();
    
    // 加载数据统计
    loadDataStats();
    
    // 加载缓存统计
    loadCacheStats();
    
    // 加载WiFi配置
    loadWifiConfig();
    
    // 加载站点功能设置
    loadSiteSettings();

    // 加载自定义字段列表
    renderCustomFieldsList();

    // 加载登录日志
    fetchLoginLogs();
}

// 渲染自定义字段列表
function renderCustomFieldsList() {
    const container = document.getElementById('settings-fields-list');
    if(!container) return;
    
    if(_customFields.length === 0) {
        container.innerHTML = '<div class="empty-hint">暂无自定义字段</div>';
        return;
    }

    const typeMap = { text: '文本', number: '数字', date: '日期', email: '邮箱', textarea: '多行文本' };

    container.innerHTML = _customFields.map(f => {
        const typeText = typeMap[f.type] || '文本';
        const requiredClass = f.required ? ' required' : '';
        const requiredText = f.required ? ' · 必填' : '';
        return `
        <div class="custom-field-item" data-field-id="${f.id}">
            <div class="custom-field-info">
                <span class="custom-field-name">${f.label}</span>
                <span class="custom-field-type${requiredClass}">${typeText}${requiredText}</span>
            </div>
            <div class="custom-field-actions">
                <button onclick="editCustomField('${f.id}')" class="custom-field-edit">编辑</button>
                <button onclick="deleteCustomField('${f.id}')" class="custom-field-delete">删除</button>
            </div>
        </div>`;
    }).join('');
}

// 编辑自定义字段
function editCustomField(fieldId) {
    const field = _customFields.find(f => f.id === fieldId);
    if(!field) return;
    
    const item = document.querySelector(`.custom-field-item[data-field-id="${fieldId}"]`);
    if(!item) return;
    
    const typeMap = { text: '文本', number: '数字', date: '日期', email: '邮箱', textarea: '多行文本' };
    const typeText = typeMap[field.type] || '文本';
    const checkedAttr = field.required ? 'checked' : '';
    
    item.classList.add('editing');
    item.innerHTML = `
        <div class="custom-field-edit-form">
            <input type="text" class="edit-field-name" value="${field.label}" maxlength="10" placeholder="字段名称">
            <span class="custom-field-type-readonly">${typeText}</span>
            <label class="required-toggle">
                <div class="toggle-switch">
                    <input type="checkbox" class="edit-field-required" ${checkedAttr}>
                    <span class="toggle-slider"></span>
                </div>
                <span class="required-switch-label">必填</span>
            </label>
        </div>
        <div class="custom-field-edit-actions">
            <button onclick="saveCustomFieldEdit('${fieldId}')" class="custom-field-save">保存</button>
            <button onclick="cancelCustomFieldEdit()" class="custom-field-cancel">取消</button>
        </div>`;
}

// 保存自定义字段编辑
async function saveCustomFieldEdit(fieldId) {
    const item = document.querySelector(`.custom-field-item[data-field-id="${fieldId}"]`);
    if(!item) return;
    
    const nameInput = item.querySelector('.edit-field-name');
    const requiredInput = item.querySelector('.edit-field-required');
    
    const newLabel = nameInput.value.trim();
    if(!newLabel) {
        alert('字段名称不能为空');
        nameInput.focus();
        return;
    }
    if(newLabel.length > 10) {
        alert('字段名称不能超过10个字符');
        nameInput.focus();
        return;
    }
    
    // 更新本地数据
    const fieldIndex = _customFields.findIndex(f => f.id === fieldId);
    if(fieldIndex === -1) return;
    
    _customFields[fieldIndex].label = newLabel;
    _customFields[fieldIndex].required = requiredInput.checked;
    
    // 保存到服务器
    try {
        const res = await fetchWithAuth(`${API_BASE}/settings/fields`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ fields: _customFields })
        });
        if(!res.ok) throw new Error('保存失败');
        renderCustomFieldsList();
    } catch(e) {
        console.error(e);
        alert('保存失败，请重试');
    }
}

// 取消自定义字段编辑
function cancelCustomFieldEdit() {
    renderCustomFieldsList();
}

// --- 数据统计 ---
async function loadDataStats() {
    try {
        const res = await fetchWithAuth(`${API_BASE}/system/stats`);
        if(res.ok) {
            const stats = await res.json();
            document.getElementById('stat-members').innerText = stats.members || 0;
            document.getElementById('stat-poems').innerText = stats.poems || 0;
            document.getElementById('stat-activities').innerText = stats.activities || 0;
            document.getElementById('stat-tasks').innerText = stats.tasks || 0;
            document.getElementById('stat-finance').innerText = stats.finance || 0;
        }
    } catch(e) { 
        console.error('Failed to load data stats', e); 
    }
}

// --- 缓存统计 ---
async function loadCacheStats() {
    const container = document.getElementById('cache-detail-list');
    if(!container) return;
    // 非超管不加载（卡片已隐藏，避免无权限请求）
    if(!currentUser || currentUser.role !== 'super_admin') return;

    try {
        const res = await fetchWithAuth(`${API_BASE}/system/cache-stats`);
        if(!res.ok) return;
        const data = await res.json();

        // 提取顶层字段
        const memFree = data.memory_free || 0;
        const memTotal = data.memory_total || 0;
        const chatSizeBytes = data.chat_size_bytes || 0;
        const chatSizeLimit = data.chat_size_limit || 0;

        // 收集缓存槽统计
        const slots = [];
        let totalEntries = 0, totalHits = 0, totalMisses = 0;
        for(const [name, info] of Object.entries(data)) {
            if(typeof info !== 'object' || !info.type) continue;
            slots.push({ name, ...info });
            totalEntries += info.size || 0;
            totalHits += info.hits || 0;
            totalMisses += info.misses || 0;
        }

        // 摘要
        const totalReqs = totalHits + totalMisses;
        const overallRate = totalReqs > 0 ? Math.round(totalHits / totalReqs * 100) : 0;
        document.getElementById('cache-slot-count').innerText = slots.length;
        document.getElementById('cache-total-entries').innerText = totalEntries;
        document.getElementById('cache-total-hit-rate').innerText = overallRate + '%';

        // 内存条
        if(memTotal > 0) {
            const memUsed = memTotal - memFree;
            const memPct = Math.round(memUsed / memTotal * 100);
            const memBar = document.getElementById('cache-memory-bar');
            const memText = document.getElementById('cache-memory-text');
            memText.innerText = formatBytes(memFree) + ' / ' + formatBytes(memTotal);
            memBar.style.width = memPct + '%';
            memBar.className = 'status-bar-fill' + (memPct > 85 ? ' danger' : memPct > 70 ? ' warning' : '');
        }

        // 详情表格
        if(slots.length === 0) {
            container.innerHTML = '<div class="empty-hint">暂无缓存数据</div>';
            return;
        }

        const typeLabels = { dict: '字典', list: '列表', value: '单值', const: '常量' };
        const header = `<div class="cache-table-header">
            <div>缓存名称</div><div>类型</div><div>条目</div><div>命中率</div><div>TTL</div><div>过期</div>
        </div>`;
        const rows = slots.map(s => {
            const total = s.hits + s.misses;
            const rate = total > 0 ? s.hit_rate + '%' : '-';
            const ttl = s.ttl > 0 ? s.ttl + 's' : '-';
            const expires = s.expires > 0 ? s.expires : '-';
            const typeLabel = typeLabels[s.type] || s.type;
            return `<div class="cache-table-row">
                <div class="cache-name" data-label="名称">${s.name}</div>
                <div data-label="类型"><span class="cache-type-badge cache-type-${s.type}">${typeLabel}</span></div>
                <div data-label="条目">${s.size}</div>
                <div data-label="命中率">${rate}</div>
                <div data-label="TTL">${ttl}</div>
                <div data-label="过期">${expires}</div>
            </div>`;
        }).join('');

        // 聊天内存用量附加信息
        let chatInfo = '';
        if(chatSizeLimit > 0) {
            const chatPct = Math.round(chatSizeBytes / chatSizeLimit * 100);
            chatInfo = `<div class="cache-chat-memory">聊天内存: ${formatBytes(chatSizeBytes)} / ${formatBytes(chatSizeLimit)} (${chatPct}%)</div>`;
        }

        container.innerHTML = `<div class="cache-table">${header}${rows}</div>${chatInfo}`;
    } catch(e) {
        console.error('Failed to load cache stats', e);
        container.innerHTML = '<div class="empty-hint">加载缓存统计失败</div>';
    }
}

function formatBytes(bytes) {
    if(bytes === 0 || bytes == null) return '0 B';
    const units = ['B', 'KB', 'MB'];
    let i = 0;
    let val = bytes;
    while(val >= 1024 && i < units.length - 1) { val /= 1024; i++; }
    return val.toFixed(i > 0 ? 1 : 0) + ' ' + units[i];
}

// --- 登录日志 ---
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

// --- WiFi 配置 ---
function toggleStaticIpFields() {
    const staticRadio = document.querySelector('input[name="wifi-ip-mode"][value="static"]');
    const fields = document.getElementById('static-ip-fields');
    if(staticRadio && fields) {
        fields.classList.toggle('hidden', !staticRadio.checked);
    }
}

async function loadWifiConfig() {
    try {
        const res = await fetchWithAuth(`${API_BASE}/wifi/config`);
        if(!res.ok) throw new Error('加载失败');
        const config = await res.json();
        
        // STA模式配置
        const ssidInput = document.getElementById('wifi-ssid');
        const pwdInput = document.getElementById('wifi-password');
        const dhcpRadio = document.querySelector('input[name="wifi-ip-mode"][value="dhcp"]');
        const staticRadio = document.querySelector('input[name="wifi-ip-mode"][value="static"]');
        const staIpInput = document.getElementById('wifi-sta-ip');
        const staSubnetInput = document.getElementById('wifi-sta-subnet');
        const staGatewayInput = document.getElementById('wifi-sta-gateway');
        const staDnsInput = document.getElementById('wifi-sta-dns');
        
        if(ssidInput) ssidInput.value = config.wifi_ssid || '';
        if(pwdInput) pwdInput.value = '';  // 不显示密码
        
        // 设置IP获取方式单选框
        if(config.sta_use_static_ip) {
            if(staticRadio) staticRadio.checked = true;
        } else {
            if(dhcpRadio) dhcpRadio.checked = true;
        }
        toggleStaticIpFields();
        
        if(staIpInput) staIpInput.value = config.sta_ip || '';
        if(staSubnetInput) staSubnetInput.value = config.sta_subnet || '255.255.255.0';
        if(staGatewayInput) staGatewayInput.value = config.sta_gateway || '';
        if(staDnsInput) staDnsInput.value = config.sta_dns || '8.8.8.8';
        
        // AP模式配置
        const apSsidInput = document.getElementById('wifi-ap-ssid');
        const apPwdInput = document.getElementById('wifi-ap-password');
        const apIpInput = document.getElementById('wifi-ap-ip');
        
        if(apSsidInput) apSsidInput.value = config.ap_ssid || '';
        if(apPwdInput) apPwdInput.value = '';  // 不显示密码
        if(apIpInput) apIpInput.value = config.ap_ip || '192.168.1.68';
        
    } catch(e) {
        console.error(e);
    }
}

async function saveWifiConfig() {
    const staticRadio = document.querySelector('input[name="wifi-ip-mode"][value="static"]');
    const isStaticIp = staticRadio?.checked || false;
    
    const config = {
        wifi_ssid: document.getElementById('wifi-ssid')?.value?.trim() || '',
        sta_use_static_ip: isStaticIp,
        sta_ip: document.getElementById('wifi-sta-ip')?.value?.trim() || '',
        sta_subnet: document.getElementById('wifi-sta-subnet')?.value?.trim() || '255.255.255.0',
        sta_gateway: document.getElementById('wifi-sta-gateway')?.value?.trim() || '',
        sta_dns: document.getElementById('wifi-sta-dns')?.value?.trim() || '8.8.8.8',
        ap_ssid: document.getElementById('wifi-ap-ssid')?.value?.trim() || '',
        ap_ip: document.getElementById('wifi-ap-ip')?.value?.trim() || '192.168.1.68'
    };
    
    // 只有输入了密码才发送
    const wifiPwd = document.getElementById('wifi-password')?.value || '';
    if(wifiPwd) config.wifi_password = wifiPwd;
    
    const apPwd = document.getElementById('wifi-ap-password')?.value || '';
    if(apPwd) config.ap_password = apPwd;
    
    // 构建动态验证规则
    const wifiRules = {
        wifi_ssid: VALIDATION_RULES.wifi_ssid
    };
    // WiFi密码：非空时验证长度
    if(wifiPwd) {
        wifiRules.wifi_password = VALIDATION_RULES.wifi_password;
    }
    // AP SSID
    if(config.ap_ssid) {
        wifiRules.ap_ssid = VALIDATION_RULES.ap_ssid;
    }
    // AP密码：非空时验证长度
    if(apPwd) {
        wifiRules.ap_password = VALIDATION_RULES.ap_password;
    }
    // 静态IP模式下：IP/子网/网关/DNS 必填且格式校验
    if(isStaticIp) {
        wifiRules.sta_ip = { required: true, type: 'ipv4', errorMsg: { required: '静态IP地址为必填项', format: '请输入有效的IP地址（如192.168.1.100）' } };
        wifiRules.sta_subnet = { required: true, type: 'ipv4', errorMsg: { required: '子网掩码为必填项', format: '请输入有效的子网掩码（如255.255.255.0）' } };
        wifiRules.sta_gateway = { required: true, type: 'ipv4', errorMsg: { required: '网关地址为必填项', format: '请输入有效的网关地址（如192.168.1.1）' } };
        wifiRules.sta_dns = { required: true, type: 'ipv4', errorMsg: { required: 'DNS服务器为必填项', format: '请输入有效的DNS地址（如8.8.8.8）' } };
    }
    // AP IP：非空时格式校验
    if(config.ap_ip) {
        wifiRules.ap_ip = { required: false, type: 'ipv4', errorMsg: { format: '请输入有效的AP模式IP地址（如192.168.1.68）' } };
    }
    
    // 构建验证数据
    const formData = {
        wifi_ssid: config.wifi_ssid,
        wifi_password: wifiPwd,
        ap_ssid: config.ap_ssid,
        ap_password: apPwd,
        sta_ip: config.sta_ip,
        sta_subnet: config.sta_subnet,
        sta_gateway: config.sta_gateway,
        sta_dns: config.sta_dns,
        ap_ip: config.ap_ip
    };
    
    // 执行验证
    const validation = validateForm(formData, wifiRules);
    if(!validation.valid) {
        alert(validation.firstError);
        return;
    }
    
    try {
        const res = await fetch(`${API_BASE}/wifi/config`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(withToken(config))
        });
        
        if(res.ok) {
            alert('WiFi配置已保存，重启设备后生效');
        } else {
            const err = await res.json();
            alert('保存失败: ' + (err.error || '权限不足'));
        }
    } catch(e) {
        console.error(e);
        alert('网络错误');
    }
}

// --- 数据备份 ---
// 备份表名称映射（用于显示）
const BACKUP_TABLE_NAMES = {
    'members': '成员数据',
    'poems': '诗词作品',
    'activities': '活动记录',
    'tasks': '事务任务',
    'finance': '财务记录',
    'points_logs': '积分日志',
    'login_logs': '登录日志',
    'settings': '系统设置',
    'wifi_config': 'WiFi配置',
    'system_config': '系统配置'
};

// 备份进度条控制
function showBackupProgress(title) {
    document.getElementById('backup-progress-title').innerText = title;
    document.getElementById('backup-progress-status').innerText = '准备中...';
    document.getElementById('backup-progress-percent').innerText = '0%';
    document.getElementById('backup-progress-bar').style.width = '0%';
    document.getElementById('backup-progress-detail').innerText = '正在初始化...';
    document.getElementById('modal-backup-progress').classList.remove('hidden');
}

function updateBackupProgress(percent, status, detail) {
    document.getElementById('backup-progress-percent').innerText = `${percent}%`;
    document.getElementById('backup-progress-bar').style.width = `${percent}%`;
    if (status) document.getElementById('backup-progress-status').innerText = status;
    if (detail) document.getElementById('backup-progress-detail').innerText = detail;
}

function hideBackupProgress() {
    document.getElementById('modal-backup-progress').classList.add('hidden');
}

async function exportBackup() {
    // 检查登录状态
    if(!getAuthToken()) {
        alert('操作失败：登录已过期，请重新登录后再试');
        return;
    }
    
    // 获取导出按钮并禁用，防止重复提交
    const exportBtn = document.querySelector('button[onclick*="exportBackup"]');
    const importBtn = document.querySelector('button[onclick*="backup-file-input"]');
    if (exportBtn) {
        exportBtn.disabled = true;
        exportBtn.innerText = '导出中...';
    }
    if (importBtn) importBtn.disabled = true;
    
    // 定义要导出的表（按顺序）
    const tables = ['members', 'poems', 'activities', 'tasks', 'finance', 'points_logs', 'login_logs', 'settings', 'wifi_config', 'system_config'];
    const totalTables = tables.length;
    
    showBackupProgress('正在导出数据...');
    
    try {
        const backupData = {
            version: "1.0",
            export_time: new Date().toISOString(),
            data: {}
        };
        
        for (let i = 0; i < tables.length; i++) {
            const table = tables[i];
            const tableName = BACKUP_TABLE_NAMES[table] || table;
            
            try {
                // 分批导出：循环请求直到所有数据获取完毕
                let allData = [];
                let page = 1;
                let hasMore = true;
                let total = 0;
                
                while (hasMore) {
                    const basePercent = (i / totalTables) * 100;
                    updateBackupProgress(
                        Math.round(basePercent), 
                        `导出 ${tableName}`, 
                        total > 0 ? `已获取 ${allData.length}/${total} 条...` : `正在获取第 ${page} 批...`
                    );
                    
                    const res = await fetchWithAuth(`${API_BASE}/backup/export-table?name=${table}&page=${page}&limit=100`);
                    if (!res.ok) {
                        const err = await res.json().catch(() => ({}));
                        throw new Error(err.error || `导出 ${tableName} 失败`);
                    }
                    const result = await res.json();
                    
                    // 处理数据
                    if (Array.isArray(result.data)) {
                        allData = allData.concat(result.data);
                    } else {
                        // 配置类数据（非数组），直接使用
                        allData = result.data;
                        hasMore = false;
                        break;
                    }
                    
                    total = result.total || 0;
                    hasMore = result.hasMore || false;
                    page++;
                    
                    // 短暂延迟，让ESP32有时间处理
                    if (hasMore) {
                        await new Promise(r => setTimeout(r, 50));
                    }
                }
                
                backupData.data[table] = allData;
                
                const percent = Math.round(((i + 1) / totalTables) * 100);
                updateBackupProgress(percent, `导出 ${tableName}`, Array.isArray(allData) ? `完成，共 ${allData.length} 条` : '完成');
                
            } catch (tableErr) {
                console.warn(`导出 ${table} 失败:`, tableErr);
                // 继续处理其他表，但记录错误
                backupData.data[table] = [];
            }
            
            // 表与表之间短暂延迟
            await new Promise(r => setTimeout(r, 100));
        }
        
        updateBackupProgress(100, '正在生成文件', '准备下载...');
        
        // 生成下载文件
        const now = new Date();
        const timestamp = now.getFullYear() + 
            String(now.getMonth() + 1).padStart(2, '0') + 
            String(now.getDate()).padStart(2, '0') + '_' +
            String(now.getHours()).padStart(2, '0') + 
            String(now.getMinutes()).padStart(2, '0');
        const filename = `backup_${timestamp}.json`;
        
        const blob = new Blob([JSON.stringify(backupData, null, 2)], {type: 'application/json'});
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        URL.revokeObjectURL(url);
        document.body.removeChild(a);
        
        hideBackupProgress();
        alert('备份导出成功！');
    } catch(e) {
        hideBackupProgress();
        console.error(e);
        alert('导出失败: ' + e.message);
    } finally {
        if (exportBtn) {
            exportBtn.disabled = false;
            exportBtn.innerText = '下载备份文件';
        }
        if (importBtn) importBtn.disabled = false;
    }
}

async function importBackup(event) {
    const file = event.target.files[0];
    if(!file) return;
    
    // 检查登录状态
    if(!getAuthToken()) {
        alert('操作失败：登录已过期，请重新登录后再试');
        document.getElementById('backup-file-input').value = '';
        return;
    }
    
    if(!confirm('导入数据将覆盖现有所有数据，此操作不可逆！\n\n确定要继续吗？')) {
        document.getElementById('backup-file-input').value = '';
        return;
    }
    
    // 获取备份按钮并禁用，防止重复操作
    const exportBtn = document.querySelector('button[onclick*="exportBackup"]');
    const importBtn = document.querySelector('button[onclick*="backup-file-input"]');
    if (exportBtn) exportBtn.disabled = true;
    if (importBtn) {
        importBtn.disabled = true;
        importBtn.innerText = '导入中...';
    }
    
    showBackupProgress('正在导入数据...');
    
    try {
        updateBackupProgress(5, '读取文件', '正在解析备份文件...');
        
        const text = await file.text();
        let backup;
        try {
            backup = JSON.parse(text);
        } catch(parseErr) {
            throw new Error('文件格式无效，请选择正确的备份文件');
        }
        
        if(!backup.version || !backup.data) {
            throw new Error('备份文件结构不完整');
        }
        
        updateBackupProgress(10, '验证完成', '开始分表导入...');
        
        // 定义要导入的表（按顺序，成员表优先）
        const tables = ['members', 'poems', 'activities', 'tasks', 'finance', 'points_logs', 'login_logs', 'settings', 'wifi_config', 'system_config'];
        const availableTables = tables.filter(t => backup.data[t] !== undefined);
        const totalTables = availableTables.length;
        
        if (totalTables === 0) {
            throw new Error('备份文件中没有可导入的数据');
        }
        
        let successCount = 0;
        let errorTables = [];
        
        for (let i = 0; i < availableTables.length; i++) {
            const table = availableTables[i];
            const tableName = BACKUP_TABLE_NAMES[table] || table;
            const percent = Math.round(10 + ((i + 1) / totalTables) * 85);
            
            updateBackupProgress(percent, `导入 ${tableName}`, `正在处理第 ${i + 1}/${totalTables} 项...`);
            
            try {
                const tableData = backup.data[table];
                
                // 对于大型数组数据，分批发送（每批最多100条记录）
                if (Array.isArray(tableData) && tableData.length > 100) {
                    const batchSize = 100;
                    const totalBatches = Math.ceil(tableData.length / batchSize);
                    
                    for (let batch = 0; batch < totalBatches; batch++) {
                        const start = batch * batchSize;
                        const end = Math.min(start + batchSize, tableData.length);
                        const batchData = tableData.slice(start, end);
                        
                        updateBackupProgress(percent, `导入 ${tableName}`, `批次 ${batch + 1}/${totalBatches} (${start + 1}-${end}/${tableData.length})`);
                        
                        const res = await fetchWithAuth(`${API_BASE}/backup/import-table?name=${table}&mode=${batch === 0 ? 'overwrite' : 'append'}`, {
                            method: 'POST',
                            body: JSON.stringify({ data: batchData })
                        });
                        
                        if (!res.ok) {
                            const errText = await res.text();
                            console.error(`导入 ${table} 批次${batch + 1} HTTP错误: 状态=${res.status}, 响应=${errText}`);
                            let errMsg = `HTTP ${res.status}`;
                            try {
                                const errJson = JSON.parse(errText);
                                errMsg = errJson.error || errMsg;
                            } catch(e) {}
                            throw new Error(errMsg);
                        }
                        
                        // 批次间延迟，让ESP32释放内存
                        await new Promise(r => setTimeout(r, 300));
                    }
                } else {
                    // 小数据直接发送
                    const res = await fetchWithAuth(`${API_BASE}/backup/import-table?name=${table}`, {
                        method: 'POST',
                        body: JSON.stringify({ data: tableData })
                    });
                    
                    if (!res.ok) {
                        const errText = await res.text();
                        console.error(`导入 ${table} HTTP错误: 状态=${res.status}, 响应=${errText}`);
                        let errMsg = `HTTP ${res.status}`;
                        try {
                            const errJson = JSON.parse(errText);
                            errMsg = errJson.error || errMsg;
                        } catch(e) {}
                        throw new Error(errMsg);
                    }
                }
                
                successCount++;
            } catch (tableErr) {
                console.error(`导入 ${table} 失败:`, tableErr);
                errorTables.push(tableName);
            }
            
            // 延迟500ms，让ESP32有时间处理和释放内存
            await new Promise(r => setTimeout(r, 500));
        }
        
        updateBackupProgress(100, '导入完成', '正在刷新页面...');
        
        hideBackupProgress();
        
        if (errorTables.length > 0) {
            alert(`数据导入完成，但以下项目导入失败：\n${errorTables.join('、')}\n\n成功导入 ${successCount}/${totalTables} 项\n\n页面将刷新`);
        } else {
            alert(`数据恢复成功！共导入 ${successCount} 项数据\n\n页面将刷新`);
        }
        
        location.reload();
    } catch(e) {
        hideBackupProgress();
        console.error(e);
        alert('导入失败: ' + e.message);
        // 恢复按钮状态
        if (exportBtn) exportBtn.disabled = false;
        if (importBtn) {
            importBtn.disabled = false;
            importBtn.innerText = '选择备份文件';
        }
    }
    
    document.getElementById('backup-file-input').value = '';
}

// ============================================================================
// 聊天室功能
// ============================================================================

// 聊天室状态变量
let _chatUserId = null;         // 当前用户在聊天室的ID
let _chatUserName = null;       // 当前用户在聊天室的名称
let _chatIsGuest = false;       // 是否为游客
let _chatLastMsgId = 0;         // 最后一条消息ID（用于增量获取）
let _chatPollingTimer = null;   // 轮询定时器
let _chatJoined = false;        // 是否已加入聊天室
let _chatInputBound = false;    // 输入框事件是否已绑定（防止重复绑定）
let _chatSending = false;       // 是否正在发送消息（防止重复提交）
let _homeChatTimer = null;      // 首页聊天刷新定时器
let _homeChatLastMsgId = 0;     // 首页聊天最后消息ID
let _homeChatMessages = [];     // 首页聊天消息缓存

const CHAT_MAX_CHARS = 1024;    // 最大字符数
const CHAT_POLL_INTERVAL = 10000; // 轮询间隔（10秒）
const HOME_CHAT_INTERVAL = 10000; // 首页聊天刷新间隔（10秒）

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

/**
 * 初始化聊天室
 */
async function initChat() {
    // 绑定输入框事件（仅首次绑定，防止重复）
    if (!_chatInputBound) {
        const input = document.getElementById('chat-input');
        if (input) {
            input.addEventListener('input', updateChatCharCount);
            input.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    sendChatMessage();
                }
            });
            _chatInputBound = true;
        }
    }
    
    // 加入聊天室
    await joinChat();
    
    // 开始轮询
    startChatPolling();
    
    // 加载初始数据
    await loadChatMessages();
    await loadChatUsers();
    await loadChatStatus();
}

/**
 * 加入聊天室（游客自动分配昵称）
 */
async function joinChat() {
    if (_chatJoined) return true;
    
    try {
        const res = await fetchWithAuth(`${API_BASE}/chat/join`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({})
        });
        
        if (res.ok) {
            const data = await res.json();
            _chatUserId = data.user_id;
            _chatUserName = data.user_name;
            _chatIsGuest = data.is_guest;
            _chatJoined = true;
            return true;
        } else {
            const err = await res.json().catch(() => ({}));
            if (err.error) {
                alert(err.error);
            }
            return false;
        }
    } catch(e) {
        console.error('加入聊天室失败:', e);
        return false;
    }
}

/**
 * 离开聊天室
 */
async function leaveChat() {
    if (!_chatJoined) return;
    
    try {
        await fetchWithAuth(`${API_BASE}/chat/leave`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ user_id: _chatUserId })
        });
    } catch(e) {
        console.error('离开聊天室失败:', e);
    }
    
    _chatJoined = false;
    _chatUserId = null;
    _chatUserName = null;
    stopChatPolling();
}

/**
 * 开始消息轮询
 */
function startChatPolling() {
    if (_chatPollingTimer) return;
    
    _chatPollingTimer = setInterval(async () => {
        await loadChatMessages(true);
        await loadChatUsers();
        await loadChatStatus();
    }, CHAT_POLL_INTERVAL);
}

/**
 * 停止消息轮询
 */
function stopChatPolling() {
    if (_chatPollingTimer) {
        clearInterval(_chatPollingTimer);
        _chatPollingTimer = null;
    }
}

/**
 * 加载聊天消息
 */
async function loadChatMessages(incremental = false) {
    try {
        const afterId = incremental ? _chatLastMsgId : 0;
        const res = await fetch(`${API_BASE}/chat/messages?after=${afterId}`);
        const messages = await res.json();
        
        if (!incremental) {
            // 全量加载
            renderChatMessages(messages);
        } else if (messages.length > 0) {
            // 增量追加
            appendChatMessages(messages);
        } else if (_chatLastMsgId > 0) {
            // 增量返回空且有旧ID，可能服务器已重启，做一次全量检测
            const checkRes = await fetch(`${API_BASE}/chat/messages?after=0`);
            const allMessages = await checkRes.json();
            if (allMessages.length === 0 || (allMessages.length > 0 && allMessages[allMessages.length - 1].id < _chatLastMsgId)) {
                // 服务器消息已重置，全量重载
                _chatLastMsgId = 0;
                renderChatMessages(allMessages);
                if (allMessages.length > 0) {
                    _chatLastMsgId = Math.max(...allMessages.map(m => m.id));
                }
                return;
            }
        }
        
        // 更新最后消息ID
        if (messages.length > 0) {
            _chatLastMsgId = Math.max(...messages.map(m => m.id));
        }
    } catch(e) {
        console.error('加载聊天消息失败:', e);
    }
}

/**
 * 渲染聊天消息（全量）
 */
function renderChatMessages(messages) {
    const container = document.getElementById('chat-messages');
    if (!container) return;
    
    if (messages.length === 0) {
        container.innerHTML = '<div class="empty-hint">暂无消息，快来说点什么吧</div>';
        return;
    }
    
    container.innerHTML = messages.map(m => renderSingleMessage(m)).join('');
    container.scrollTop = container.scrollHeight;
}

/**
 * 追加聊天消息（增量）
 */
function appendChatMessages(messages) {
    const container = document.getElementById('chat-messages');
    if (!container) return;
    
    // 移除空状态提示
    const emptyHint = container.querySelector('.empty-hint');
    if (emptyHint) emptyHint.remove();
    
    messages.forEach(m => {
        container.insertAdjacentHTML('beforeend', renderSingleMessage(m));
    });
    
    container.scrollTop = container.scrollHeight;
}

/**
 * 渲染单条消息
 */
function renderSingleMessage(msg) {
    const isSelf = msg.user_id === _chatUserId;
    const isGuest = msg.is_guest;
    const timeStr = formatMessageTime(msg.timestamp);
    
    let classes = 'chat-message';
    if (isSelf) classes += ' is-self';
    if (isGuest) classes += ' is-guest';
    
    return `
        <div class="${classes}">
            <div class="chat-message-header">
                <span class="chat-message-user ${isGuest ? 'guest' : ''}">${escapeHtml(msg.user_name)}</span>
                <span class="chat-message-time">${timeStr}</span>
            </div>
            <div class="chat-message-content">${escapeHtml(msg.content)}</div>
        </div>
    `;
}

/**
 * 格式化消息时间
 */
function formatMessageTime(timestamp) {
    const date = new Date(timestamp * 1000);
    const now = new Date();
    const hours = date.getHours().toString().padStart(2, '0');
    const mins = date.getMinutes().toString().padStart(2, '0');
    
    // 如果是今天，只显示时间
    if (date.toDateString() === now.toDateString()) {
        return `${hours}:${mins}`;
    }
    
    // 否则显示日期+时间
    const month = (date.getMonth() + 1).toString().padStart(2, '0');
    const day = date.getDate().toString().padStart(2, '0');
    return `${month}-${day} ${hours}:${mins}`;
}

/**
 * HTML转义
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Markdown 渲染函数
 * 使用 marked.js 将 Markdown 文本转换为 HTML
 * 集成 DOMPurify 进行 XSS 防护
 */
function renderMarkdown(text) {
    if (!text) return '';
    
    // 配置 marked
    marked.setOptions({
        gfm: true,        // GitHub Flavored Markdown（表格、删除线、任务列表）
        breaks: true,     // 换行转 <br>（适合诗歌格式）
        pedantic: false,
        async: false
    });
    
    try {
        let html = marked.parse(text);
        // 后处理：将空段落转为带空行效果的 <br>
        // 保留连续空行效果：将 <p><br></p> 或 <p></p> 替换为带高度的空行
        html = html.replace(/<p>\s*<br\s*\/?>\s*<\/p>/gi, '<p class="empty-line">&nbsp;</p>');
        
        // XSS 防护：使用 DOMPurify 白名单净化 HTML
        if (typeof DOMPurify !== 'undefined') {
            html = DOMPurify.sanitize(html, {
                ALLOWED_TAGS: [
                    'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
                    'p', 'br', 'hr', 'blockquote',
                    'ul', 'ol', 'li',
                    'strong', 'em', 'del', 'code', 'pre',
                    'a', 'img',
                    'table', 'thead', 'tbody', 'tr', 'th', 'td',
                    'input', 'span', 'div'
                ],
                ALLOWED_ATTR: [
                    'href', 'src', 'alt', 'title', 'class',
                    'type', 'checked', 'disabled'
                ],
                ALLOW_DATA_ATTR: false,
                ALLOW_UNKNOWN_PROTOCOLS: false
            });
        }
        
        return html;
    } catch (e) {
        console.error('Markdown parse error:', e);
        return escapeHtml(text);  // 降级为纯文本
    }
}

/**
 * 加载在线用户列表
 */
async function loadChatUsers() {
    try {
        const res = await fetch(`${API_BASE}/chat/users`);
        const users = await res.json();
        
        renderChatUsers(users);
        
        // 更新在线人数
        const countEl = document.getElementById('chat-online-count');
        if (countEl) countEl.textContent = `(${users.length})`;
        
        const homeCountEl = document.getElementById('home-chat-user-count');
        if (homeCountEl) homeCountEl.textContent = `(${users.length}人在线)`;
    } catch(e) {
        console.error('加载在线用户失败:', e);
    }
}

/**
 * 渲染在线用户列表
 */
function renderChatUsers(users) {
    const container = document.getElementById('chat-user-list');
    if (!container) return;
    
    if (users.length === 0) {
        container.innerHTML = '<div class="empty-hint">暂无用户</div>';
        return;
    }
    
    container.innerHTML = users.map(u => {
        const initial = u.name.charAt(0);
        const isGuest = u.is_guest;
        return `
            <div class="chat-user-item">
                <div class="chat-user-avatar ${isGuest ? 'guest' : ''}">${escapeHtml(initial)}</div>
                <span class="chat-user-name ${isGuest ? 'guest' : ''}">${escapeHtml(u.name)}</span>
            </div>
        `;
    }).join('');
}

/**
 * 加载聊天室状态
 */
async function loadChatStatus() {
    try {
        const res = await fetch(`${API_BASE}/chat/status`);
        const status = await res.json();
        
        const memoryEl = document.getElementById('chat-memory-usage');
        const msgCountEl = document.getElementById('chat-msg-count');
        const guestSlotsEl = document.getElementById('chat-guest-slots');
        const maxUsersEl = document.getElementById('chat-max-users');
        
        if (memoryEl) {
            const usedKB = (status.memory_used / 1024).toFixed(1);
            const limitKB = (status.memory_limit / 1024).toFixed(0);
            memoryEl.textContent = `${usedKB}KB / ${limitKB}KB`;
        }
        if (msgCountEl) msgCountEl.textContent = status.message_count;
        if (guestSlotsEl) guestSlotsEl.textContent = `${status.guest_count}/${status.guest_max}人`;
        if (maxUsersEl) maxUsersEl.textContent = `${status.user_count}/${status.max_users}人`;
    } catch(e) {
        console.error('加载聊天室状态失败:', e);
    }
}

/**
 * 更新字符计数
 */
function updateChatCharCount() {
    const input = document.getElementById('chat-input');
    const countEl = document.getElementById('chat-char-count');
    if (!input || !countEl) return;
    
    const len = input.value.length;
    countEl.textContent = `${len}/${CHAT_MAX_CHARS}`;
    
    countEl.classList.remove('warning', 'danger');
    if (len >= CHAT_MAX_CHARS) {
        countEl.classList.add('danger');
    } else if (len >= CHAT_MAX_CHARS * 0.8) {
        countEl.classList.add('warning');
    }
}

/**
 * 更新聊天室发送按钮状态
 */
function updateChatSendBtn() {
    const input = document.getElementById('chat-input');
    const btn = document.getElementById('chat-send-btn');
    if (input && btn) {
        btn.disabled = !input.value.trim();
    }
    updateChatCharCount();
}

/**
 * 发送聊天消息
 */
async function sendChatMessage() {
    const input = document.getElementById('chat-input');
    const sendBtn = document.getElementById('chat-send-btn');
    if (!input) return;
    
    const content = input.value.trim();
    if (!content) return;
    
    // 防止重复提交
    if (_chatSending) return;
    _chatSending = true;
    
    if (content.length > CHAT_MAX_CHARS) {
        alert(`消息过长，最多${CHAT_MAX_CHARS}个字符`);
        _chatSending = false;
        return;
    }
    
    // 立即禁用按钮防止重复发送
    if (sendBtn) sendBtn.disabled = true;
    
    // 如果未加入聊天室，先加入
    if (!_chatJoined) {
        await joinChat();
        if (!_chatJoined) {
            updateChatSendBtn();
            return;
        }
    }
    
    try {
        const res = await fetchWithAuth(`${API_BASE}/chat/send`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                content: content,
                user_id: _chatUserId
            })
        });
        
        if (res.ok) {
            const msg = await res.json();
            // 清空输入框
            input.value = '';
            // 追加消息
            appendChatMessages([msg]);
            _chatLastMsgId = msg.id;
        } else {
            const err = await res.json().catch(() => ({}));
            alert(err.error || '发送失败');
        }
    } catch(e) {
        console.error('发送消息失败:', e);
        alert('发送失败，请重试');
    }
    // 更新按钮状态（清空后会自动禁用）
    _chatSending = false;
    updateChatSendBtn();
}

/**
 * 更新首页聊天预览
 */
function updateHomeChatPreview(messages) {
    const container = document.getElementById('home-chat-preview');
    if (!container) return;
    
    // 显示最近10条消息
    const recent = messages.slice(-10);
    if (recent.length === 0) {
        container.innerHTML = '<div class="empty-hint">暂无消息，快来说点什么吧</div>';
        return;
    }
    
    container.innerHTML = recent.map(m => {
        // 判断是否是当前用户发送的消息：优先使用_chatUserId，回退到currentUser.id
        const isSelf = m.user_id === _chatUserId || (currentUser && m.user_id === currentUser.id);
        const timeStr = formatMessageTime(m.timestamp);
        let classes = 'chat-message';
        if (isSelf) classes += ' is-self';
        if (m.is_guest) classes += ' is-guest';
        return `
        <div class="${classes}">
            <div class="chat-message-header">
                <span class="chat-message-user ${m.is_guest ? 'guest' : ''}">${m.user_name}</span>
                <span class="chat-message-time">${timeStr}</span>
            </div>
            <div class="chat-message-content">${escapeHtml(m.content)}</div>
        </div>
    `;
    }).join('');
    
    // 滚动到底部
    container.scrollTop = container.scrollHeight;
}

/**
 * 加载首页聊天预览（增量加载机制）
 */
async function loadHomeChatPreview() {
    try {
        // 增量加载消息
        const msgRes = await fetch(`${API_BASE}/chat/messages?after=${_homeChatLastMsgId}`);
        const newMessages = await msgRes.json();
        
        if (newMessages.length > 0) {
            // 追加新消息到缓存
            _homeChatMessages = _homeChatMessages.concat(newMessages);
            // 只保留最近50条消息避免内存占用
            if (_homeChatMessages.length > 50) {
                _homeChatMessages = _homeChatMessages.slice(-50);
            }
            _homeChatLastMsgId = Math.max(...newMessages.map(m => m.id));
            updateHomeChatPreview(_homeChatMessages);
        } else if (_homeChatLastMsgId > 0) {
            // 增量返回空且有旧ID，检测服务器是否重启
            const checkRes = await fetch(`${API_BASE}/chat/messages?after=0`);
            const allMessages = await checkRes.json();
            if (allMessages.length === 0 || (allMessages.length > 0 && allMessages[allMessages.length - 1].id < _homeChatLastMsgId)) {
                // 服务器消息已重置，全量重载
                _homeChatLastMsgId = 0;
                _homeChatMessages = allMessages;
                if (allMessages.length > 0) {
                    _homeChatLastMsgId = Math.max(...allMessages.map(m => m.id));
                }
                updateHomeChatPreview(_homeChatMessages);
            }
        } else if (_homeChatMessages.length === 0) {
            // 首次加载且无消息
            updateHomeChatPreview([]);
        }
        
        // 加载在线用户数
        const userRes = await fetch(`${API_BASE}/chat/users`);
        const users = await userRes.json();
        const homeCountEl = document.getElementById('home-chat-user-count');
        if (homeCountEl) homeCountEl.textContent = `(${users.length}人在线)`;
    } catch(e) {
        console.error('加载首页聊天预览失败:', e);
    }
}

/**
 * 启动首页聊天定时刷新（每分钟）
 */
function startHomeChatPolling() {
    if (_homeChatTimer) return;
    _homeChatTimer = setInterval(() => {
        loadHomeChatPreview();
    }, HOME_CHAT_INTERVAL);
}

/**
 * 停止首页聊天定时刷新
 */
function stopHomeChatPolling() {
    if (_homeChatTimer) {
        clearInterval(_homeChatTimer);
        _homeChatTimer = null;
    }
}

/**
 * 检查聊天功能是否启用，并控制首页聊天区域显示
 */
async function checkChatEnabledAndLoad() {
    try {
        const res = await fetch(`${API_BASE}/settings/system`);
        if (res.ok) {
            const data = await res.json();
            const chatEnabled = data.chat_enabled !== false;
            
            // 控制首页聊天卡片显示（使用classList保留CSS原有布局）
            const homeChatCard = document.querySelector('.home-chat-card');
            if (homeChatCard) {
                homeChatCard.classList.toggle('hidden', !chatEnabled);
            }
            
            // 控制导航栏摆龙门阵链接显示
            const chatNavLinks = document.querySelectorAll('nav a[onclick*="showSection(\'chat\')"]');
            chatNavLinks.forEach(link => {
                link.classList.toggle('hidden', !chatEnabled);
            });
            
            // 只有在启用时才加载聊天预览
            if (chatEnabled) {
                loadHomeChatPreview();
                startHomeChatPolling();
            } else {
                stopHomeChatPolling();
            }
        }
    } catch(e) {
        console.error('检查聊天功能状态失败:', e);
        // 失败时默认显示聊天功能
        loadHomeChatPreview();
        startHomeChatPolling();
    }
}

/**
 * 更新首页聊天发送按钮状态
 */
function updateHomeChatSendBtn() {
    const input = document.getElementById('home-chat-input');
    const btn = document.getElementById('home-chat-send-btn');
    if (input && btn) {
        btn.disabled = !input.value.trim();
    }
}

/**
 * 从首页发送聊天消息
 */
async function sendHomeChatMessage() {
    const input = document.getElementById('home-chat-input');
    const sendBtn = document.getElementById('home-chat-send-btn');
    if (!input) return;
    
    const content = input.value.trim();
    if (!content) return;
    
    // 防止重复提交
    if (_chatSending) return;
    _chatSending = true;
    
    if (content.length > CHAT_MAX_CHARS) {
        alert(`消息过长，最多${CHAT_MAX_CHARS}个字符`);
        _chatSending = false;
        return;
    }
    
    // 立即禁用按钮防止重复发送
    if (sendBtn) sendBtn.disabled = true;
    
    // 如果未加入聊天室，先加入
    if (!_chatJoined) {
        const joined = await joinChat();
        if (!joined) {
            updateHomeChatSendBtn();
            return;
        }
    }
    
    try {
        const res = await fetchWithAuth(`${API_BASE}/chat/send`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                content: content,
                user_id: _chatUserId
            })
        });
        
        if (res.ok) {
            const msg = await res.json();
            // 清空输入框
            input.value = '';
            // 刷新首页预览
            await loadHomeChatPreview();
        } else {
            const err = await res.json().catch(() => ({}));
            alert(err.error || '发送失败');
        }
    } catch(e) {
        console.error('发送消息失败:', e);
        alert('发送失败，请重试');
    }
    // 更新按钮状态（清空后会自动禁用）
    _chatSending = false;
    updateHomeChatSendBtn();
}
