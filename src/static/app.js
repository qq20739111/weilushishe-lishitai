// Constants
const API_BASE = '/api';
let currentUser = null;
let _customFields = [];
let _systemSettings = { points_name: '围炉值', password_salt: 'weilu2018' };

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

// Login Logic
function checkLogin() {
    const user = localStorage.getItem('user');
    if (user) {
        currentUser = JSON.parse(user);
        document.getElementById('login-section').style.display = 'none';
        document.getElementById('main-app').style.display = 'block';
        fetchCustomFields(); // Load custom fields schema
        fetchSystemSettings(); // Load system settings
        updateNavUser(); // Update nav user display
        showSection('home');
    } else {
        document.getElementById('login-section').style.display = 'flex';
        document.getElementById('main-app').style.display = 'none';
    }
}

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
            localStorage.setItem('user', JSON.stringify(user));
            checkLogin();
        } else {
            alert('登录失败: 账号或密码错误');
        }
    } catch (e) {
        alert('登录出错: ' + e.message);
    }
}

function logout() {
    localStorage.removeItem('user');
    currentUser = null;
    checkLogin();
}

// --- 修改密码 ---
function openChangePasswordModal() {
    document.getElementById('cp-old-password').value = '';
    document.getElementById('cp-new-password').value = '';
    document.getElementById('cp-confirm-password').value = '';
    toggleModal('modal-change-password');
}

async function submitChangePassword() {
    const oldPwd = document.getElementById('cp-old-password').value;
    const newPwd = document.getElementById('cp-new-password').value;
    const confirmPwd = document.getElementById('cp-confirm-password').value;
    
    if (!oldPwd || !newPwd || !confirmPwd) {
        alert('请填写所有密码字段');
        return;
    }
    
    if (newPwd !== confirmPwd) {
        alert('两次输入的新密码不一致');
        return;
    }
    
    if (newPwd.length < 4) {
        alert('新密码长度至少4位');
        return;
    }
    
    try {
        const res = await fetch(`${API_BASE}/members/change_password`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                id: currentUser.id,
                old_password: oldPwd,
                new_password: newPwd
            })
        });
        
        if (res.ok) {
            alert('密码修改成功');
            toggleModal('modal-change-password');
        } else {
            const data = await res.json();
            alert('修改失败: ' + (data.error || '未知错误'));
        }
    } catch (e) {
        console.error(e);
        alert('网络错误，请重试');
    }
}

// Navigation
let _lastSection = 'home';

function showSection(id) {
    if(!currentUser) return; // Prevent navigation if not logged in
    
    // Track history (except for search results view)
    if (id !== 'search-results-section') {
        _lastSection = id;
    }

    document.querySelectorAll('main > section').forEach(el => el.style.display = 'none');
    document.getElementById(id).style.display = 'block';
    
    // Toggle Search Bar Visibility
    // Only show on: home, activities, poems, tasks
    const searchContainer = document.querySelector('.search-container');
    if (searchContainer) {
        // Keep visible if in search-results-section so user can clear/edit
        const visibleSections = ['home', 'activities', 'poems', 'tasks', 'search-results-section'];
        searchContainer.style.display = visibleSections.includes(id) ? 'block' : 'none';
    }
    
    // Auto-fetch data based on section
    if(id === 'poems') fetchPoems();
    if(id === 'activities') fetchActivities();
    if(id === 'members') fetchMembers();
    if(id === 'finance') fetchFinance();
    if(id === 'tasks') fetchTasks();
    if(id === 'home' || id === 'admin') {
        loadSystemInfo();
        if(id === 'admin') renderAdminSettings();
    }

    // Check permissions
    const btnAddMember = document.getElementById('btn-add-member');
    const btnAddActivity = document.getElementById('btn-add-activity');
    const isManager = currentUser && ['super_admin', 'admin', 'director'].includes(currentUser.role);

    if (btnAddMember) btnAddMember.style.display = isManager ? 'block' : 'none';
    if (btnAddActivity) btnAddActivity.style.display = isManager ? 'block' : 'none';
}

// Modal
function toggleModal(id) {
    const el = document.getElementById(id);
    el.style.display = (el.style.display === 'block') ? 'none' : 'block';
}

let _cachedPoems = [];
let _poemPage = 1;         // Pagination: Current Page
let _poemHasMore = true;   // Pagination: Has next page?
let _showingAllPoems = false;
let _poemSearchTerm = '';
let editingPoemId = null;
let editingPoemIsLocal = false;

// ... existing helper ...

async function fetchPoems(isLoadMore = false) {
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

function showAllPoems() {
    // Deprecated in favor of Load More
    loadMorePoems();
}

function renderPoems() {
    const container = document.getElementById('poem-list');
    const isManager = currentUser && ['super_admin', 'admin', 'director'].includes(currentUser.role);
    
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
        loadMoreBtn.innerText = '加载更多';
        loadMoreBtn.onclick = loadMorePoems;
        loadMoreBtn.style = "display:none; width:100%; padding:10px; background:#eee; border:none; margin-top:10px; cursor:pointer;";
        container.parentElement.appendChild(loadMoreBtn);
    }
    
    if (_poemHasMore) {
        loadMoreBtn.style.display = 'block';
        loadMoreBtn.innerText = '加载更多...';
    } else {
        loadMoreBtn.style.display = 'none';
    }

    // Render
    container.innerHTML = displayList.map(p => {
        const isAuthor = currentUser && (p.author === currentUser.name || p.author === currentUser.alias);
        const canManage = isManager || p.isLocal || isAuthor;
        
        // Generate ID string for function calls
        const idParam = typeof p.id === 'string' ? `'${p.id}'` : p.id;
        const isLocalParam = p.isLocal ? 'true' : 'false';
        
        const displayDate = p.date ? p.date.replace('T', ' ') : '';

        return `
        <div class="card poem-card" style="${p.isLocal ? 'border-left: 4px solid #FFA000;' : ''}">
            <div style="display:flex; justify-content:space-between; align-items:start;">
                <h3>${p.title}</h3>
                ${p.isLocal ? '<span style="background:#FFA000; color:white; padding:2px 6px; border-radius:4px; font-size:0.7em;">草稿 (存储在本地)</span>' : ''}
            </div>
            <div class="poem-body">${p.content}</div>
            <div class="poem-meta" style="align-items:center;">
                <div style="display:flex; align-items:center; flex-wrap:wrap; gap:10px;">
                    <span style="${getPoemTypeStyle(p.type)} padding:2px 8px; border-radius:4px; font-size:0.85em;">${p.type}</span>
                    <span style="color:#555;">${p.author}</span>
                    <span style="color:#999; font-size:0.9em;">${displayDate}</span>
                </div>
                ${ canManage ? `
                    <div style="margin-left:auto;">
                        <button onclick="openPoemModal(_cachedPoems.find(x => x.id == '${p.id}' || x.id == ${p.id}))" style="background:#4CAF50; padding:6px 14px; font-size:0.9em; margin-right:8px;">${p.isLocal ? '编辑' : '修订'}</button>
                        <button onclick="deletePoemWrapper(${idParam}, ${isLocalParam})" style="background:#e74c3c; padding:6px 14px; font-size:0.9em;">删除</button>
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
                <button onclick="saveDraft()" style="background:#FFA000; color:white;">保存草稿</button>
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
            <button onclick="saveDraft()" style="background:#FFA000; color:white;">保存草稿</button>
            <button onclick="publishPoem()">发布到藏诗阁</button>
        `;
    }
    toggleModal('modal-poem');
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

    const poemData = {
        title, type, content,
        author: currentUser.alias || currentUser.name,
        date: date || toLocalISOString(new Date())
    };

    try {
        const res = await fetch(`${API_BASE}/poems`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(poemData)
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
}

async function submitPoemUpdate() {
   // Existing logic for updating server poem
   const title = document.getElementById('p-title').value;
   const content = document.getElementById('p-content').value;
   const type = document.getElementById('p-type').value;
   const date = document.getElementById('p-date').value;
   
   try {
       const res = await fetch(`${API_BASE}/poems/update`, {
           method: 'POST',
           headers: {'Content-Type': 'application/json'},
           body: JSON.stringify({
               id: editingPoemId,
               title, content, type, date
           })
       });
       if(res.ok) {
           alert('更新成功');
           toggleModal('modal-poem');
           fetchPoems();
       } else { alert('更新失败'); }
   } catch(e) { console.error(e); }
}

async function withdrawPoem() {
    if(!confirm('撤回后，该作品将仅保存在您的本地草稿箱中。继续？')) return;
    
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
            body: JSON.stringify({id: editingPoemId})
        });
        
        if(res.ok) {
            alert('已撤回至本地草稿');
            toggleModal('modal-poem');
            fetchPoems();
        } else {
            alert('撤回失败(服务器删除失败)');
        }
    } catch(e) { alert('操作失败: ' + e); }
}

async function deletePoemWrapper(id, isLocal) {
    if(!confirm('确定永久删除这篇作品吗？(无法恢复)')) return;
    
    if (isLocal) {
        await LocalDrafts.delete(id);
        fetchPoems();
    } else {
        try {
            const res = await fetch(`${API_BASE}/poems/delete`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({id: id})
            });
            if(res.ok) fetchPoems();
            else alert('删除失败');
        } catch(e) { console.error(e); }
    }
}

// Data Fetching


let _cachedMembers = [];

function editMemberClick(id) {
    const member = _cachedMembers.find(m => m.id === id);
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

async function fetchMembers() {
    showLoading('member-list');
    
    try {
        const res = await fetch(`${API_BASE}/members`);
        if (!res.ok) throw new Error('Failed to fetch members');
        _cachedMembers = await res.json();
    } catch (e) {
        console.error(e);
        showEmptyState('member-list', '😕', '加载失败，请刷新重试');
        return;
    }

    const container = document.getElementById('member-list');
    const canEdit = ['super_admin', 'admin', 'director'].includes(currentUser?.role);
    const canDelete = currentUser?.role === 'super_admin';
    
    if(_cachedMembers.length === 0) {
        showEmptyState('member-list', '👥', '暂无社员，快来录入第一位社员吧！', '录入社员', 'openMemberModal()');
        return;
    }

    container.innerHTML = _cachedMembers.map(m => `
        <div class="member-card">
            <div class="member-avatar">🤠</div>
            <h4>${m.name}</h4>
            <div class="member-role">
                ${m.alias || ''}
                <br><small>${formatRole(m.role)}</small>
            </div>
            <div style="margin: 8px 0;">
                <span class="points-badge">🪙 ${m.points || 0} ${getPointsName()}</span>
            </div>
            <div style="display:flex; gap:8px; justify-content:center; margin-top:10px;">
                ${canEdit ? `<button class="btn-small" onclick="editMemberClick(${m.id})" style="background:#4CAF50; color:white; padding:4px 8px; border:none; border-radius:4px; cursor:pointer;">编辑</button>` : ''}
                ${canDelete ? `<button class="delete-btn" onclick="deleteMember(${m.id})" style="padding:4px 8px;">移除</button>` : ''}
            </div>
        </div>
    `).join('');
}

let editingMemberId = null;

async function openMemberModal(member = null) {
    if (member) {
        editingMemberId = member.id;
        document.querySelector('#modal-member h3').innerText = '编辑社员资料';
        document.getElementById('m-name').value = member.name;
        document.getElementById('m-alias').value = member.alias || '';
        document.getElementById('m-phone').value = member.phone || '';
        document.getElementById('m-password').value = ''; // 编辑时不显示原密码 
        document.getElementById('m-role').value = member.role || 'member';
        document.getElementById('m-points').value = member.points || 0;
        // Password placeholder note
        document.getElementById('m-password').placeholder = "留空则不修改密码";
    } else {
        editingMemberId = null;
        document.querySelector('#modal-member h3').innerText = '录入新社员';
        document.getElementById('m-name').value = '';
        document.getElementById('m-alias').value = '';
        document.getElementById('m-phone').value = '';
        document.getElementById('m-password').value = '';
        document.getElementById('m-role').value = 'member';
        document.getElementById('m-points').value = '';
        document.getElementById('m-password').placeholder = "初始密码";
        document.getElementById('m-points').placeholder = `初始${getPointsName()} (默认0)`;
    }

    // Render Custom Fields
    const customContainer = document.getElementById('m-custom-fields-container');
    if (customContainer) {
        customContainer.innerHTML = _customFields.map(f => {
            const val = (member && member.custom && member.custom[f.id]) ? member.custom[f.id] : '';
            return `<div style="margin-bottom:8px;">
                        <label style="font-size:0.8em; color:#666;">${f.label}</label>
                        <input type="${f.type || 'text'}" class="custom-field-input" data-id="${f.id}" placeholder="${f.label}" value="${val}" style="width:100%; box-sizing:border-box;">
                    </div>`;
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
        const data = {
            name: document.getElementById('m-name').value,
            alias: document.getElementById('m-alias').value,
            phone: document.getElementById('m-phone').value,
            role: document.getElementById('m-role').value,
            points: parseInt(document.getElementById('m-points').value || 0)
        };
        
        // Collect Custom Fields
        const customData = {};
        document.querySelectorAll('.custom-field-input').forEach(input => {
            customData[input.dataset.id] = input.value;
        });
        data.custom = customData;

        const pwd = document.getElementById('m-password').value;
        if (pwd) data.password = pwd;

        if(!editingMemberId) {
             // Creating new
             if(!data.name || !data.phone || !data.password) {
                alert('姓名、手机号和初始密码必填');
                return;
            }
            data.joined_at = new Date().toISOString().split('T')[0];
            
            const response = await fetch(`${API_BASE}/members`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(data)
            });
            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(errorText);
            }
        } else {
            // Updating
            data.id = editingMemberId;
            const response = await fetch(`${API_BASE}/members/update`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(data)
            });
            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(errorText);
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

async function deleteMember(id) {
    if(!confirm('确定要移除该社员吗？此操作无法撤销。')) return;
    await fetch(`${API_BASE}/members/delete`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({id: id})
    });
    fetchMembers();
}

async function fetchFinance() {
    // 权限控制：只有财务、管理员、超级管理员可以记账
    const addFinanceBtn = document.getElementById('btn-add-finance');
    if(addFinanceBtn && currentUser) {
        const canRecord = ['super_admin', 'admin', 'finance'].includes(currentUser.role);
        addFinanceBtn.style.display = canRecord ? 'inline-block' : 'none';
    }
    
    const res = await fetch(`${API_BASE}/finance`);
    const records = await res.json();
    
    let income = 0, expense = 0;
    records.forEach(r => {
        if(r.type === 'income') income += r.amount;
        else expense += r.amount;
    });
    
    document.getElementById('total-income').innerText = income.toLocaleString();
    document.getElementById('total-expense').innerText = expense.toLocaleString();
    document.getElementById('balance').innerText = (income - expense).toLocaleString();
    
    const tbody = document.getElementById('finance-list');
    tbody.innerHTML = records.map(r => `
        <tr>
            <td>${r.date}</td>
            <td>${r.summary}<br><small>${r.category}</small></td>
            <td class="money ${r.type === 'income' ? 'plus' : 'minus'}">
                ${r.type === 'income' ? '+' : '-'}${r.amount}
            </td>
            <td>${r.handler}</td>
        </tr>
    `).join('');
}

let _cachedTasks = [];
async function fetchTasks() {
    // 动态更新标题
    const titleEl = document.getElementById('tasks-section-title');
    if(titleEl) {
        titleEl.innerText = `事务与${getPointsName()}`;
    }
    
    // 显示/隐藏发布按钮（仅理事以上可见）
    const addTaskBtn = document.getElementById('btn-add-task');
    if(addTaskBtn && currentUser) {
        const canCreate = ['super_admin', 'admin', 'director'].includes(currentUser.role);
        addTaskBtn.style.display = canCreate ? 'inline-block' : 'none';
    }
    
    showLoading('task-list');
    
    try {
        const res = await fetch(`${API_BASE}/tasks`);
        const tasks = await res.json();
        _cachedTasks = tasks;

        const container = document.getElementById('task-list');
        
        if(tasks.length === 0) {
            showEmptyState('task-list', '📋', '暂无待办事务，一切顺利！');
            return;
        }
        
        const pointsName = getPointsName();
        const userName = currentUser ? currentUser.name : '';
        const isManager = currentUser && ['super_admin', 'admin', 'director'].includes(currentUser.role);
        
        container.innerHTML = tasks.map(t => {
            const statusInfo = getTaskStatusInfo(t.status);
            const isCreator = t.creator === userName;
            const isAssignee = t.assignee === userName;
            
            let actionButtons = '';
            
            if(t.status === 'open') {
                // 待领取：所有人可领取
                actionButtons = `<button onclick="claimTask(${t.id})" class="btn-claim">领取任务</button>`;
            } else if(t.status === 'claimed') {
                // 进行中
                if(isAssignee) {
                    // 领取者：可提交或撤销
                    actionButtons = `
                        <button onclick="submitTaskComplete(${t.id})" class="btn-submit">提交完成</button>
                        <button onclick="unclaimTask(${t.id})" class="btn-unclaim" style="margin-left:8px;">撤销领取</button>
                    `;
                } else if(isManager) {
                    // 管理者：可撤销他人领取
                    actionButtons = `<button onclick="unclaimTask(${t.id})" class="btn-unclaim">撤销领取</button>`;
                }
            } else if(t.status === 'submitted' && (isCreator || isManager)) {
                // 待验收：发布者或管理员可审批
                actionButtons = `
                    <button onclick="approveTask(${t.id})" class="btn-approve">通过</button>
                    <button onclick="rejectTask(${t.id})" class="btn-reject">退回</button>
                `;
            }
            
            // 删除按钮
            // 管理员可删除任何状态的任务，发布者只能删除未完成的任务
            let deleteBtn = '';
            if(isManager || (isCreator && t.status !== 'completed')) {
                deleteBtn = `<button onclick="deleteTask(${t.id})" class="btn-delete" style="margin-left:10px;">删除</button>`;
            }
            
            return `
            <div class="card task-item">
                <div>
                    <h4>${t.title} <span class="task-status ${statusInfo.className}">${statusInfo.label}</span></h4>
                    <p>${t.description || ''}</p>
                    <small>
                        奖励: <span class="task-reward">${t.reward}</span> ${pointsName}
                        ${t.creator ? `&nbsp;|&nbsp;发布者: ${t.creator}` : ''}
                        ${t.assignee ? `&nbsp;|&nbsp;领取者: ${t.assignee}` : ''}
                    </small>
                </div>
                <div style="display:flex; align-items:center;">
                    ${actionButtons}
                    ${deleteBtn}
                </div>
            </div>
            `;
        }).join('');
    } catch(e) { 
        console.error(e);
        showEmptyState('task-list', '😕', '加载失败，请刷新重试');
    }
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

function openTaskModal() {
    document.getElementById('task-modal-title').innerText = '发布事务';
    document.getElementById('t-title').value = '';
    document.getElementById('t-description').value = '';
    document.getElementById('t-reward').value = '';
    document.getElementById('t-reward').placeholder = `奖励${getPointsName()}`;
    toggleModal('modal-task');
}

async function submitTask() {
    const title = document.getElementById('t-title').value.trim();
    const description = document.getElementById('t-description').value.trim();
    const reward = parseInt(document.getElementById('t-reward').value) || 0;
    
    if(!title) { alert('请填写事务标题'); return; }
    
    try {
        const res = await fetch(`${API_BASE}/tasks`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                title,
                description,
                reward,
                creator: currentUser.name
            })
        });
        
        if(res.ok) {
            toggleModal('modal-task');
            fetchTasks();
            alert('事务发布成功！');
        } else {
            alert('发布失败');
        }
    } catch(e) {
        console.error(e);
        alert('网络错误');
    }
}

async function claimTask(taskId) {
    if(!confirm('确认领取此任务？')) return;
    
    try {
        const res = await fetch(`${API_BASE}/tasks/claim`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ task_id: taskId, member_name: currentUser.name })
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
    }
}

async function unclaimTask(taskId) {
    if(!confirm('确认撤销领取？任务将重新变为待领取状态。')) return;
    
    try {
        const res = await fetch(`${API_BASE}/tasks/unclaim`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ task_id: taskId })
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
    }
}

async function submitTaskComplete(taskId) {
    if(!confirm('确认提交任务？提交后将等待发布者验收。')) return;
    
    try {
        const res = await fetch(`${API_BASE}/tasks/submit`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ task_id: taskId })
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
    }
}

async function approveTask(taskId) {
    if(!confirm(`确认验收通过？通过后将发放${getPointsName()}奖励。`)) return;
    
    try {
        const res = await fetch(`${API_BASE}/tasks/approve`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ task_id: taskId })
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
    }
}

async function rejectTask(taskId) {
    if(!confirm('确认退回任务？任务将退回给领取者重做。')) return;
    
    try {
        const res = await fetch(`${API_BASE}/tasks/reject`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ task_id: taskId })
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
    }
}

async function deleteTask(taskId) {
    if(!confirm('确认删除此任务？此操作不可恢复。')) return;
    
    try {
        const res = await fetch(`${API_BASE}/tasks/delete`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ task_id: taskId })
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
    }
}

async function completeTask(taskId) {
    // 兼容旧版：直接完成任务
    if(!confirm('确认完成此任务？')) return;
    
    const memberName = currentUser ? currentUser.name : '未知用户';
    
    try {
        const res = await fetch(`${API_BASE}/tasks/complete`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ task_id: taskId, member_name: memberName })
        });
        
        if(res.ok) {
            fetchTasks();
            alert(`任务完成！${getPointsName()}已到账。`);
        } else {
            alert('完成任务失败');
        }
    } catch(e) {
        console.error(e);
        alert('网络错误');
    }
}

// --- Activities ---
let _cachedActivities = [];
let editingActivityId = null;

async function fetchActivities() {
    const container = document.getElementById('activity-list');
    showLoading('activity-list');
    
    try {
        const res = await fetch(`${API_BASE}/activities`);
        _cachedActivities = await res.json();
        
        if(_cachedActivities.length === 0) {
            showEmptyState('activity-list', '📅', '暂无活动，快来发起一个吧！', '发起活动', 'openActivityModal()');
            return;
        }

        container.innerHTML = _cachedActivities.map(a => `
            <div class="card" onclick="openActivityDetailView(${a.id})" style="cursor:pointer; margin-bottom:20px; transition:all 0.2s;">
                <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:10px;">
                     <h3 style="margin:0; font-size:1.2rem; line-height:1.4; flex:1; padding-right:12px;">${a.title}</h3>
                     <span class="points-badge" style="${getStatusStyle(a.status)}; margin-top:2px; float:none; flex-shrink:0; white-space:nowrap;">${a.status}</span>
                </div>
                <div style="color:#444; margin-bottom:15px; line-height:1.6; max-height:4.8em; overflow:hidden; display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical;">
                    ${a.desc || ''}
                </div>
                <div style="font-size:0.9em; color:#999; border-top:1px solid #eee; padding-top:10px; display:flex; justify-content:space-between; align-items:center;">
                    <span style="flex-shrink:0; margin-right:10px;">${formatDate(a.date)}</span>
                    <span style="flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; text-align:right;">${a.location || '线上'}</span>
                </div>
            </div>
        `).join('');
    } catch(e) { console.error(e); }
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
            publisher: currentUser ? currentUser.name : 'Unknown'
        };

        if(!data.title) { alert('请输入活动主题'); throw new Error('Title required'); }

        let url = `${API_BASE}/activities`;
        if(editingActivityId) {
            url = `${API_BASE}/activities/update`;
            data.id = editingActivityId;
        }

        const res = await fetch(url, {
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

async function deleteActivity(id) {
    if(!confirm('确定删除此活动？')) return;
    await fetch(`${API_BASE}/activities/delete`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({id})
    });
    fetchActivities();
    loadSystemInfo(); // Refresh Home list too
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
            date: new Date().toISOString().split('T')[0]
        };

        if (isNaN(data.amount) || !data.summary) {
            alert('请填写完整财务流向');
            return;
        }

        const response = await fetch(`${API_BASE}/finance`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(data)
        });

        if (!response.ok) throw new Error(`Server Error: ${response.status}`);

        document.getElementById('f-amount').value = '';
        document.getElementById('f-summary').value = '';
        document.getElementById('f-handler').value = '';
        document.getElementById('f-category').value = '会费';
        
        toggleModal('modal-finance');
        showSection('finance');
    } catch(err) {
        alert('提交失败: ' + err.message);
    } finally {
        submitBtn.innerText = originalText;
        submitBtn.disabled = false;
    }
}

let _homeActivities = []; // Store for home usage

function openActivityDetailView(id) {
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
                    <span>${act.location || '线上'}</span>
                </div>
                <div style="display:flex;">
                    <span style="color:#666; width:80px; flex-shrink:0;">发布人</span>
                    <span>${act.publisher || '未知'}</span>
                </div>
            </div>
            <div style="white-space:pre-wrap; line-height:1.8; color:#333; font-size:1.05rem;">${(act.desc || '（暂无详情）').trim()}</div>
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
                <button onclick="deleteActivityInView(${act.id})" style="background:#e74c3c; padding:6px 14px; font-size:0.9em;">删除</button>
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

async function deleteActivityInView(id) {
    if(!confirm('确定删除此活动？')) return;
    toggleModal('modal-activity-view'); // Close view
    await deleteActivity(id); // Reuse existing delete
}

async function loadSystemInfo() {
    try {
        const res = await fetch(`${API_BASE}/system/info`);
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
        }
            
        // Load Daily Recommendation (Random)
        const pRes = await fetch(`${API_BASE}/poems`);
        const poems = await pRes.json();
        if(poems.length > 0) {
            const p = poems[Math.floor(Math.random() * poems.length)];
            document.getElementById('daily-poem').innerHTML = `
                <h4>${p.title}</h4>
                <p style="white-space: pre-wrap;">${p.content}</p>
                <small>—— ${p.author}</small>
            `;
        } else {
            document.getElementById('daily-poem').innerText = "暂无诗词，快去藏诗阁发布吧！";
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
                    .filter(a => a.status !== '已结束')
                    .sort((a, b) => new Date(a.date) - new Date(b.date))
                    .slice(0, 3);
                
                if(upcoming.length === 0) {
                    homeActList.innerHTML = '<p style="color:#666;">暂无近期活动</p>';
                } else {
                    homeActList.innerHTML = upcoming.map(a => `
                        <div onclick="openActivityDetailView(${a.id})" style="border-bottom: 1px solid #eee; padding: 12px 0; display:flex; justify-content:space-between; align-items:center; cursor:pointer;" class="clickable-item">
                            <div style="flex: 1; min-width: 0; padding-right: 10px;">
                                <strong style="font-size:1.1em; display:block; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${a.title}</strong>
                                <div style="font-size:0.85em; color:#999; margin-top:6px;">
                                    <span style="margin-right:12px;">${formatDate(a.date)}</span>
                                    <span>${a.location || '线上'}</span>
                                </div>
                            </div>
                            <span class="points-badge" style="${getStatusStyle(a.status)}; margin:0; float:none; flex-shrink:0;">${a.status}</span>
                        </div>
                    `).join('');
                }
            } catch(e) {
                homeActList.innerText = '加载活动失败';
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
async function loadLatestPoems() {
    const container = document.getElementById('latest-poems-list');
    if(!container) return;
    
    try {
        const res = await fetch(`${API_BASE}/poems?page=1&limit=3`);
        const poems = await res.json();
        
        if(poems.length === 0) {
            container.innerHTML = '<p style="color:#666; text-align:center;">暂无诗作</p>';
            return;
        }
        
        container.innerHTML = poems.map(p => `
            <div style="border-bottom:1px solid #eee; padding:10px 0; cursor:pointer;" onclick="showSection('poems')">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <strong style="font-size:1em;">${p.title}</strong>
                    <span style="${getPoemTypeStyle(p.type)} padding:2px 6px; border-radius:4px; font-size:0.75em;">${p.type}</span>
                </div>
                <div style="font-size:0.85em; color:#888; margin-top:4px;">${p.author}</div>
            </div>
        `).join('');
    } catch(e) {
        console.error(e);
        container.innerHTML = '<p style="color:#e74c3c;">加载失败</p>';
    }
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
            container.innerHTML = '<p style="color:#666; text-align:center;">暂无年度数据</p>';
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
                    <span style="font-weight:${i < 3 ? '600' : '400'};">${m.alias || m.name}</span>
                </div>
                <span class="points-badge" title="年度新增${pointsName}">🪙 +${m.yearly_points || 0}</span>
            </div>
        `).join('');
    } catch(e) {
        console.error(e);
        container.innerHTML = '<p style="color:#e74c3c;">加载失败</p>';
    }
}

// --- Global Search Logic ---
let _globalSearchTerm = '';
let _searchCache = { poems: [], activities: [] };
let _debounceTimer = null;
let _currentSearchReq = 0; // To track latest request

function openPoemFromSearch(id) {
    const p = _searchCache.poems.find(x => x.id == id);
    if(p) openPoemModal(p);
}

function openActivityFromSearch(id) {
    let a = null;
    if(_searchCache.activities) a = _searchCache.activities.find(x => x.id == id);
    if(!a && typeof _cachedActivities !== 'undefined') a = _cachedActivities.find(x => x.id == id);
    
    if(a) openActivityModal(a);
    else openActivityDetailView(id);
}

// This is called when user types in global search input
async function handleGlobalSearch(term) {
    if (!term) {
        clearGlobalSearch();
        return;
    }
    
    // Switch to search results section immediately
    document.querySelectorAll('main > section').forEach(el => el.style.display = 'none');
    document.getElementById('search-results-section').style.display = 'block';
    
    // Optimistic UI for immediate feedback
    const resultsContainer = document.getElementById('search-results-container');
    resultsContainer.innerHTML = '<div style="text-align:center; padding:20px; color:#666;">正在搜索...</div>';
    
    const t = term.toLowerCase(); 
    const thisReqId = ++_currentSearchReq;

    try {
        // SERVER SIDE SEARCH for Scalability
        const [poems, activities, tasks] = await Promise.all([
            fetch(`${API_BASE}/poems?limit=20&q=${encodeURIComponent(term)}`).then(r=>r.json()).catch(()=>[]),
            fetch(`${API_BASE}/activities?limit=20&q=${encodeURIComponent(term)}`).then(r=>r.json()).catch(()=>[]),
            // Tasks remains client side or simple fetch for now if small
            fetch(`${API_BASE}/tasks`).then(r=>r.json()).catch(()=>[])
        ]);
        
        // Race Condition Check: If a newer request has started, ignore this result
        if (thisReqId !== _currentSearchReq) return;
        
        _searchCache = { poems, activities };

        // Filter tasks locally (assuming it returns all)
        const matchedTasks = tasks.filter(task => 
            (task.title && task.title.toLowerCase().includes(t)) || 
            (task.description && task.description.toLowerCase().includes(t))
        );

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
                    <b>[作品] ${highlight(p.title)}</b> - ${highlight(p.author)}
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
    document.getElementById('search-results-section').style.display = 'none';
    
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
        document.getElementById('login-section').style.display = 'flex';
    }
}

// --- Custom Fields Management ---

async function fetchCustomFields() {
    try {
        const res = await fetch(`${API_BASE}/settings/fields`);
        if(res.ok) _customFields = await res.json();
    } catch(e) { console.error('Failed to load custom fields', e); }
}

// --- 系统设置管理 ---
async function fetchSystemSettings() {
    try {
        const res = await fetch(`${API_BASE}/settings/system`);
        if(res.ok) {
            _systemSettings = await res.json();
            // 更新网页标题
            document.title = _systemSettings.system_name || '围炉诗社·理事台';
        }
    } catch(e) { console.error('Failed to load system settings', e); }
}

function loadSystemSettingsUI() {
    const systemNameInput = document.getElementById('setting-system-name');
    const saltInput = document.getElementById('setting-password-salt');
    const pointsInput = document.getElementById('setting-points-name');
    if(systemNameInput) systemNameInput.value = _systemSettings.system_name || '围炉诗社·理事台';
    if(saltInput) saltInput.value = _systemSettings.password_salt || 'weilu2018';
    if(pointsInput) pointsInput.value = _systemSettings.points_name || '围炉值';
}

async function saveSystemName() {
    const input = document.getElementById('setting-system-name');
    const value = input.value.trim();
    if(!value) { alert('系统名称不能为空'); return; }
    
    try {
        const res = await fetch(`${API_BASE}/settings/system`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ system_name: value })
        });
        if(res.ok) {
            _systemSettings.system_name = value;
            alert('系统名称已更新');
        } else {
            alert('保存失败');
        }
    } catch(e) { console.error(e); alert('网络错误'); }
}

async function savePointsName() {
    const input = document.getElementById('setting-points-name');
    const value = input.value.trim();
    if(!value) { alert('积分名称不能为空'); return; }
    
    try {
        const res = await fetch(`${API_BASE}/settings/system`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ points_name: value })
        });
        if(res.ok) {
            _systemSettings.points_name = value;
            alert('积分名称已更新');
            // 刷新页面以更新所有积分显示
            if(confirm('是否刷新页面以应用新名称？')) {
                location.reload();
            }
        } else {
            alert('保存失败');
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
    
    if(!confirm('修改Salt后，所有现有密码将失效，需要重新执行密码迁移！确定要修改吗？')) return;
    
    try {
        const res = await fetch(`${API_BASE}/settings/system`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ password_salt: value })
        });
        if(res.ok) {
            _systemSettings.password_salt = value;
            alert('Salt已更新，请立即执行密码迁移！');
        } else {
            alert('保存失败');
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
    const label = input.value.trim();
    const type = typeSelect ? typeSelect.value : 'text';

    if(!label) return;
    
    // Check dupe
    if(_customFields.find(f => f.label === label)) return alert('字段名已存在');
    
    const newField = { id: 'cf_' + Date.now(), label: label, type: type };
    const newFields = [..._customFields, newField];
    
    await saveCustomFields(newFields);
    input.value = '';
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
             body: JSON.stringify(fields)
         });
         if(res.ok) {
             _customFields = fields;
             renderAdminSettings(); 
             alert('设置已保存');
         } else {
             alert('保存失败');
         }
     } catch(e) { console.error(e); alert('网络错误'); }
}

function renderAdminSettings() {
    const container = document.getElementById('settings-fields-list');
    if(!container) return;
    
    // 加载系统设置UI
    loadSystemSettingsUI();
    
    // 加载数据统计
    loadDataStats();
    
    // 加载WiFi配置
    loadWifiConfig();
    
    if(_customFields.length === 0) {
        container.innerHTML = '<small>暂无自定义字段</small>';
        return;
    }

    const typeMap = { text: '文本', number: '数字', date: '日期', email: '邮箱' };

    container.innerHTML = _customFields.map(f => `
        <div class="field-item">
            <span><strong>${f.label}</strong> <small style="color:#888; font-weight:normal">(${typeMap[f.type] || '文本'})</small></span>
            <button onclick="deleteCustomField('${f.id}')" class="delete-btn">删除</button>
        </div>
    `).join('');
    
    // 加载登录日志
    fetchLoginLogs();
}

// --- 数据统计 ---
async function loadDataStats() {
    try {
        const res = await fetch(`${API_BASE}/system/stats`);
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

// --- 登录日志 ---
async function fetchLoginLogs() {
    const container = document.getElementById('login-logs-list');
    if(!container) return;
    
    try {
        const res = await fetch(`${API_BASE}/login_logs`);
        if(!res.ok) throw new Error('Failed');
        const logs = await res.json();
        
        if(logs.length === 0) {
            container.innerHTML = '<p style="color:#999; text-align:center;">暂无登录记录</p>';
            return;
        }
        
        container.innerHTML = logs.map(log => `
            <div style="display:flex; justify-content:space-between; align-items:center; padding:8px 0; border-bottom:1px solid #eee;">
                <div>
                    <span style="font-weight:500;">${log.member_name || '未知'}</span>
                    <span style="color:#888; font-size:0.85em; margin-left:8px;">${log.phone}</span>
                </div>
                <div style="text-align:right;">
                    <span class="points-badge" style="${log.status === 'success' ? 'background:#E8F5E9; color:#2E7D32;' : 'background:#FFEBEE; color:#C62828;'}">${log.status === 'success' ? '成功' : '失败'}</span>
                    <div style="font-size:0.8em; color:#999; margin-top:4px;">${log.login_time ? log.login_time.replace('T', ' ') : ''}</div>
                </div>
            </div>
        `).join('');
    } catch(e) {
        console.error(e);
        container.innerHTML = '<p style="color:#e74c3c;">加载失败</p>';
    }
}

// --- 密码迁移 ---
async function migratePasswords() {
    if(!confirm('确定要将所有明文密码迁移为哈希存储吗？此操作不可逆。')) return;
    
    try {
        const res = await fetch(`${API_BASE}/migrate_passwords`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'}
        });
        
        if(res.ok) {
            const result = await res.json();
            alert(`密码迁移完成！共迁移 ${result.migrated} 个账户。`);
        } else {
            alert('迁移失败');
        }
    } catch(e) {
        console.error(e);
        alert('网络错误');
    }
}

// --- WiFi 配置 ---
function toggleStaticIpFields() {
    const staticRadio = document.querySelector('input[name="wifi-ip-mode"][value="static"]');
    const fields = document.getElementById('static-ip-fields');
    if(staticRadio && fields) {
        fields.style.display = staticRadio.checked ? 'block' : 'none';
    }
}

async function loadWifiConfig() {
    try {
        const res = await fetch(`${API_BASE}/wifi/config`);
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
        if(apIpInput) apIpInput.value = config.ap_ip || '192.168.18.1';
        
    } catch(e) {
        console.error(e);
    }
}

async function saveWifiConfig() {
    const staticRadio = document.querySelector('input[name="wifi-ip-mode"][value="static"]');
    const config = {
        wifi_ssid: document.getElementById('wifi-ssid')?.value || '',
        sta_use_static_ip: staticRadio?.checked || false,
        sta_ip: document.getElementById('wifi-sta-ip')?.value || '',
        sta_subnet: document.getElementById('wifi-sta-subnet')?.value || '255.255.255.0',
        sta_gateway: document.getElementById('wifi-sta-gateway')?.value || '',
        sta_dns: document.getElementById('wifi-sta-dns')?.value || '8.8.8.8',
        ap_ssid: document.getElementById('wifi-ap-ssid')?.value || '',
        ap_ip: document.getElementById('wifi-ap-ip')?.value || '192.168.18.1'
    };
    
    // 只有输入了密码才发送
    const wifiPwd = document.getElementById('wifi-password')?.value;
    if(wifiPwd) config.wifi_password = wifiPwd;
    
    const apPwd = document.getElementById('wifi-ap-password')?.value;
    if(apPwd) config.ap_password = apPwd;
    
    if(!config.wifi_ssid) {
        alert('请输入WiFi名称');
        return;
    }
    
    try {
        const res = await fetch(`${API_BASE}/wifi/config`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(config)
        });
        
        if(res.ok) {
            alert('WiFi配置已保存，重启设备后生效');
        } else {
            const err = await res.json();
            alert('保存失败: ' + (err.error || '未知错误'));
        }
    } catch(e) {
        console.error(e);
        alert('网络错误');
    }
}

// --- 数据备份 ---
async function exportBackup() {
    try {
        const res = await fetch(`${API_BASE}/backup/export`);
        if(!res.ok) {
            throw new Error('导出请求失败');
        }
        const backup = await res.json();
        
        const now = new Date();
        const timestamp = now.getFullYear() + 
            String(now.getMonth() + 1).padStart(2, '0') + 
            String(now.getDate()).padStart(2, '0') + '_' +
            String(now.getHours()).padStart(2, '0') + 
            String(now.getMinutes()).padStart(2, '0');
        const filename = `backup_${timestamp}.json`;
        
        const blob = new Blob([JSON.stringify(backup, null, 2)], {type: 'application/json'});
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        URL.revokeObjectURL(url);
        document.body.removeChild(a);
        
        alert('备份导出成功');
    } catch(e) {
        console.error(e);
        alert('导出失败: ' + e.message);
    }
}

function triggerImportBackup() {
    document.getElementById('backup-file-input').click();
}

async function importBackup(event) {
    const file = event.target.files[0];
    if(!file) return;
    
    if(!confirm('导入数据将覆盖现有所有数据，此操作不可逆！\n\n确定要继续吗？')) {
        document.getElementById('backup-file-input').value = '';
        return;
    }
    
    try {
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
        
        const res = await fetch(`${API_BASE}/backup/import`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(backup)
        });
        
        if(res.ok) {
            alert('数据恢复成功，页面将刷新');
            location.reload();
        } else {
            const err = await res.json();
            throw new Error(err.error || '未知错误');
        }
    } catch(e) {
        console.error(e);
        alert('导入失败: ' + e.message);
    }
    
    document.getElementById('backup-file-input').value = '';
}
