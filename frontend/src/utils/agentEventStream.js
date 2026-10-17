/**
 * Durable SSE Agent Event Stream Reader
 *
 * Connects to the backend EventBroadcaster SSE endpoint with automatic replay,
 * exponential backoff, visibility-change reconnection, and keep-alive tracking.
 * Modeled on Vibe_lite's streamSessionEvents architecture.
 */

import { API_ENDPOINTS } from '../config';

/**
 * Fetch buffered agent logs snapshot for instant zero-latency initial render.
 */
export async function fetchBufferedAgentLogs(projectToken, token = null) {
  try {
    const url = API_ENDPOINTS.AGENT_LOGS_BUFFERED(projectToken);
    const headers = {};
    if (token) headers['Authorization'] = `Bearer ${token}`;
    const res = await fetch(url, { headers });
    if (!res.ok) return [];
    const data = await res.json();
    return Array.isArray(data.events) ? data.events : [];
  } catch (err) {
    console.warn('[AgentEventStream] Failed to fetch initial buffered logs:', err);
    return [];
  }
}

/**
 * Stream live agent events with auto-reconnect, Last-Event-ID replay, and visibility resumption.
 * Returns an abort cleanup function.
 */
export function streamAgentEvents(projectToken, {
  onEvent,
  onDone,
  onError,
  onReconnect,
  onReconnecting,
  token = null,
} = {}) {
  const controller = new AbortController();
  let lastEventId = null;
  let retryCount = 0;
  const maxRetries = 25;
  const BASE_DELAY = 1200;
  const MAX_DELAY = 15000;

  const getDelay = () => Math.min(BASE_DELAY * Math.pow(1.4, retryCount - 1), MAX_DELAY);

  let visibilityAbort = null;
  const onVisibilityChange = () => {
    if (document.visibilityState === 'visible' && visibilityAbort) {
      visibilityAbort();
      visibilityAbort = null;
    }
  };
  document.addEventListener('visibilitychange', onVisibilityChange);

  (async () => {
    try {
      while (retryCount <= maxRetries && !controller.signal.aborted) {
        try {
          const baseUrl = API_ENDPOINTS.AGENT_EVENTS_STREAM(projectToken);
          const url = lastEventId !== null
            ? `${baseUrl}?last_event_id=${lastEventId}`
            : baseUrl;

          const headers = {};
          if (token) headers['Authorization'] = `Bearer ${token}`;
          if (lastEventId !== null) headers['Last-Event-ID'] = String(lastEventId);

          const resp = await fetch(url, {
            headers,
            signal: controller.signal,
          });

          if (!resp.ok || !resp.body) {
            throw new Error(`SSE HTTP error ${resp.status}`);
          }

          const reader = resp.body.getReader();
          const decoder = new TextDecoder();
          let buffer = '';
          let currentId = null;

          const parseLine = (line) => {
            if (line.startsWith('id:')) {
              const raw = line.slice(3).trim();
              if (raw && !isNaN(Number(raw))) {
                currentId = Number(raw);
              }
              return;
            }
            if (!line.startsWith('data:')) return;
            const dataStr = line.slice(5).trim();
            if (!dataStr) return;

            try {
              const parsed = JSON.parse(dataStr);
              if (currentId !== null) {
                parsed._clientId = currentId;
                lastEventId = currentId;
              }
              if (onEvent) onEvent(parsed);
            } catch (jsonErr) {
              // Ignore ping or keepalive malformed frame
            }
          };

          // Successfully connected / resumed
          retryCount = 0;
          if (onReconnect && lastEventId !== null) {
            onReconnect();
          }

          while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const frames = buffer.split('\n\n');
            buffer = frames.pop() || '';
            frames.forEach((frame) => {
              currentId = null;
              frame.split('\n').forEach(parseLine);
            });
          }

          if (onDone) onDone();
          document.removeEventListener('visibilitychange', onVisibilityChange);
          return;

        } catch (streamErr) {
          if (controller.signal.aborted) break;
          retryCount++;
          if (retryCount > maxRetries) {
            if (onError) onError(streamErr);
            break;
          }

          if (onReconnecting) onReconnecting(retryCount);

          const delay = getDelay();
          await new Promise((resolve) => {
            const timer = setTimeout(resolve, delay);
            visibilityAbort = () => {
              clearTimeout(timer);
              resolve();
            };
          });
        }
      }
    } catch (fatalErr) {
      if (!controller.signal.aborted && onError) {
        onError(fatalErr);
      }
    } finally {
      document.removeEventListener('visibilitychange', onVisibilityChange);
    }
  })();

  return () => {
    controller.abort();
    document.removeEventListener('visibilitychange', onVisibilityChange);
  };
}
