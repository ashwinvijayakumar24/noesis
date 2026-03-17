import { useEffect, useRef, useState } from 'react';
import { supabase } from '../lib/supabase';

interface AnalysisStreamState {
  progress: number;
  step: string;
  message: string;
  complete: boolean;
  error: string | null;
}

export function useAnalysisStream(draftId: string | null, enabled: boolean) {
  const [state, setState] = useState<AnalysisStreamState>({
    progress: 0,
    step: '',
    message: '',
    complete: false,
    error: null,
  });
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!draftId || !enabled) return;

    let cancelled = false;

    async function connect() {
      const { data: { session } } = await supabase.auth.getSession();
      const token = session?.access_token;
      if (!token || cancelled) return;

      const wsBase = import.meta.env.VITE_API_URL?.replace('http', 'ws').replace('https', 'wss') ?? 'ws://localhost:8000';
      const url = `${wsBase}/drafts/${draftId}/analysis-stream?token=${token}`;

      try {
        const ws = new WebSocket(url);
        wsRef.current = ws;

        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            setState(prev => ({
              ...prev,
              progress: data.progress ?? prev.progress,
              step: data.step ?? prev.step,
              message: data.message ?? prev.message,
              complete: (data.progress ?? 0) >= 100,
            }));
          } catch {
            // ignore malformed messages
          }
        };

        ws.onerror = () => {
          if (!cancelled) setState(prev => ({ ...prev, error: 'Stream unavailable' }));
        };

        ws.onclose = () => {
          if (!cancelled) setState(prev => ({ ...prev, complete: prev.progress >= 100 || prev.complete }));
        };
      } catch {
        if (!cancelled) setState(prev => ({ ...prev, error: 'WebSocket not supported' }));
      }
    }

    connect();

    return () => {
      cancelled = true;
      wsRef.current?.close();
    };
  }, [draftId, enabled]);

  return state;
}
