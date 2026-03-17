// Noesis Extension — Overleaf Content Script
(function() {
  'use strict';

  function injectNoesisButton() {
    // Avoid double-injection
    if (document.getElementById('noesis-review-btn')) return;

    // Find the Overleaf toolbar — try multiple selectors for resilience
    const toolbar = document.querySelector('.toolbar-editor') ||
                    document.querySelector('[class*="toolbar"]') ||
                    document.querySelector('.formatting-btn-list');

    if (!toolbar) {
      // Retry after a delay if toolbar not yet rendered
      setTimeout(injectNoesisButton, 2000);
      return;
    }

    const btn = document.createElement('button');
    btn.id = 'noesis-review-btn';
    btn.title = 'Analyze with Noesis';
    btn.innerHTML = `
      <span style="
        display: inline-flex;
        align-items: center;
        gap: 6px;
        background: #E5484D;
        color: white;
        border: none;
        border-radius: 6px;
        padding: 5px 12px;
        font-size: 13px;
        font-weight: 600;
        cursor: pointer;
        font-family: Inter, sans-serif;
        letter-spacing: 0.01em;
      ">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/>
        </svg>
        Noesis Review
      </span>
    `;
    btn.style.cssText = 'background: none; border: none; cursor: pointer; margin-left: 8px;';
    btn.addEventListener('click', extractAndSend);
    toolbar.appendChild(btn);
  }

  function extractLatexContent() {
    // CodeMirror 6 (Overleaf's editor)
    const cmContent = document.querySelector('.cm-content');
    if (cmContent) return cmContent.textContent || '';

    // Fallback: CodeMirror 5
    const cm5 = document.querySelector('.CodeMirror');
    if (cm5 && cm5.CodeMirror) return cm5.CodeMirror.getValue();

    return '';
  }

  function getDocumentTitle() {
    // Try to get from Overleaf page title or project name element
    const titleEl = document.querySelector('.doc-name-input') ||
                    document.querySelector('[class*="doc-name"]') ||
                    document.querySelector('.editor-header-title');
    if (titleEl) return titleEl.value || titleEl.textContent || 'Overleaf Document';

    // Fallback to page title
    const pageTitle = document.title.replace(' - Overleaf, Online LaTeX Editor', '').trim();
    return pageTitle || 'Overleaf Document';
  }

  async function extractAndSend() {
    const content = extractLatexContent();
    if (!content || content.trim().length < 100) {
      alert('Could not extract document content. Please make sure a document is open in the editor.');
      return;
    }

    const title = getDocumentTitle();

    // Get auth token from storage
    chrome.runtime.sendMessage({ type: 'GET_AUTH' }, async (auth) => {
      if (!auth?.noesis_token) {
        // Signal sidebar to show login prompt
        chrome.runtime.sendMessage({ type: 'SHOW_LOGIN_PROMPT' });
        return;
      }

      // Update button to show loading
      const btn = document.getElementById('noesis-review-btn');
      if (btn) btn.querySelector('span').textContent = 'Sending...';

      chrome.runtime.sendMessage(
        {
          type: 'ANALYZE_DOCUMENT',
          payload: {
            content,
            title,
            projectId: auth.noesis_project_id || null,
            token: auth.noesis_token,
          }
        },
        (response) => {
          if (btn) btn.querySelector('span').innerHTML = `
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/>
            </svg>
            Noesis Review
          `;
          if (response?.error) {
            alert('Error sending to Noesis: ' + response.error);
          } else {
            // Open the extension popup to show progress
            chrome.runtime.sendMessage({ type: 'OPEN_SIDEBAR' });
          }
        }
      );
    });
  }

  // Also listen for auth token sync from the Noesis web app
  window.addEventListener('message', (event) => {
    if (event.origin !== 'https://noesis.is') return;
    if (event.data?.type === 'NOESIS_AUTH_TOKEN') {
      chrome.storage.local.set({
        noesis_token: event.data.token,
        noesis_project_id: event.data.projectId || null,
      });
    }
  });

  // Inject on load and watch for SPA navigation
  injectNoesisButton();
  const observer = new MutationObserver(() => injectNoesisButton());
  observer.observe(document.body, { childList: true, subtree: true });
})();
