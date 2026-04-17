import { useEffect, useRef, useCallback, useState } from 'react';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/vibecoding';
const WS_BASE_URL = API_BASE_URL.replace(/^http/, 'ws');

/**
 * Custom hook for WebSocket connection with automatic reconnection
 * @param {string} projectId - The project ID to connect to
 * @param {function} onMessage - Callback when a message is received
 * @param {boolean} enabled - Whether the WebSocket should be active
 */
export const useWebSocket = (projectId, onMessage, enabled = true) => {
  const wsRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);
  const [isConnected, setIsConnected] = useState(false);
  const [reconnectAttempts, setReconnectAttempts] = useState(0);
  const maxReconnectAttempts = 5;
  const reconnectDelay = 2000; // 2 seconds

  const connect = useCallback(() => {
    if (!projectId || !enabled) return;

    try {
      const wsUrl = `${WS_BASE_URL}/ws/${projectId}`;
      console.log('🔌 Connecting to WebSocket:', wsUrl);
      
      const ws = new WebSocket(wsUrl);
      
      ws.onopen = () => {
        console.log('✅ WebSocket connected for project:', projectId);
        setIsConnected(true);
        setReconnectAttempts(0);
        
        // Send heartbeat every 30 seconds to keep connection alive
        const heartbeatInterval = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'ping' }));
          }
        }, 30000);
        
        ws.heartbeatInterval = heartbeatInterval;
      };
      
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          
          // Ignore pong messages
          if (data.type === 'pong') return;
          
          console.log('📨 WebSocket message received:', data);
          
          if (onMessage) {
            onMessage(data);
          }
        } catch (error) {
          console.error('Failed to parse WebSocket message:', error);
        }
      };
      
      ws.onerror = (error) => {
        console.error('❌ WebSocket error:', error);
        setIsConnected(false);
      };
      
      ws.onclose = () => {
        console.log('🔌 WebSocket disconnected');
        setIsConnected(false);
        
        // Clear heartbeat interval
        if (ws.heartbeatInterval) {
          clearInterval(ws.heartbeatInterval);
        }
        
        // Attempt to reconnect if enabled and under max attempts
        if (enabled && reconnectAttempts < maxReconnectAttempts) {
          console.log(`🔄 Reconnecting in ${reconnectDelay}ms... (attempt ${reconnectAttempts + 1}/${maxReconnectAttempts})`);
          reconnectTimeoutRef.current = setTimeout(() => {
            setReconnectAttempts(prev => prev + 1);
            connect();
          }, reconnectDelay);
        } else if (reconnectAttempts >= maxReconnectAttempts) {
          console.log('⚠️ Max reconnection attempts reached. Falling back to polling.');
        }
      };
      
      wsRef.current = ws;
    } catch (error) {
      console.error('Failed to create WebSocket connection:', error);
      setIsConnected(false);
    }
  }, [projectId, enabled, onMessage, reconnectAttempts]);

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
    }
    
    if (wsRef.current) {
      // Clear heartbeat interval
      if (wsRef.current.heartbeatInterval) {
        clearInterval(wsRef.current.heartbeatInterval);
      }
      
      wsRef.current.close();
      wsRef.current = null;
    }
    
    setIsConnected(false);
    setReconnectAttempts(0);
  }, []);

  useEffect(() => {
    if (enabled && projectId) {
      connect();
    }
    
    return () => {
      disconnect();
    };
  }, [projectId, enabled]);

  return {
    isConnected,
    reconnectAttempts,
    disconnect
  };
};
