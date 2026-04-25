/**
 * useWebSocket.js — Vibecoding real-time update hook
 *
 * Connects to /vibecoding/ws/{projectId} and exposes the last received message.
 * Handles reconnection automatically so the tab never needs a refresh.
 *
 * Usage:
 *   const { lastMessage, isConnected } = useWebSocket(projectId);
 */

import { useEffect, useRef, useState, useCallback } from 'react';

const WS_BASE = (() => {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
  return `${proto}://${window.location.host}/vibecoding/ws`;
})();

const HEARTBEAT_INTERVAL_MS = 25_000; // send ping every 25 s
const RECONNECT_BASE_MS      = 1_500;  // first reconnect after 1.5 s
const RECONNECT_MAX_MS       = 30_000; // cap reconnect delay at 30 s
const RECONNECT_JITTER_MS    = 500;    // ± jitter to avoid thundering herd

export function useWebSocket(projectId) {
  const wsRef              = useRef(null);
  const heartbeatRef       = useRef(null);
  const reconnectTimerRef  = useRef(null);
  const reconnectDelay     = useRef(RECONNECT_BASE_MS);
  const isMounted          = useRef(true);

  const [lastMessage,  setLastMessage]  = useState(null);
  const [isConnected,  setIsConnected]  = useState(false);

  const clearHeartbeat = () => {
    if (heartbeatRef.current) {
      clearInterval(heartbeatRef.current);
      heartbeatRef.current = null;
    }
  };

  const clearReconnectTimer = () => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
  };

  const connect = useCallback(() => {
    if (!projectId || !isMounted.current) return;

    // Don't open a second socket if one is already open/connecting
    if (wsRef.current && (wsRef.current.readyState === WebSocket.OPEN ||
                          wsRef.current.readyState === WebSocket.CONNECTING)) {
      return;
    }

    const url = `${WS_BASE}/${projectId}`;
    console.log(`[WS] Connecting → ${url}`);

    let ws;
    try {
      ws = new WebSocket(url);
    } catch (err) {
      console.error('[WS] Failed to construct WebSocket:', err);
      scheduleReconnect();
      return;
    }

    wsRef.current = ws;

    ws.onopen = () => {
      if (!isMounted.current) { ws.close(); return; }
      console.log(`[WS] ✅ Connected (project: ${projectId})`);
      setIsConnected(true);
      reconnectDelay.current = RECONNECT_BASE_MS; // reset backoff on success

      // Start heartbeat — server echoes "pong" to keep NAT/proxy alive
      clearHeartbeat();
      heartbeatRef.current = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'ping', timestamp: new Date().toISOString() }));
        }
      }, HEARTBEAT_INTERVAL_MS);
    };

    ws.onmessage = (event) => {
      if (!isMounted.current) return;
      try {
        const data = JSON.parse(event.data);
        console.log('[WS] Raw message received:', data);
        // Ignore server-side pong heartbeats — they carry no UI data
        if (data?.type === 'pong') return;
        setLastMessage(data);
      } catch (err) {
        console.warn('[WS] Failed to parse message:', err, 'Raw:', event.data);
        // Non-JSON frame — ignore silently
      }
    };

    ws.onerror = (err) => {
      console.warn('[WS] Error:', err);
      // onclose fires immediately after onerror, so reconnect happens there
    };

    ws.onclose = (event) => {
      clearHeartbeat();
      setIsConnected(false);
      if (!isMounted.current) return;
      console.log(`[WS] Closed (code ${event.code}). Reconnecting in ${reconnectDelay.current}ms…`);
      scheduleReconnect();
    };
  }, [projectId]); // eslint-disable-line react-hooks/exhaustive-deps

  const scheduleReconnect = useCallback(() => {
    clearReconnectTimer();
    if (!isMounted.current || !projectId) return;
    const jitter  = Math.random() * RECONNECT_JITTER_MS * 2 - RECONNECT_JITTER_MS;
    const delay   = Math.min(reconnectDelay.current + jitter, RECONNECT_MAX_MS);
    reconnectDelay.current = Math.min(reconnectDelay.current * 2, RECONNECT_MAX_MS);
    reconnectTimerRef.current = setTimeout(connect, delay);
  }, [connect, projectId]);

  // Re-connect whenever projectId changes (or on first mount)
  useEffect(() => {
    isMounted.current = true;

    if (!projectId) return;

    // Close previous connection cleanly before opening a new one
    if (wsRef.current) {
      wsRef.current.onclose = null; // suppress reconnect for the old socket
      wsRef.current.close();
      wsRef.current = null;
      clearHeartbeat();
      clearReconnectTimer();
      reconnectDelay.current = RECONNECT_BASE_MS;
    }

    setIsConnected(false);
    setLastMessage(null);
    connect();

    return () => {
      isMounted.current = false;
      clearHeartbeat();
      clearReconnectTimer();
      if (wsRef.current) {
        wsRef.current.onclose = null; // don't trigger reconnect on unmount
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [projectId]); // eslint-disable-line react-hooks/exhaustive-deps

  return { lastMessage, isConnected };
}