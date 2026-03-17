// Noesis Extension — Background Service Worker
const API_BASE = 'https://api.noesis.is';

// Listen for messages from content script or sidebar
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === 'ANALYZE_DOCUMENT') {
    handleAnalyzeDocument(message.payload).then(sendResponse).catch(err => {
      sendResponse({ error: err.message });
    });
    return true; // Keep message channel open for async response
  }

  if (message.type === 'GET_AUTH') {
    chrome.storage.local.get(['noesis_token', 'noesis_project_id'], (result) => {
      sendResponse(result);
    });
    return true;
  }

  if (message.type === 'GET_DRAFT_STATUS') {
    getDraftStatus(message.draftId, message.token).then(sendResponse).catch(err => {
      sendResponse({ error: err.message });
    });
    return true;
  }
});

async function handleAnalyzeDocument({ content, title, projectId, token }) {
  const response = await fetch(`${API_BASE}/drafts/analyze-from-extension`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
    },
    body: JSON.stringify({ content, title, project_id: projectId }),
  });

  if (!response.ok) {
    const err = await response.text();
    throw new Error(`API error ${response.status}: ${err}`);
  }

  const data = await response.json();
  // Store draft_id for sidebar to poll
  await chrome.storage.local.set({ noesis_current_draft_id: data.draft_id, noesis_current_project_id: data.project_id });
  return data;
}

async function getDraftStatus(draftId, token) {
  const response = await fetch(`${API_BASE}/drafts/${draftId}`, {
    headers: { 'Authorization': `Bearer ${token}` },
  });
  if (!response.ok) throw new Error(`Status check failed: ${response.status}`);
  return response.json();
}
