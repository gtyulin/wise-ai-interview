// ── 狀態 ─────────────────────────────────────────
let sessionId = null;
let participantId = null;
let timerInterval = null;
let startTime = null;
let isWaitingForAI = false;

// ── 頁面切換 ──────────────────────────────────────

// 知情同意頁：勾選才啟用按鈕
document.getElementById('consent-check').addEventListener('change', function () {
  document.getElementById('btn-consent').disabled = !this.checked;
});

function showPage(id) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  window.scrollTo(0, 0);
}

function goToForm() {
  showPage('page-form');
}

// ── 開始訪談 ──────────────────────────────────────
async function startInterview(event) {
  event.preventDefault();

  const btn = document.getElementById('btn-start');
  const errDiv = document.getElementById('form-error');
  errDiv.style.display = 'none';

  const body = {
    department: document.getElementById('department').value,
    graduation_year: document.getElementById('graduation-year').value,
    current_job: document.getElementById('current-job').value,
    job_category: document.getElementById('job-category').value,
    career_transition_timing: document.getElementById('career-timing').value,
  };

  btn.disabled = true;
  btn.textContent = '正在連線，請稍候…';

  try {
    const res = await fetch('/api/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || '伺服器錯誤，請稍後再試');
    }

    const data = await res.json();
    sessionId = data.session_id;
    participantId = data.participant_id;

    // 切換到對話頁
    showPage('page-chat');
    document.getElementById('participant-label').textContent = participantId;
    startTimer();

    // 顯示 AI 第一句
    appendMessage('ai', data.message);

    if (data.is_complete) endInterview();

  } catch (e) {
    errDiv.textContent = e.message;
    errDiv.style.display = 'block';
    btn.disabled = false;
    btn.textContent = '開始訪談 →';
  }
}

// ── 傳送訊息 ──────────────────────────────────────
async function sendMessage() {
  if (isWaitingForAI) return;

  const input = document.getElementById('user-input');
  const text = input.value.trim();
  if (!text) return;

  input.value = '';
  input.style.height = 'auto';
  appendMessage('user', text);

  isWaitingForAI = true;
  document.getElementById('send-btn').disabled = true;
  input.disabled = true;

  showTyping();

  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, message: text }),
    });

    removeTyping();

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || '伺服器錯誤，請稍後再試');
    }

    const data = await res.json();
    appendMessage('ai', data.message);

    if (data.is_complete) {
      endInterview();
    }

  } catch (e) {
    removeTyping();
    appendMessage('ai', `⚠️ 發生錯誤：${e.message}。請重新整理頁面。`);
  } finally {
    isWaitingForAI = false;
    document.getElementById('send-btn').disabled = false;
    input.disabled = false;
    input.focus();
  }
}

function handleEnterKey(event) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    sendMessage();
  }
}

// ── 訊息顯示 ──────────────────────────────────────
function appendMessage(role, text) {
  const container = document.getElementById('chat-messages');

  const wrapper = document.createElement('div');
  wrapper.className = `message ${role}`;

  const label = document.createElement('div');
  label.className = 'message-label';
  label.textContent = role === 'ai' ? 'AI 訪談員' : '您';

  const bubble = document.createElement('div');
  bubble.className = 'message-bubble';
  bubble.textContent = text;

  wrapper.appendChild(label);
  wrapper.appendChild(bubble);
  container.appendChild(wrapper);

  container.scrollTop = container.scrollHeight;
}

let typingEl = null;

function showTyping() {
  const container = document.getElementById('chat-messages');
  typingEl = document.createElement('div');
  typingEl.className = 'message ai';
  typingEl.id = 'typing-wrapper';

  const label = document.createElement('div');
  label.className = 'message-label';
  label.textContent = 'AI 訪談員';

  const indicator = document.createElement('div');
  indicator.className = 'typing-indicator';
  indicator.innerHTML = `
    <div class="typing-dot"></div>
    <div class="typing-dot"></div>
    <div class="typing-dot"></div>
  `;

  typingEl.appendChild(label);
  typingEl.appendChild(indicator);
  container.appendChild(typingEl);
  container.scrollTop = container.scrollHeight;
}

function removeTyping() {
  const el = document.getElementById('typing-wrapper');
  if (el) el.remove();
}

// ── 結束訪談 ──────────────────────────────────────
function endInterview() {
  clearInterval(timerInterval);

  document.getElementById('chat-input-area').style.display = 'none';

  const endedDiv = document.getElementById('interview-ended');
  endedDiv.style.display = 'flex';
  document.getElementById('ended-participant-id').textContent =
    `受訪者代號：${participantId}`;
}

// ── 計時器 ────────────────────────────────────────
function startTimer() {
  startTime = Date.now();
  const el = document.getElementById('time-elapsed');

  timerInterval = setInterval(() => {
    const elapsed = Math.floor((Date.now() - startTime) / 1000);
    const m = String(Math.floor(elapsed / 60)).padStart(2, '0');
    const s = String(elapsed % 60).padStart(2, '0');
    el.textContent = `${m}:${s}`;
  }, 1000);
}
