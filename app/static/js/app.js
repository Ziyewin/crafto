/* ── 工业级智能 Agent 平台 — 前端主逻辑 ── */

// ── API 工具 ──
// ── API 工具（独立函数，避免 this 问题） ──
function getAuthHeaders() {
  // 直接从 localStorage 读取，避免 getter 可能的问题
  const uid = localStorage.getItem('agent_user_id') || '';
  const key = localStorage.getItem('agent_api_key') || '';
  return {
    'Content-Type': 'application/json',
    'Authorization': uid ? `Bearer ${uid}` : '',
    'X-API-Key': key || '',
  };
}

const API = {
  base: '',

  async get(path) {
    const res = await fetch(this.base + path, { headers: getAuthHeaders() });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: '请求失败' }));
      throw new Error(err.detail || '请求失败');
    }
    return res.json();
  },

  async post(path, body) {
    const res = await fetch(this.base + path, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: '请求失败' }));
      throw new Error(err.detail || '请求失败');
    }
    return res.json();
  },

  async del(path) {
    const res = await fetch(this.base + path, {
      method: 'DELETE',
      headers: getAuthHeaders(),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: '请求失败' }));
      throw new Error(err.detail || '请求失败');
    }
    return res.json();
  },
};

// ── 本地存储 ──
const store = {
  get userId() { return localStorage.getItem('agent_user_id') || ''; },
  set userId(v) { localStorage.setItem('agent_user_id', v); },
  get apiKey() { return localStorage.getItem('agent_api_key') || ''; },
  set apiKey(v) { localStorage.setItem('agent_api_key', v); },
  get username() { return localStorage.getItem('agent_username') || ''; },
  set username(v) { localStorage.setItem('agent_username', v); },
  get role() { return localStorage.getItem('agent_role') || 'normal'; },
  set role(v) { localStorage.setItem('agent_role', v); },
  clear() { localStorage.removeItem('agent_user_id'); localStorage.removeItem('agent_api_key'); localStorage.removeItem('agent_username'); localStorage.removeItem('agent_role'); },
};

// ── 工具函数 ──
function $(sel) { return document.querySelector(sel); }
function $$(sel) { return document.querySelectorAll(sel); }
function escapeHtml(str) { const d = document.createElement('div'); d.textContent = str; return d.innerHTML; }
function now() { return new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }); }

function toast(msg, type = 'info') {
  const container = $('#toast-container');
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  const icons = { success: '✅', error: '❌', info: 'ℹ️' };
  el.innerHTML = `${icons[type] || '•'} ${escapeHtml(msg)}`;
  container.appendChild(el);
  setTimeout(() => { el.style.opacity = '0'; el.style.transition = 'opacity 0.3s'; setTimeout(() => el.remove(), 300); }, 3000);
}

// ── 简易 Markdown 渲染 ──
function renderMarkdown(text) {
  if (!text) return '';
  let html = text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    // 代码块
    .replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>')
    // 行内代码
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    // 标题
    .replace(/^### (.+)$/gm, '<h3>$1</h3>')
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/^# (.+)$/gm, '<h1>$1</h1>')
    // 粗体/斜体
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    // 列表
    .replace(/^- (.+)$/gm, '<li>$1</li>')
    // 数字列表
    .replace(/^\d+\.\s(.+)$/gm, '<li>$1</li>')
    // 链接
    .replace(/\[(.+?)\]\((.+?)\)/g, '<a href="$2" target="_blank">$1</a>')
    // 换行
    .replace(/\n/g, '<br>');
  // 包裹列表
  html = html.replace(/(<li>.*?<\/li>)/g, '<ul>$1</ul>');
  html = html.replace(/<\/ul>\s*<ul>/g, '');
  return html;
}

// ── 页面状态 ──
let state = {
  sessions: [],
  activeSessionId: null,
  messages: {},
  isStreaming: false,
  abortController: null,
};

// ── 初始化 ──
async function init() {
  checkLogin();
}

function checkLogin() {
  if (store.userId && store.apiKey) {
    showApp();
    loadSessions();
  } else {
    showAuth();
  }
}

function showAuth() {
  $('#app').classList.remove('active');
  $('#auth-page').style.display = 'flex';
  switchAuthTab('login');
}

function showApp() {
  $('#auth-page').style.display = 'none';
  $('#app').classList.add('active');
  $('#user-name').textContent = store.username || '用户';
  $('#user-role').textContent = store.role === 'admin' ? '管理员' : store.role === 'advanced' ? '高级用户' : '普通用户';
  $('#user-avatar').textContent = (store.username || '用')[0];
  // 管理员入口
  $('#admin-link').style.display = store.role === 'admin' ? 'flex' : 'none';
}

// ── 启用输入框 ──
function enableChatInput() {
  document.getElementById('chat-input').disabled = false;
  document.querySelector('.send-btn').disabled = false;
  document.getElementById('chat-input').focus();
  document.getElementById('status-indicator').textContent = '就绪';
}


// ── 登录/注册 ──
function switchAuthTab(tab) {
  $$('.auth-tab').forEach(t => t.classList.toggle('active', t.dataset.tab === tab));
  $('#login-form').style.display = tab === 'login' ? 'block' : 'none';
  $('#register-form').style.display = tab === 'register' ? 'block' : 'none';
}

async function handleLogin() {
  const username = $('#login-username').value.trim();
  const password = $('#login-password').value.trim();
  if (!username || !password) { showAuthError('请填写用户名和密码'); return; }

  try {
    const res = await API.post('/api/v1/auth/login', { username, password });
    store.userId = res.user_id;
    store.apiKey = res.api_key;
    store.username = res.username;
    store.role = res.role;
    toast('登录成功', 'success');
    showApp();
    loadSessions();
  } catch (e) {
    showAuthError(e.message);
  }
}

async function handleRegister() {
  const username = $('#reg-username').value.trim();
  const password = $('#reg-password').value.trim();
  const role = $('#reg-role').value;
  if (!username || !password) { showAuthError('请填写用户名和密码'); return; }
  if (password.length < 6) { showAuthError('密码至少6位'); return; }

  try {
    const res = await API.post('/api/v1/auth/register', { username, password, role });
    store.userId = res.user_id;
    store.apiKey = res.api_key;
    store.username = username;
    store.role = role;
    toast('注册成功', 'success');
    showApp();
    loadSessions();
  } catch (e) {
    showAuthError(e.message);
  }
}

function showAuthError(msg) {
  $('#auth-error').textContent = msg;
  $('#auth-error').style.display = 'block';
}

function logout() {
  if (state.isStreaming && state.abortController) state.abortController.abort();
  store.clear();
  state = { sessions: [], activeSessionId: null, messages: {}, isStreaming: false, abortController: null };
  $('#chat-messages').innerHTML = '';
  showAuth();
  toast('已退出登录', 'info');
}

// ── 会话管理 ──
async function loadSessions() {
  try {
    const data = await API.get('/api/v1/chat/sessions');
    state.sessions = data.sessions || [];
    renderSessionList();
  } catch (e) {
    console.error('加载会话失败:', e);
    // 401 = 认证失效，可能是旧 session 残留，跳转回登录页
    if (e.message && e.message.includes('401')) {
      console.warn('认证失效，清除旧 session 并跳转到登录页');
      store.clear();
      showAuth();
    }
  }
}

function renderSessionList() {
  const list = $('#session-list');
  if (state.sessions.length === 0) {
    list.innerHTML = '<div style="padding: 16px; text-align: center; color: var(--text-muted); font-size: 13px;">暂无会话，点击上方按钮新建</div>';
    return;
  }
  list.innerHTML = state.sessions.map(s => `
    <div class="session-item ${s.session_id === state.activeSessionId ? 'active' : ''}"
         data-id="${s.session_id}" onclick="switchSession('${s.session_id}')">
      <span class="icon">💬</span>
      <span>${escapeHtml(s.title || '新对话')}</span>
    </div>
  `).join('');
}

async function newSession() {
  if (state.isStreaming) return;
  state.activeSessionId = null;
  $('#chat-messages').innerHTML = `
    <div class="empty-state">
      <div class="icon">🤖</div>
      <h3>智能 Agent 平台</h3>
      <p>开始一段新对话，输入问题即可。支持预置工具调用和代码生成执行。</p>
    </div>
  `;
  $('#chat-title').textContent = '新对话';
  renderSessionList();
  $('#chat-input').focus();
}

async function switchSession(sessionId) {
  if (state.isStreaming) return;
  state.activeSessionId = sessionId;
  renderSessionList();

  // 从服务器加载历史消息
  const container = $('#chat-messages');
  container.innerHTML = '<div style="text-align:center;padding:40px;color:var(--text-muted);">加载中...</div>';

  try {
    const data = await API.get(`/api/v1/chat/sessions/${sessionId}/messages`);
    const msgs = data.messages || [];
    
    if (msgs.length === 0) {
      container.innerHTML = `
        <div class="empty-state">
          <div class="icon">💬</div>
          <h3>继续对话</h3>
          <p>在下方输入消息继续这个会话。</p>
        </div>
      `;
    } else {
      container.innerHTML = '';
      msgs.forEach(m => {
        if (m.role === 'user') {
          addMessage('user', m.content);
        } else if (m.role === 'assistant') {
          addMessage('assistant', m.content);
        } else if (m.role === 'tool') {
          // 工具消息：显示为系统消息
          const div = document.createElement('div');
          div.className = 'message system';
          try {
            const parsed = JSON.parse(m.content);
            div.innerHTML = `<div class="bubble">🛠 ${escapeHtml(parsed.tool_name || '工具')}: ${parsed.success ? '✅' : '❌'}\</div>`;
          } catch {
            div.innerHTML = `<div class="bubble">🔧 工具执行结果</div>`;
          }
          container.appendChild(div);
        }
      });
      scrollToBottom();
    }
  } catch (e) {
    container.innerHTML = `<div class="empty-state"><div class="icon">⚠️</div><h3>加载失败</h3><p>${escapeHtml(e.message)}</p></div>`;
  }

  const session = state.sessions.find(s => s.session_id === sessionId);
  $('#chat-title').textContent = session ? escapeHtml(session.title) : '对话';
}

// ── 发送消息 ──
async function sendMessage() {
  const input = $('#chat-input');
  const text = input.value.trim();
  if (!text || state.isStreaming) return;

  input.value = '';
  input.style.height = 'auto';

  // 移除空状态
  const container = $('#chat-messages');
  const empty = container.querySelector('.empty-state');
  if (empty) container.innerHTML = '';

  // 添加用户消息
  addMessage('user', text);

  // 添加 AI 消息占位
  const msgDiv = document.createElement('div');
  msgDiv.className = 'message assistant';
  msgDiv.id = 'streaming-msg';
  msgDiv.innerHTML = `
    <div class="bubble">
      <div class="thinking-indicator">
        <span class="thinking-label">思考中</span>
        <div class="thinking-dots"><span></span><span></span><span></span></div>
      </div>
    </div>
  `;
  container.appendChild(msgDiv);
  container.scrollTop = container.scrollHeight;

  state.isStreaming = true;
  state.abortController = new AbortController();
  const sendBtn = $('.send-btn');
  sendBtn.disabled = true;

  try {
    const res = await fetch('/api/v1/chat/send', {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({
        session_id: state.activeSessionId || null,
        message: text,
        stream: false,
      }),
      signal: state.abortController.signal,
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || '请求失败');
    }

    const data = await res.json();

    // 更新流式占位
    const bubble = msgDiv.querySelector('.bubble');
    bubble.innerHTML = renderMarkdown(data.reply);

    // 更新时间
    const time = document.createElement('div');
    time.className = 'time';
    time.textContent = now();
    msgDiv.appendChild(time);

    // 显示工具调用
    if (data.tool_calls && data.tool_calls.length > 0) {
      const toolSection = document.createElement('div');
      toolSection.style.marginTop = '8px';
      data.tool_calls.forEach(tc => {
        const badge = document.createElement('div');
        badge.className = `tool-call-badge ${tc.success ? 'success' : 'error'}`;
        badge.innerHTML = `${tc.success ? '✅' : '❌'} 🛠 ${escapeHtml(tc.tool_name)} ${tc.execution_time_ms ? `(${tc.execution_time_ms}ms)` : ''}`;
        toolSection.appendChild(badge);
        if (tc.output || tc.error) {
          const detail = document.createElement('div');
          detail.className = 'tool-call-detail';
          detail.innerHTML = `<pre>${escapeHtml(tc.output || tc.error || '')}</pre>`;
          toolSection.appendChild(detail);
        }
      });
      msgDiv.appendChild(toolSection);
    }

    // 更新会话 ID 和信息
    state.activeSessionId = data.session_id;
    $('#chat-title').textContent = data.session_id === state.activeSessionId ? '对话' : '对话';
    await loadSessions();
    scrollToBottom();

  } catch (e) {
    if (e.name === 'AbortError') return;
    msgDiv.querySelector('.bubble').innerHTML = `<span style="color: var(--error)">❌ 出错了：${escapeHtml(e.message)}</span>`;
    toast(e.message, 'error');
  } finally {
    state.isStreaming = false;
    sendBtn.disabled = false;
    const streaming = document.getElementById('streaming-msg');
    if (streaming) streaming.id = '';
  }
}

function addMessage(role, content, extra = '') {
  const container = $('#chat-messages');
  const div = document.createElement('div');
  div.className = `message ${role}`;
  div.innerHTML = `
    <div class="bubble">${escapeHtml(content)}</div>
    <div class="time">${now()}</div>
    ${extra}
  `;
  container.appendChild(div);
  scrollToBottom();
}

function scrollToBottom() {
  const container = $('#chat-messages');
  container.scrollTop = container.scrollHeight;
}

// ── 输入框自动调整 ──
function autoResize(textarea) {
  textarea.style.height = 'auto';
  textarea.style.height = Math.min(textarea.scrollHeight, 120) + 'px';
}

// ── 快捷键 ──
document.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey && $('#app').classList.contains('active')) {
    e.preventDefault();
    sendMessage();
  }
  if (e.key === 'Enter' && $('#auth-page').style.display !== 'none') {
    if ($('#login-form').style.display !== 'none') handleLogin();
    else handleRegister();
  }
});

// ── 管理后台 ──
function openAdmin() {
  if (store.role !== 'admin') { toast('需要管理员权限', 'error'); return; }
  $('#admin-modal').classList.add('active');
  switchAdminTab('anomalies');
  loadAdminData('anomalies');
}

function closeAdmin() {
  $('#admin-modal').classList.remove('active');
}

function switchAdminTab(tab) {
  $$('.admin-tab').forEach(t => t.classList.toggle('active', t.dataset.tab === tab));
  $$('.admin-panel').forEach(p => p.style.display = 'none');
  const panel = document.getElementById(`admin-${tab}`);
  if (panel) panel.style.display = 'block';
  loadAdminData(tab);
}

async function loadAdminData(tab) {
  try {
    if (tab === 'anomalies') {
      const data = await API.get('/api/v1/admin/anomalies');
      renderAdminTable('anomalies-table', data.anomalies || [], [
        { key: 'anomaly_id', label: '异常ID', render: v => v.slice(0, 8) + '...' },
        { key: 'error_type', label: '类型' },
        { key: 'user_id', label: '用户', render: v => v ? v.slice(0, 8) + '...' : '-' },
        { key: 'retry_status', label: '重试状态', render: v => `<span class="badge-status ${v === 'completed' ? 'ok' : 'warn'}">${v}</span>` },
        { key: 'resolved', label: '已解决', render: v => `<span class="badge-status ${v ? 'ok' : 'err'}">${v ? '是' : '否'}</span>` },
        { key: 'created_at', label: '时间', render: v => v ? new Date(v).toLocaleString('zh-CN') : '-' },
      ]);
    } else if (tab === 'logs') {
      const data = await API.get('/api/v1/admin/logs');
      renderAdminTable('logs-table', data.logs || [], [
        { key: 'trace_id', label: 'TraceID', render: v => v.slice(0, 8) + '...' },
        { key: 'level', label: '级别', render: v => `<span class="badge-status ${v === 'ERROR' ? 'err' : v === 'WARN' ? 'warn' : 'ok'}">${v}</span>` },
        { key: 'component', label: '组件' },
        { key: 'message', label: '消息', render: v => escapeHtml((v || '').slice(0, 60)) },
        { key: 'created_at', label: '时间', render: v => v ? new Date(v).toLocaleString('zh-CN') : '-' },
      ]);
    } else if (tab === 'users') {
      const data = await API.get('/api/v1/admin/users');
      renderAdminTable('users-table', data.users || [], [
        { key: 'user_id', label: '用户ID', render: v => v.slice(0, 8) + '...' },
        { key: 'username', label: '用户名' },
        { key: 'role', label: '角色', render: v => `<span class="badge-status ${v === 'admin' ? 'ok' : v === 'advanced' ? 'warn' : ''}">${v}</span>` },
        { key: 'is_active', label: '状态', render: v => `<span class="badge-status ${v ? 'ok' : 'err'}">${v ? '活跃' : '禁用'}</span>` },
        { key: 'created_at', label: '创建时间', render: v => v ? new Date(v).toLocaleString('zh-CN') : '-' },
      ]);
    }
  } catch (e) {
    toast('加载管理数据失败: ' + e.message, 'error');
  }
}

function renderAdminTable(tableId, data, columns) {
  const table = document.getElementById(tableId);
  if (!table) return;
  if (data.length === 0) {
    table.innerHTML = '<tr><td colspan="10" style="text-align:center;color:var(--text-muted);padding:40px;">暂无数据</td></tr>';
    return;
  }
  table.innerHTML = data.map(row => {
    const cells = columns.map(col => {
      const val = row[col.key] !== undefined ? row[col.key] : '-';
      return `<td>${col.render ? col.render(val) : escapeHtml(String(val))}</td>`;
    }).join('');
    return `<tr>${cells}</tr>`;
  }).join('');
}

// ── 页面加载后初始化 ──
document.addEventListener('DOMContentLoaded', () => {
  // 登录回车
  $('#login-password').addEventListener('keydown', (e) => { if (e.key === 'Enter') handleLogin(); });
  $('#reg-password').addEventListener('keydown', (e) => { if (e.key === 'Enter') handleRegister(); });
  init();
});

// 暴露到全局
window.sendMessage = sendMessage;
window.handleLogin = handleLogin;
window.handleRegister = handleRegister;
window.switchAuthTab = switchAuthTab;
window.newSession = newSession;
window.switchSession = switchSession;
window.logout = logout;
window.openAdmin = openAdmin;
window.closeAdmin = closeAdmin;
window.switchAdminTab = switchAdminTab;
window.autoResize = autoResize;
