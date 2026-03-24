# Overleaf Integration Research

**Date**: March 2026
**Status**: Extension functional (single-file). Multi-file support added in this PR.
**Author**: Noesis engineering

---

## 1. Technical Feasibility

### What We Can Do Today (✅ Working)
- **Read editor content**: CodeMirror 6 (Overleaf's editor) exposes text via `.cm-content` element. `textContent` extraction works reliably.
- **DOM injection**: We inject a "Noesis Review" button into the Overleaf toolbar. MutationObserver handles SPA navigation.
- **Content scripts**: Standard Chrome extension content scripts run on `overleaf.com` with no special permissions.
- **Auth bridge**: Auth tokens sync from the Noesis web app via `window.postMessage`.

### What We Can't Do Today (❌ Limitations)
- **Multi-file projects**: Overleaf LaTeX projects span many `.tex` files. The current extension reads only the active file.
- **Real-time suggestions**: We do a single synchronous POST. True real-time would require WebSocket streaming from the backend (WebSocket endpoint exists but not wired to extension yet).
- **PDF compilation**: We can't access the compiled PDF — only the source LaTeX.
- **File tree navigation**: The Overleaf file tree DOM is accessible but requires iterating through `.file-tree-item` elements and clicking to open each file.

---

## 2. Overleaf Terms of Service Analysis

### Key ToS Provisions (as of 2026)
Overleaf's Terms of Service (https://www.overleaf.com/legal) do **not** explicitly prohibit:
- Browser extensions that read editor content for **personal, non-commercial productivity use**
- Extensions that operate on behalf of the authenticated user to analyze their own content

### What Is Prohibited
- Automated scraping at scale (not applicable — we read on user click)
- Reverse engineering their API (not applicable — we use DOM, not their private API)
- Selling Overleaf's data to third parties (we store user's own content, not Overleaf's)

### Risk Assessment
**Low risk** for current use case:
- User explicitly clicks "Noesis Review" to trigger extraction
- We process the user's own LaTeX source code
- No mass scraping, no API abuse, no automated access
- Similar to Grammarly, Writefull, and other extensions that read Overleaf content

### Precedent: Writefull
Writefull (acquired by Digital Science 2021) has a Chrome extension that reads Overleaf editor content and provides inline suggestions. They appear to operate under the same DOM reading approach. Later they obtained "integration partner" status with Overleaf, giving them deeper embed access. This is the path for us too if we grow.

---

## 3. Multi-File Support Architecture

### Challenge
Real LaTeX papers span multiple files:
```
main.tex          ← root document
chapters/
  introduction.tex
  methods.tex
  results.tex
bibliography.bib
```

The Overleaf file tree is rendered in the left sidebar as `.file-tree-item` elements.

### Implementation Strategy (Added in This PR)

#### File Tree Extraction
```javascript
function extractAllProjectFiles() {
  const fileItems = document.querySelectorAll('.file-tree-item[data-file-id]');
  // OR:
  const fileItems = document.querySelectorAll('[data-test-id="file-tree-item"]');

  const files = {};
  for (const item of fileItems) {
    const fileName = item.querySelector('.file-tree-item-label')?.textContent?.trim();
    if (!fileName?.endsWith('.tex')) continue;

    // Click to open, read content, click back
    // Problem: async navigation + CodeMirror re-render takes ~200ms per file
  }
}
```

#### Fallback: Regex Parsing
Instead of navigating to each file, parse `\input{filename}` and `\include{filename}` commands from the root document and extract all referenced files by their names.

#### Recommended Approach (Implemented)
1. Read current active file content
2. Parse `\input{}` / `\include{}` references
3. Extract referenced file names from file tree DOM (don't navigate to them)
4. Send as `{ filename: content }` map — use active file content for referenced files not yet visited
5. Show indicator: "Analyzing 1/5 files — open each file to include its content"

This is a practical compromise: the user controls which files get included by opening them.

### Better Long-Term Approach
Use Overleaf's **project export** endpoint (not part of public API, but extractable from network logs):
```
GET https://www.overleaf.com/project/{projectId}/download/zip
```
This downloads the entire project as a ZIP. The extension could intercept this (with user permission) or trigger it programmatically. However, this requires the user to have download permissions and would be flagged as suspicious behavior by Overleaf's security systems.

---

## 4. Real-Time Suggestions Architecture

### Current Flow (Synchronous)
```
User clicks "Noesis Review"
  → Extract LaTeX content
  → POST /drafts (create draft record)
  → POST /drafts/{id}/analyze (trigger analysis)
  → Poll every 5s for status
  → Show results when analyzed
```

### Desired Flow (Real-Time)
```
User writes in Overleaf
  → Content script detects significant change (debounce 3s)
  → POST to Noesis analysis stream
  → Extension sidebar receives streaming tokens via WebSocket
  → Show inline suggestions as they arrive
```

### Implementation Requirements
1. **Backend**: WebSocket endpoint at `/drafts/{id}/analysis-stream` (exists ✅)
2. **Extension**: Connect WebSocket in sidebar.js (implemented ✅)
3. **Debouncing**: Don't analyze on every keystroke — only after 3s pause or explicit click
4. **Token budget**: GPT-5.2 streaming costs ~2x per token vs batched. Need to use GPT-5-mini for real-time suggestions.
5. **Rate limiting**: 1 analysis per 30s to prevent cost explosion

**Status**: Backend WebSocket exists. Extension polls and connects WebSocket. Real-time automatic triggering (without user click) is not implemented — waiting for GPT-5-mini integration to control costs.

---

## 5. Zotero Connector Integration

### Zotero Local HTTP Server
The Zotero desktop app runs a local HTTP server on port **23119**:
- `GET http://localhost:23119/connector/ping` — returns Zotero version if running
- `POST http://localhost:23119/connector/saveSnapshot` — save current page to Zotero
- This is the Zotero Connector protocol (documented at https://github.com/zotero/zotero-connectors)

### Extension → Zotero Bridge
The Noesis extension could check if Zotero is running locally and offer "Save to Zotero" from the analysis results sidebar:
```javascript
async function checkZoteroRunning() {
  try {
    const resp = await fetch('http://localhost:23119/connector/ping');
    return resp.ok;
  } catch {
    return false; // Zotero not running
  }
}
```

**Use case**: User is in Overleaf, runs Noesis analysis, sees "You're missing Smith et al. (2024)" suggestion, clicks "Add to Zotero" from the extension sidebar → Noesis sends the paper metadata to Zotero via port 23119.

**Status**: Research complete. Implementation not done yet — pending prioritization.

---

## 6. Overleaf Integration Partner Program

### What It Is
Overleaf has an official integration partner program. Companies like Writefull and Research Rabbit have deeper integration access through this program.

### What Partners Get
- Embedded sidebar (not just toolbar button — a dedicated panel)
- Access to project metadata (title, collaborators, change history)
- Potentially: access to compiled PDF
- Marketing placement on Overleaf's integrations page
- Co-marketing opportunities

### How to Apply
Contact: partnerships@overleaf.com
Requirements: Established user base, demonstrated research tool value, compliance with data handling requirements

### Our Path
1. **Now**: Extension with DOM reading (current approach)
2. **Month 3-6**: Apply for integration partner status when we have 500+ users using the Overleaf extension
3. **Month 6+**: If accepted, build embedded sidebar with richer integration

---

## 7. Known Risks & Mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Overleaf DOM change breaks selectors | Medium (every ~6 months) | High | Multiple fallback selectors + MutationObserver |
| Overleaf blocks extension | Low | High | Stay below ToS limits, pursue partnership |
| CodeMirror version upgrade | Low | High | Detect CM version, maintain separate code paths |
| User privacy concerns | Low | Medium | Clear privacy disclosure in extension popup |

---

## 8. Current Extension Limitations (Prioritized Fixes)

| Priority | Issue | Fix |
|----------|-------|-----|
| P0 | Single-file only | Multi-file extraction (added this PR) |
| P1 | `alert()` for errors | Proper sidebar UX (added this PR) |
| P1 | No visual feedback during analysis | Progress bar in sidebar (implemented ✅) |
| P2 | No retry on failure | Retry button in sidebar (implemented ✅) |
| P3 | No real-time suggestions | Requires cost analysis + GPT-5-mini |
| P4 | File tree navigation for full content | Requires complex async DOM navigation |

---

## 9. Recommendation

**Short term (now → Month 2)**:
- Ship multi-file awareness (read `\input{}` references)
- Improve sidebar UX (no alerts, better progress)
- Focus on making single-file analysis excellent — most Overleaf papers keep everything in one file for submission

**Medium term (Month 3-6)**:
- Apply for Overleaf integration partner status
- Add real-time suggestions with debouncing (GPT-5-mini for cost control)
- Add "Save suggested paper to Zotero" via port 23119

**Long term (Month 6+)**:
- If partner: embedded sidebar with full project access
- If not: continue extension approach, expand fallback selectors
