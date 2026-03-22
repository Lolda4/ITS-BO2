"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { API_BASE } from "./config";
import type { SSEMetricEvent } from "./types";

/**
 * SSE hook for live session metrics.
 * Auto-reconnects up to 5 times, cleans up on unmount.
 *
 * EventSource runs cross-origin (:3000 → :8000).
 * Backend CORS must allow *, without credentials.
 * DO NOT set withCredentials — that would require specific origin.
 */
export function useSessionSSE(sessionId: string | null) {
  const [metrics, setMetrics]   = useState<SSEMetricEvent | null>(null);
  const [error, setError]       = useState<string | null>(null);
  const [connected, setConnected] = useState(false);
  const esRef    = useRef<EventSource | null>(null);
  const retryRef = useRef(0);

  const close = useCallback(() => {
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }
    setConnected(false);
  }, []);

  useEffect(() => {
    if (!sessionId) { close(); return; }

    const connect = () => {
      close();
      const url = `${API_BASE}/api/v1/session/status/${sessionId}`;
      const es = new EventSource(url);
      esRef.current = es;

      es.onopen = () => {
        setConnected(true);
        setError(null);
        retryRef.current = 0;
      };

      es.onmessage = (ev) => {
        try {
          const data: SSEMetricEvent = JSON.parse(ev.data);
          setMetrics(data);

          // Auto-close if terminal state
          if (data.state === "COMPLETED" || data.state === "ERROR" || data.state === "INTERRUPTED") {
            // Keep last metrics, do not auto-close — user may want to see final values
          }
        } catch {
          // ignore malformed event
        }
      };

      es.onerror = () => {
        es.close();
        setConnected(false);
        if (retryRef.current < 5) {
          retryRef.current += 1;
          setTimeout(connect, 2000 * retryRef.current);
        } else {
          setError("SSE connection lost after 5 retries");
        }
      };
    };

    connect();
    return close;
  }, [sessionId, close]);

  return { metrics, error, connected, close };
}
