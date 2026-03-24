// Noesis Extension — Sidebar popup (vanilla JS, no build step needed)
const API_BASE = 'https://api.noesis.is';
const NOESIS_BASE = 'https://noesis.is';

const content = document.getElementById('content');

let state = {
  token: null,
  projectId: null,
  draftId: null,
  currentProjectId: null,
  draft: null,           // { id, status, title, project_id }
  progress: 0,
  message: '',
  wsConnected: false,
  topActions: [],
  errorMessage: null,    // Non-blocking error to show in sidebar
  multiFileWarning: null, // Warning for multi-file projects
};

let pollInterval = null;
let ws = null;

// ── Render ────────────────────────────────────────────────────────────────────

function render() {
  const { token, draft, progress, message, wsConnected, topActions, errorMessage, multiFileWarning } = state;

  if (!token) {
    content.innerHTML = `
      <div class="center">
        <p class="muted">Log in to Noesis to analyze your Overleaf drafts with expert reviewer-style feedback.</p>
        <button class="btn-primary" id="btn-login">Log in to Noesis</button>
      </div>`;
    document.getElementById('btn-login').addEventListener('click', () => {
      chrome.tabs.create({ url: `${NOESIS_BASE}/login` });
    });
    return;
  }

  // Show non-blocking error
  if (errorMessage) {
    content.innerHTML = `
      <div class="center">
        <p class="error-label">${escHtml(errorMessage)}</p>
        <button class="btn-secondary" id="btn-dismiss-error">Dismiss</button>
      </div>`;
    document.getElementById('btn-dismiss-error').addEventListener('click', () => {
      state.errorMessage = null;
      render();
    });
    return;
  }

  if (!draft) {
    content.innerHTML = `
      <div class="center">
        <p class="muted">Open an Overleaf project and click the <strong style="color:#E8E8F0">Noesis Review</strong> button in the editor toolbar to analyze your draft.</p>
        <button class="btn-primary" id="btn-analyze">Analyze Draft</button>
      </div>`;
    document.getElementById('btn-analyze').addEventListener('click', triggerAnalyze);
    return;
  }

  if (draft.status === 'processing' || draft.status === 'pending') {
    const multiFileHtml = multiFileWarning
      ? `<p class="polling-note" style="color:#E5A84D">⚠ ${escHtml(multiFileWarning)}</p>`
      : '';
    content.innerHTML = `
      <p class="progress-label">Analyzing: ${escHtml(draft.title || 'Draft')}</p>
      <div class="progress-track"><div class="progress-fill" id="progress-fill" style="width:${progress}%"></div></div>
      <p class="progress-msg" id="progress-msg">${escHtml(message || 'Analyzing draft...')}${progress > 0 ? ` (${progress}%)` : ''}</p>
      ${multiFileHtml}
      ${!wsConnected ? '<p class="polling-note">Polling for updates...</p>' : ''}`;
    return;
  }

  if (draft.status === 'analyzed') {
    const actionsHtml = topActions.length
      ? `<p class="actions-title">Top Action Items</p>
         <div class="actions-list">${topActions.map(a => `<div class="action-item">${escHtml(a)}</div>`).join('')}</div>`
      : '';
    const draftUrl = `${NOESIS_BASE}/projects/${draft.project_id || state.currentProjectId}/drafts/${draft.id}`;
    content.innerHTML = `
      <p class="complete-label">✓ Analysis complete</p>
      ${actionsHtml}
      <a class="btn-link" id="btn-view" href="${draftUrl}">View Full Analysis →</a>`;
    document.getElementById('btn-view').addEventListener('click', (e) => {
      e.preventDefault();
      chrome.tabs.create({ url: draftUrl });
    });
    return;
  }

  if (draft.status === 'failed') {
    content.innerHTML = `
      <div class="center">
        <p class="error-label">Analysis failed. Please try again.</p>
        <button class="btn-secondary" id="btn-retry">Retry</button>
      </div>`;
    document.getElementById('btn-retry').addEventListener('click', triggerAnalyze);
    return;
  }
}

// ── Progress bar update without full re-render ────────────────────────────────

function updateProgressInPlace() {
  const fill = document.getElementById('progress-fill');
  const msg = document.getElementById('progress-msg');
  if (fill) fill.style.width = `${state.progress}%`;
  if (msg) msg.textContent = `${state.message || 'Analyzing draft...'}${state.progress > 0 ? ` (${state.progress}%)` : ''}`;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function triggerAnalyze() {
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    if (tabs[0]?.id) {
      chrome.tabs.sendMessage(tabs[0].id, { type: 'TRIGGER_ANALYZE' });
    }
  });
}

// ── WebSocket progress ────────────────────────────────────────────────────────

function connectWebSocket(draftId, token) {
  if (ws) { try { ws.close(); } catch (_) {} }
  const url = `wss://api.noesis.is/drafts/${draftId}/analysis-stream?token=${token}`;
  try {
    ws = new WebSocket(url);
    ws.onopen = () => { state.wsConnected = true; };
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        state.progress = data.progress ?? state.progress;
        state.message = data.message ?? state.message;
        // Update in-place if still in processing state, else full re-render
        if (state.draft?.status === 'processing' || state.draft?.status === 'pending') {
          updateProgressInPlace();
        } else {
          render();
        }
      } catch (_) {}
    };
    ws.onerror = () => { state.wsConnected = false; };
    ws.onclose = () => { state.wsConnected = false; };
  } catch (_) {
    state.wsConnected = false;
  }
}

// ── Draft status polling ──────────────────────────────────────────────────────

function startPolling(draftId, token) {
  stopPolling();
  pollInterval = setInterval(async () => {
    try {
      const resp = await fetch(`${API_BASE}/drafts/${draftId}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!resp.ok) return;
      const data = await resp.json();
      state.draft = data;
      if (data.status === 'analyzed') {
        stopPolling();
        fetchTopActions(draftId, token);
      }
      render();
    } catch (_) {}
  }, 5000);
}

function stopPolling() {
  if (pollInterval) { clearInterval(pollInterval); pollInterval = null; }
}

async function fetchTopActions(draftId, token) {
  try {
    const resp = await fetch(`${API_BASE}/drafts/${draftId}/feedback?limit=3`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!resp.ok) return;
    const data = await resp.json();
    const items = (data.feedback || data.items || data || []).slice(0, 3);
    state.topActions = items
      .map(f => f.feedback_text || f.text || '')
      .filter(Boolean);
    render();
  } catch (_) {}
}

// ── Init ──────────────────────────────────────────────────────────────────────

chrome.storage.local.get(
  ['noesis_token', 'noesis_project_id', 'noesis_current_draft_id', 'noesis_current_project_id'],
  (result) => {
    state.token = result.noesis_token || null;
    state.projectId = result.noesis_project_id || null;
    state.draftId = result.noesis_current_draft_id || null;
    state.currentProjectId = result.noesis_current_project_id || null;

    render();

    if (state.token && state.draftId) {
      connectWebSocket(state.draftId, state.token);
      startPolling(state.draftId, state.token);
    }
  }
);

// Listen for messages from content script (errors, multi-file warnings)
chrome.runtime.onMessage.addListener((msg) => {
  if (msg?.type === 'SHOW_ERROR') {
    state.errorMessage = msg.message || 'An error occurred';
    render();
  } else if (msg?.type === 'MULTI_FILE_WARNING') {
    state.multiFileWarning = msg.message || null;
    // Don't re-render immediately — warning shows when processing state renders
  } else if (msg?.type === 'SHOW_LOGIN_PROMPT') {
    // Clear token so login screen shows
    state.token = null;
    render();
  }
});

// Watch for storage changes (e.g., content script just triggered analysis)
chrome.storage.onChanged.addListener((changes) => {
  let changed = false;
  if (changes.noesis_token) { state.token = changes.noesis_token.newValue; changed = true; }
  if (changes.noesis_project_id) { state.projectId = changes.noesis_project_id.newValue; changed = true; }
  if (changes.noesis_current_project_id) { state.currentProjectId = changes.noesis_current_project_id.newValue; changed = true; }
  if (changes.noesis_current_draft_id) {
    const newDraftId = changes.noesis_current_draft_id.newValue;
    if (newDraftId && newDraftId !== state.draftId) {
      state.draftId = newDraftId;
      state.draft = null;
      state.progress = 0;
      state.message = '';
      state.topActions = [];
      if (state.token) {
        connectWebSocket(newDraftId, state.token);
        startPolling(newDraftId, state.token);
      }
    }
    changed = true;
  }
  if (changed) render();
});
