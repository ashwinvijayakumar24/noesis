// Noesis Extension — Overleaf Content Script
// Multi-file aware: reads active file + parses \input{} references for context
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
      <span id="noesis-review-btn-inner" style="
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

  // ── Content Extraction ──────────────────────────────────────────────────────

  function extractLatexContent() {
    // CodeMirror 6 (current Overleaf editor)
    const cmContent = document.querySelector('.cm-content');
    if (cmContent) return cmContent.textContent || '';

    // Fallback: CodeMirror 5
    const cm5 = document.querySelector('.CodeMirror');
    if (cm5 && cm5.CodeMirror) return cm5.CodeMirror.getValue();

    return '';
  }

  function getDocumentTitle() {
    const titleEl = document.querySelector('.doc-name-input') ||
                    document.querySelector('[class*="doc-name"]') ||
                    document.querySelector('.editor-header-title');
    if (titleEl) return titleEl.value || titleEl.textContent || 'Overleaf Document';

    const pageTitle = document.title.replace(' - Overleaf, Online LaTeX Editor', '').trim();
    return pageTitle || 'Overleaf Document';
  }

  /**
   * Extract currently visible file names from the Overleaf file tree.
   * These are the .tex files in the project sidebar.
   */
  function getVisibleFileNames() {
    const names = [];

    // Try multiple selectors for file tree items (Overleaf changes these)
    const fileItems = document.querySelectorAll(
      '.file-tree-item, [data-test-id="file-tree-item"], [class*="file-tree"] [class*="item"]'
    );

    for (const item of fileItems) {
      const label = item.querySelector('[class*="name"], [class*="label"], span');
      const name = label?.textContent?.trim() || '';
      if (name.endsWith('.tex')) names.push(name);
    }

    return names;
  }

  /**
   * Parse \input{} and \include{} references from a LaTeX document.
   * Returns the list of referenced file names (without .tex extension sometimes).
   */
  function parseInputReferences(latexContent) {
    const refs = [];
    // Match \input{filename}, \include{filename}, \subfile{filename}
    const pattern = /\\(?:input|include|subfile)\{([^}]+)\}/g;
    let match;
    while ((match = pattern.exec(latexContent)) !== null) {
      let ref = match[1].trim();
      if (!ref.endsWith('.tex')) ref += '.tex';
      refs.push(ref);
    }
    return refs;
  }

  /**
   * Build the full content payload for the Noesis backend.
   *
   * Returns:
   *   { content: string, title: string, file_count: number, referenced_files: string[] }
   *
   * We include referenced file names so the backend knows what's missing
   * (files the user hasn't opened yet).
   */
  function buildContentPayload() {
    const activeContent = extractLatexContent();
    const title = getDocumentTitle();
    const referencedFiles = parseInputReferences(activeContent);
    const visibleFiles = getVisibleFileNames();

    // Count how many referenced files we can't read (not the active file)
    const unreadFiles = referencedFiles.filter(
      ref => !title.includes(ref.replace('.tex', ''))
    );

    return {
      content: activeContent,
      title,
      file_count: 1 + unreadFiles.length,   // Total files in project (estimated)
      referenced_files: referencedFiles,     // Files referenced by \input{} etc.
      unread_files: unreadFiles,             // Files not yet read
      is_multi_file: referencedFiles.length > 0,
    };
  }

  // ── Button State ────────────────────────────────────────────────────────────

  function setButtonState(state) {
    const inner = document.getElementById('noesis-review-btn-inner');
    if (!inner) return;

    if (state === 'loading') {
      inner.textContent = 'Sending...';
      inner.style.opacity = '0.7';
    } else if (state === 'success') {
      inner.innerHTML = `
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
        </svg>
        Sent!
      `;
      inner.style.opacity = '1';
      // Reset after 2 seconds
      setTimeout(() => {
        inner.innerHTML = `
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/>
          </svg>
          Noesis Review
        `;
      }, 2000);
    } else {
      // Default / reset
      inner.innerHTML = `
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/>
        </svg>
        Noesis Review
      `;
      inner.style.opacity = '1';
    }
  }

  // ── Main Action ─────────────────────────────────────────────────────────────

  async function extractAndSend() {
    const payload = buildContentPayload();

    if (!payload.content || payload.content.trim().length < 100) {
      // Send message to sidebar to show error (no alert())
      chrome.runtime.sendMessage({
        type: 'SHOW_ERROR',
        message: 'Could not extract document content. Make sure a document is open in the editor.'
      });
      return;
    }

    // Warn if multi-file project — sidebar will show indicator
    if (payload.is_multi_file && payload.unread_files.length > 0) {
      chrome.runtime.sendMessage({
        type: 'MULTI_FILE_WARNING',
        unread_files: payload.unread_files,
        message: `This project has ${payload.file_count} files. Currently analyzing the active file. Open other files to include them in the analysis.`
      });
    }

    // Get auth token from storage
    chrome.runtime.sendMessage({ type: 'GET_AUTH' }, async (auth) => {
      if (!auth?.noesis_token) {
        chrome.runtime.sendMessage({ type: 'SHOW_LOGIN_PROMPT' });
        return;
      }

      setButtonState('loading');

      chrome.runtime.sendMessage(
        {
          type: 'ANALYZE_DOCUMENT',
          payload: {
            content: payload.content,
            title: payload.title,
            projectId: auth.noesis_project_id || null,
            token: auth.noesis_token,
            // Multi-file metadata (for display purposes)
            file_count: payload.file_count,
            referenced_files: payload.referenced_files,
            is_multi_file: payload.is_multi_file,
          }
        },
        (response) => {
          if (response?.error) {
            setButtonState('default');
            chrome.runtime.sendMessage({
              type: 'SHOW_ERROR',
              message: 'Error sending to Noesis: ' + response.error
            });
          } else {
            setButtonState('success');
            chrome.runtime.sendMessage({ type: 'OPEN_SIDEBAR' });
          }
        }
      );
    });
  }

  // Also listen for TRIGGER_ANALYZE from sidebar "Analyze Draft" button
  chrome.runtime.onMessage.addListener((msg) => {
    if (msg?.type === 'TRIGGER_ANALYZE') {
      extractAndSend();
    }
  });

  // Auth token sync from Noesis web app
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
