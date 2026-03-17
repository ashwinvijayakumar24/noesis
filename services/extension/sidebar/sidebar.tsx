import React, { useEffect, useState, useCallback } from 'react';
import { createRoot } from 'react-dom/client';

const API_BASE = 'https://api.noesis.is';
const NOESIS_BASE = 'https://noesis.is';

interface DraftStatus {
  id: string;
  status: 'pending' | 'processing' | 'analyzed' | 'failed';
  title: string;
  project_id?: string;
}

interface AuthState {
  noesis_token?: string;
  noesis_project_id?: string;
  noesis_current_draft_id?: string;
  noesis_current_project_id?: string;
}

interface StreamState {
  progress: number;
  message: string;
}

function App() {
  const [auth, setAuth] = useState<AuthState>({});
  const [draft, setDraft] = useState<DraftStatus | null>(null);
  const [stream, setStream] = useState<StreamState>({ progress: 0, message: '' });
  const [topActions, setTopActions] = useState<string[]>([]);
  const [wsConnected, setWsConnected] = useState(false);

  // Load auth + current draft from storage
  useEffect(() => {
    chrome.storage.local.get(
      ['noesis_token', 'noesis_project_id', 'noesis_current_draft_id', 'noesis_current_project_id'],
      (result) => setAuth(result as AuthState)
    );
    // Watch for storage changes (e.g., after content script triggers analysis)
    chrome.storage.onChanged.addListener((changes) => {
      const updated: Partial<AuthState> = {};
      for (const [key, { newValue }] of Object.entries(changes)) {
        (updated as Record<string, unknown>)[key] = newValue;
      }
      setAuth(prev => ({ ...prev, ...updated }));
    });
  }, []);

  // Poll draft status every 5s while processing
  useEffect(() => {
    if (!auth.noesis_current_draft_id || !auth.noesis_token) return;
    if (draft?.status === 'analyzed' || draft?.status === 'failed') return;

    const interval = setInterval(async () => {
      try {
        const resp = await fetch(`${API_BASE}/drafts/${auth.noesis_current_draft_id}`, {
          headers: { Authorization: `Bearer ${auth.noesis_token}` },
        });
        if (resp.ok) {
          const data = await resp.json();
          setDraft(data);
          if (data.status === 'analyzed') {
            clearInterval(interval);
            fetchTopActions(data.id);
          }
        }
      } catch {
        // network error — keep polling
      }
    }, 5000);

    return () => clearInterval(interval);
  }, [auth.noesis_current_draft_id, auth.noesis_token, draft?.status]);

  // Connect WebSocket for live progress
  useEffect(() => {
    if (!auth.noesis_current_draft_id || !auth.noesis_token) return;
    if (draft?.status === 'analyzed' || draft?.status === 'failed') return;

    const wsUrl = `wss://api.noesis.is/drafts/${auth.noesis_current_draft_id}/analysis-stream?token=${auth.noesis_token}`;
    let ws: WebSocket;
    try {
      ws = new WebSocket(wsUrl);
      setWsConnected(true);
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          setStream({ progress: data.progress ?? 0, message: data.message ?? '' });
        } catch { /* ignore */ }
      };
      ws.onerror = () => setWsConnected(false);
      ws.onclose = () => setWsConnected(false);
    } catch {
      setWsConnected(false);
    }
    return () => ws?.close();
  }, [auth.noesis_current_draft_id, auth.noesis_token]);

  const fetchTopActions = async (draftId: string) => {
    try {
      const resp = await fetch(`${API_BASE}/drafts/${draftId}/feedback?limit=3`, {
        headers: { Authorization: `Bearer ${auth.noesis_token}` },
      });
      if (resp.ok) {
        const data = await resp.json();
        const items = (data.feedback || data.items || data || []).slice(0, 3);
        setTopActions(items.map((f: { feedback_text?: string; text?: string }) => f.feedback_text || f.text || '').filter(Boolean));
      }
    } catch { /* ignore */ }
  };

  const handleLogin = () => {
    chrome.tabs.create({ url: `${NOESIS_BASE}/login` });
  };

  const handleAnalyze = useCallback(() => {
    // Tell content script to extract and analyze
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      if (tabs[0]?.id) {
        chrome.tabs.sendMessage(tabs[0].id, { type: 'TRIGGER_ANALYZE' });
      }
    });
  }, []);

  const isLoggedIn = !!auth.noesis_token;
  const isProcessing = draft?.status === 'processing' || draft?.status === 'pending';
  const isComplete = draft?.status === 'analyzed';

  return (
    <div style={{
      width: 380,
      minHeight: 500,
      background: '#0F0F14',
      color: '#E8E8F0',
      fontFamily: 'Inter, system-ui, sans-serif',
      padding: '20px',
      boxSizing: 'border-box',
    }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 24 }}>
        <div style={{ width: 32, height: 32, background: '#E5484D', borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <span style={{ color: 'white', fontSize: 16, fontWeight: 700 }}>N</span>
        </div>
        <div>
          <div style={{ fontWeight: 600, fontSize: 15 }}>Noesis</div>
          <div style={{ fontSize: 11, color: '#6B6B7E' }}>Research Review</div>
        </div>
      </div>

      {!isLoggedIn && (
        <div style={{ textAlign: 'center', padding: '40px 0' }}>
          <p style={{ color: '#9898A8', fontSize: 14, marginBottom: 20, lineHeight: 1.6 }}>
            Log in to Noesis to analyze your Overleaf drafts with expert reviewer-style feedback.
          </p>
          <button onClick={handleLogin} style={{
            background: '#E5484D',
            color: 'white',
            border: 'none',
            borderRadius: 8,
            padding: '10px 24px',
            fontWeight: 600,
            fontSize: 14,
            cursor: 'pointer',
          }}>
            Log in to Noesis
          </button>
        </div>
      )}

      {isLoggedIn && !draft && (
        <div style={{ textAlign: 'center', padding: '40px 0' }}>
          <p style={{ color: '#9898A8', fontSize: 14, marginBottom: 20, lineHeight: 1.6 }}>
            Open an Overleaf project and click the <strong style={{ color: '#E8E8F0' }}>Noesis Review</strong> button in the editor toolbar to analyze your draft.
          </p>
          <button onClick={handleAnalyze} style={{
            background: '#E5484D',
            color: 'white',
            border: 'none',
            borderRadius: 8,
            padding: '10px 24px',
            fontWeight: 600,
            fontSize: 14,
            cursor: 'pointer',
          }}>
            Analyze Draft
          </button>
        </div>
      )}

      {isLoggedIn && draft && isProcessing && (
        <div style={{ padding: '20px 0' }}>
          <p style={{ fontSize: 14, fontWeight: 600, marginBottom: 12 }}>Analyzing: {draft.title}</p>
          <div style={{ background: '#18181F', borderRadius: 999, height: 8, overflow: 'hidden', marginBottom: 8 }}>
            <div style={{
              height: '100%',
              background: '#E5484D',
              width: `${stream.progress}%`,
              borderRadius: 999,
              transition: 'width 0.3s ease',
            }} />
          </div>
          <p style={{ fontSize: 12, color: '#6B6B7E', marginTop: 4 }}>
            {stream.message || 'Analyzing draft...'} {stream.progress > 0 ? `(${stream.progress}%)` : ''}
          </p>
          {!wsConnected && (
            <p style={{ fontSize: 11, color: '#4B4B5E', marginTop: 8 }}>Polling for updates...</p>
          )}
        </div>
      )}

      {isLoggedIn && draft && isComplete && (
        <div style={{ padding: '10px 0' }}>
          <p style={{ fontSize: 14, fontWeight: 600, color: '#5BE56B', marginBottom: 16 }}>
            Analysis complete
          </p>

          {topActions.length > 0 && (
            <div style={{ marginBottom: 20 }}>
              <p style={{ fontSize: 12, fontWeight: 600, color: '#9898A8', marginBottom: 10, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                Top Action Items
              </p>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {topActions.map((action, i) => (
                  <div key={i} style={{
                    background: '#18181F',
                    border: '1px solid rgba(255,255,255,0.08)',
                    borderRadius: 8,
                    padding: '10px 12px',
                    fontSize: 13,
                    color: '#C8C8D8',
                    lineHeight: 1.5,
                  }}>
                    {action}
                  </div>
                ))}
              </div>
            </div>
          )}

          <a
            href={`${NOESIS_BASE}/projects/${draft.project_id ?? auth.noesis_current_project_id}/drafts/${draft.id}`}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              display: 'block',
              background: '#E5484D',
              color: 'white',
              borderRadius: 8,
              padding: '10px 16px',
              textAlign: 'center',
              textDecoration: 'none',
              fontWeight: 600,
              fontSize: 14,
            }}
            onClick={(e) => {
              e.preventDefault();
              chrome.tabs.create({ url: `${NOESIS_BASE}/projects/${draft.project_id ?? auth.noesis_current_project_id}/drafts/${draft.id}` });
            }}
          >
            View Full Analysis
          </a>
        </div>
      )}

      {isLoggedIn && draft?.status === 'failed' && (
        <div style={{ padding: '20px 0', textAlign: 'center' }}>
          <p style={{ color: '#E5484D', fontSize: 14, marginBottom: 16 }}>Analysis failed. Please try again.</p>
          <button onClick={handleAnalyze} style={{
            background: '#18181F',
            color: '#E8E8F0',
            border: '1px solid rgba(255,255,255,0.12)',
            borderRadius: 8,
            padding: '10px 24px',
            fontWeight: 600,
            fontSize: 14,
            cursor: 'pointer',
          }}>
            Retry
          </button>
        </div>
      )}
    </div>
  );
}

const root = document.getElementById('root');
if (root) createRoot(root).render(<App />);
