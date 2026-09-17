import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { 
  LifeBuoy, Plus, Search, Filter, CheckCircle2, Clock, 
  AlertCircle, RefreshCw, Send, Shield, Building2, User, 
  Lock, MessageSquare, Check, X, Flame, Sparkles, Copy, 
  Tag, Activity, ChevronDown, CheckCircle, ArrowLeft, Radio, FileText, Ticket
} from 'lucide-react';
import { API_ENDPOINTS } from '../config';
import { soundNotifier } from '../utils/notificationSound';

const CATEGORIES = [
  { id: 'Agent Allocation', label: 'Agent Allocation & Capacity', icon: '🤖', color: 'from-purple-500/20 to-indigo-500/20 text-purple-300 border-purple-500/30' },
  { id: 'Technical Issue', label: 'Technical & Code Generation', icon: '🔧', color: 'from-blue-500/20 to-cyan-500/20 text-blue-300 border-blue-500/30' },
  { id: 'Account & Billing', label: 'Account, Tokens & Billing', icon: '💳', color: 'from-amber-500/20 to-yellow-500/20 text-amber-300 border-amber-500/30' },
  { id: 'System Bug', label: 'Bug Report', icon: '🐛', color: 'from-rose-500/20 to-red-500/20 text-rose-300 border-rose-500/30' },
  { id: 'Feature Request', label: 'Feature Request', icon: '✨', color: 'from-emerald-500/20 to-teal-500/20 text-emerald-300 border-emerald-500/30' },
  { id: 'General Inquiry', label: 'General Inquiry', icon: '💬', color: 'from-slate-500/20 to-zinc-500/20 text-slate-300 border-slate-500/30' },
];

const PRIORITIES = [
  { id: 'LOW', label: 'Low', color: 'bg-slate-100 text-slate-700 border-slate-300 dark:bg-slate-500/20 dark:text-slate-300 dark:border-slate-500/30' },
  { id: 'MEDIUM', label: 'Medium', color: 'bg-amber-100 text-amber-800 border-amber-300 dark:bg-amber-500/20 dark:text-amber-300 dark:border-amber-500/30' },
  { id: 'HIGH', label: 'High', color: 'bg-orange-100 text-orange-800 border-orange-300 dark:bg-orange-500/20 dark:text-orange-300 dark:border-orange-500/30' },
  { id: 'URGENT', label: 'Urgent', color: 'bg-rose-100 text-rose-800 border-rose-300 dark:bg-rose-500/20 dark:text-rose-300 dark:border-rose-500/40 animate-pulse' },
];

const STATUSES = [
  { id: 'OPEN', label: 'Open', color: 'bg-emerald-100 text-emerald-800 border-emerald-300 dark:bg-emerald-500/20 dark:text-emerald-300 dark:border-emerald-500/30' },
  { id: 'IN_PROGRESS', label: 'In Progress', color: 'bg-blue-100 text-blue-800 border-blue-300 dark:bg-blue-500/20 dark:text-blue-300 dark:border-blue-500/30' },
  { id: 'AWAITING_INFO', label: 'Awaiting Info', color: 'bg-amber-100 text-amber-800 border-amber-300 dark:bg-amber-500/20 dark:text-amber-300 dark:border-amber-500/30' },
  { id: 'RESOLVED', label: 'Resolved', color: 'bg-purple-100 text-purple-800 border-purple-300 dark:bg-purple-500/20 dark:text-purple-300 dark:border-purple-500/30' },
  { id: 'CLOSED', label: 'Closed', color: 'bg-slate-100 text-slate-700 border-slate-300 dark:bg-slate-500/20 dark:text-slate-400 dark:border-slate-500/30' },
];

export default function SupportTickets() {
  const [tickets, setTickets] = useState([]);
  const [stats, setStats] = useState({ total: 0, open: 0, in_progress: 0, awaiting_info: 0, resolved: 0, closed: 0, urgent: 0 });
  const [selectedTicket, setSelectedTicket] = useState(null);
  const [loading, setLoading] = useState(true);
  const [ticketLoading, setTicketLoading] = useState(false);
  const [error, setError] = useState(null);

  // Filters
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('ALL');
  const [priorityFilter, setPriorityFilter] = useState('ALL');
  const [categoryFilter, setCategoryFilter] = useState('ALL');

  // New ticket modal
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  const [newDescription, setNewDescription] = useState('');
  const [newCategory, setNewCategory] = useState('Technical Issue');
  const [newPriority, setNewPriority] = useState('MEDIUM');
  const [submittingTicket, setSubmittingTicket] = useState(false);

  // Resolution modal
  const [showResolveModal, setShowResolveModal] = useState(false);
  const [resolutionSummary, setResolutionSummary] = useState('');
  const [resolvingTicket, setResolvingTicket] = useState(false);

  // Chat message composer
  const [messageText, setMessageText] = useState('');
  const [isInternalNote, setIsInternalNote] = useState(false);
  const [sendingMessage, setSendingMessage] = useState(false);
  const [typingUsers, setTypingUsers] = useState({});
  const [isWsConnected, setIsWsConnected] = useState(false);

  // Apple-style Notification state & auto-dismiss
  const [appleNotification, setAppleNotification] = useState(null);
  const notifTimerRef = useRef(null);

  const triggerAppleNotification = useCallback((notif) => {
    if (notifTimerRef.current) clearTimeout(notifTimerRef.current);
    setAppleNotification(notif);
    // Sound effect temporarily disabled as requested
    // soundNotifier.playChime();
    notifTimerRef.current = setTimeout(() => {
      setAppleNotification(null);
    }, 6000);
  }, []);

  // Format raw email into clean human display name (e.g. 'admin@bourntec.com' -> 'Admin')
  const formatSenderName = useCallback((rawEmailOrName) => {
    if (!rawEmailOrName) return 'Support Team';
    if (!rawEmailOrName.includes('@')) return rawEmailOrName;
    const username = rawEmailOrName.split('@')[0];
    const clean = username.split('+')[0].replace(/[._-]/g, ' ').trim();
    const formatted = clean
      .split(' ')
      .filter(Boolean)
      .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
      .join(' ');
    return formatted || 'Support Member';
  }, []);

  // Real-time WebSocket
  const wsRef = useRef(null);
  const messagesEndRef = useRef(null);
  const token = localStorage.getItem('token');

  // Current user info
  const [currentUser, setCurrentUser] = useState(null);

  useEffect(() => {
    if (!token) return;
    fetch(API_ENDPOINTS.USERS_ME, {
      headers: { Authorization: `Bearer ${token}` }
    })
      .then(res => res.json())
      .then(data => setCurrentUser(data))
      .catch(() => {});
  }, [token]);

  const isSuperAdmin = Boolean(currentUser?.is_super_admin);
  const isOrgAdmin = Boolean(currentUser?.is_org_admin);
  const isAdmin = isSuperAdmin || isOrgAdmin;

  const knownMessagesRef = useRef(new Set());
  const initialLoadDoneRef = useRef(false);

  // Fetch ticket list and stats on mount or filter change
  const fetchTickets = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true);
    setError(null);
    try {
      const url = new URL(API_ENDPOINTS.SUPPORT_TICKETS, window.location.origin);
      if (statusFilter !== 'ALL') url.searchParams.set('status', statusFilter);
      if (priorityFilter !== 'ALL') url.searchParams.set('priority', priorityFilter);
      if (categoryFilter !== 'ALL') url.searchParams.set('category', categoryFilter);
      if (searchQuery.trim()) url.searchParams.set('search', searchQuery.trim());

      const [ticketsRes, statsRes] = await Promise.all([
        fetch(url.toString(), { headers: { Authorization: `Bearer ${token}` } }),
        fetch(API_ENDPOINTS.SUPPORT_TICKET_STATS, { headers: { Authorization: `Bearer ${token}` } })
      ]);

      if (!ticketsRes.ok) throw new Error('Failed to load tickets');
      const ticketsData = await ticketsRes.json();
      setTickets(ticketsData);

      if (statsRes.ok) {
        const statsData = await statsRes.json();
        setStats(statsData);
      }
    } catch (err) {
      setError(err.message || 'Error fetching tickets');
    } finally {
      if (!quiet) setLoading(false);
    }
  }, [token, statusFilter, priorityFilter, categoryFilter, searchQuery]);

  useEffect(() => {
    fetchTickets();
  }, [fetchTickets]);

  // Fetch full ticket details on selection
  const fetchTicketDetail = useCallback(async (ticketId) => {
    if (!ticketId) return;
    setTicketLoading(true);
    try {
      const res = await fetch(API_ENDPOINTS.SUPPORT_TICKET_DETAIL(ticketId), {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (!res.ok) throw new Error('Failed to load ticket conversation');
      const data = await res.json();
      setSelectedTicket(data);
      // Mark as read in queue list
      setTickets(prev => prev.map(t => t.id === ticketId ? { ...t, unread: false } : t));
      window.dispatchEvent(new CustomEvent('dsuite-ticket-unread-sync'));
    } catch (err) {
      console.error(err);
    } finally {
      setTicketLoading(false);
    }
  }, [token]);

  // Handle ticket selection
  const handleSelectTicket = (t) => {
    setSelectedTicket(t);
    fetchTicketDetail(t.id);
  };

  // Scroll to bottom of chat
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [selectedTicket?.messages]);

  const hubWsRef = useRef(null);
  const selectedTicketRef = useRef(null);
  useEffect(() => {
    selectedTicketRef.current = selectedTicket;
  }, [selectedTicket]);

  // ── Real-Time Hub WebSocket: Push-based notification & ticket sync (0 Polling!) ──
  useEffect(() => {
    if (!token) return;
    let isSubscribed = true;
    let reconnectTimer = null;

    const connectHubWs = () => {
      if (!isSubscribed) return;
      if (hubWsRef.current) {
        try { hubWsRef.current.close(); } catch (_) {}
        hubWsRef.current = null;
      }

      const wsUrl = API_ENDPOINTS.SUPPORT_TICKET_HUB_WS(token);
      const ws = new WebSocket(wsUrl);
      hubWsRef.current = ws;

      ws.onopen = () => {
        if (!isSubscribed) return;
        setIsWsConnected(true);
        ws._pingInterval = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'PING' }));
          }
        }, 25000);
      };

      ws.onmessage = (event) => {
        if (!isSubscribed) return;
        try {
          const payload = JSON.parse(event.data);
          if (payload.type === 'NEW_MESSAGE') {
            const { ticket_id, ticket_code, ticket_title, message: newMsg } = payload;
            
            // 1. If currently viewing this ticket, append message directly into chat thread
            if (selectedTicketRef.current?.id === ticket_id) {
              setSelectedTicket(prev => {
                if (!prev || prev.id !== ticket_id) return prev;
                if (prev.messages?.some(m => m.id === newMsg.id)) return prev;
                return {
                  ...prev,
                  last_message_at: newMsg.created_at,
                  messages: [...(prev.messages || []), newMsg]
                };
              });
            }

            // 2. If sent by someone else, trigger floating glass notification
            if (newMsg.sender_user_id !== currentUser?.id) {
              triggerAppleNotification({
                id: newMsg.id,
                ticketId: ticket_id,
                ticketCode: ticket_code || `TCK-${ticket_id}`,
                ticketTitle: ticket_title || 'Support Ticket Update',
                senderName: newMsg.sender?.email || 'Support Member',
                senderRole: newMsg.sender?.is_super_admin ? 'Super Admin' : newMsg.sender?.is_org_admin ? 'Org Admin' : 'Reporter',
                message: newMsg.message,
                isInternalNote: newMsg.is_internal_note,
                timestamp: new Date()
              });
            }

            // 3. Update the ticket in the queue list in state (0 API calls!)
            setTickets(prev => prev.map(t => {
              if (t.id !== ticket_id) return t;
              return {
                ...t,
                last_message_at: newMsg.created_at,
                unread: selectedTicketRef.current?.id !== ticket_id ? true : false,
                message_count: (t.message_count || 0) + 1
              };
            }));

            // Notify sidebar badge to refresh
            window.dispatchEvent(new CustomEvent('dsuite-ticket-unread-sync'));

          } else if (payload.type === 'TICKET_CREATED') {
            const newTicket = payload.ticket;
            setTickets(prev => {
              if (prev.some(t => t.id === newTicket.id)) return prev;
              return [newTicket, ...prev];
            });
            setStats(prev => ({
              ...prev,
              total: (prev.total || 0) + 1,
              open: (prev.open || 0) + 1
            }));
            window.dispatchEvent(new CustomEvent('dsuite-ticket-unread-sync'));

          } else if (payload.type === 'TICKET_RESOLVED') {
            const { ticket_id, resolution_summary } = payload;
            setTickets(prev => prev.map(t => {
              if (t.id !== ticket_id) return t;
              return { ...t, status: 'RESOLVED', resolution_summary };
            }));
            setSelectedTicket(prev => {
              if (!prev || prev.id !== ticket_id) return prev;
              return { ...prev, status: 'RESOLVED', resolution_summary };
            });
            setStats(prev => ({
              ...prev,
              open: Math.max(0, (prev.open || 1) - 1),
              resolved: (prev.resolved || 0) + 1
            }));
            window.dispatchEvent(new CustomEvent('dsuite-ticket-unread-sync'));
          }
        } catch (_) {}
      };

      ws.onclose = () => {
        if (ws._pingInterval) clearInterval(ws._pingInterval);
        setIsWsConnected(false);
        if (isSubscribed) {
          reconnectTimer = setTimeout(connectHubWs, 5000);
        }
      };

      ws.onerror = () => {
        try { ws.close(); } catch (_) {}
      };
    };

    connectHubWs();

    return () => {
      isSubscribed = false;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (hubWsRef.current) {
        if (hubWsRef.current._pingInterval) clearInterval(hubWsRef.current._pingInterval);
        try { hubWsRef.current.close(); } catch (_) {}
        hubWsRef.current = null;
      }
    };
  }, [token, currentUser?.id, triggerAppleNotification]);

  // Real-time resilient WebSocket connection for selected ticket
  useEffect(() => {
    if (!selectedTicket?.id || !token) {
      setIsWsConnected(false);
      return;
    }

    let isSubscribed = true;
    let reconnectTimeout = null;

    const connectWs = () => {
      if (!isSubscribed) return;
      if (wsRef.current) {
        try { wsRef.current.close(); } catch (_) {}
        wsRef.current = null;
      }

      const wsUrl = API_ENDPOINTS.SUPPORT_TICKET_WS(selectedTicket.id, token);
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!isSubscribed) return;
        setIsWsConnected(true);
        ws._pingInterval = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'PING' }));
          }
        }, 25000);
      };

      ws.onmessage = (event) => {
        if (!isSubscribed) return;
        try {
          const payload = JSON.parse(event.data);
          if (payload.type === 'NEW_MESSAGE') {
            const newMsg = payload.message;
            setSelectedTicket(prev => {
              if (!prev || prev.id !== newMsg.ticket_id) return prev;
              if (prev.messages?.some(m => m.id === newMsg.id)) return prev;
              return {
                ...prev,
                last_message_at: newMsg.created_at,
                messages: [...(prev.messages || []), newMsg]
              };
            });

            // Trigger Apple popup notification banner with sound if message is from someone else
            if (newMsg.sender_user_id !== currentUser?.id) {
              triggerAppleNotification({
                id: newMsg.id,
                ticketId: newMsg.ticket_id,
                ticketCode: selectedTicket?.ticket_code || `TCK-${newMsg.ticket_id}`,
                ticketTitle: selectedTicket?.title || 'Support Ticket Update',
                senderName: newMsg.sender?.email || 'Support Member',
                senderRole: newMsg.sender?.is_super_admin ? 'Super Admin' : newMsg.sender?.is_org_admin ? 'Org Admin' : 'Reporter',
                message: newMsg.message,
                isInternalNote: newMsg.is_internal_note,
                timestamp: new Date()
              });
            }

            // Refresh tickets list so timestamps/previews update
            fetchTickets(true);
          } else if (payload.type === 'TICKET_UPDATED' || payload.type === 'TICKET_RESOLVED') {
            const updated = payload.ticket;
            setSelectedTicket(prev => {
              if (!prev || prev.id !== updated.id) return prev;
              return {
                ...prev,
                ...updated,
                messages: updated.messages || prev.messages
              };
            });
            
            if (payload.type === 'TICKET_RESOLVED') {
              triggerAppleNotification({
                id: Date.now(),
                ticketId: updated.id,
                ticketCode: updated.ticket_code,
                ticketTitle: updated.title,
                senderName: updated.resolved_by?.email || 'Support Lead',
                senderRole: 'Super Admin',
                message: `Ticket marked as RESOLVED: ${updated.resolution_summary || 'Issue has been successfully resolved.'}`,
                isInternalNote: false,
                timestamp: new Date()
              });
            } else {
              soundNotifier.playChime();
            }
            fetchTickets(true);
          } else if (payload.type === 'USER_TYPING') {
            const { user_email, user_id, is_typing } = payload;
            if (user_id !== currentUser?.id) {
              setTypingUsers(prev => {
                const next = { ...prev };
                if (is_typing) {
                  next[user_email] = true;
                } else {
                  delete next[user_email];
                }
                return next;
              });
            }
          }
        } catch (e) {
          console.error('[TicketWS] parse error', e);
        }
      };

      ws.onerror = () => {
        setIsWsConnected(false);
      };

      ws.onclose = () => {
        setIsWsConnected(false);
        if (ws._pingInterval) clearInterval(ws._pingInterval);
        if (isSubscribed) {
          // Reconnect with 3-second delay
          reconnectTimeout = setTimeout(connectWs, 3000);
        }
      };
    };

    connectWs();

    return () => {
      isSubscribed = false;
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
      if (wsRef.current) {
        if (wsRef.current._pingInterval) clearInterval(wsRef.current._pingInterval);
        try { wsRef.current.close(); } catch (_) {}
        wsRef.current = null;
      }
      setIsWsConnected(false);
    };
  }, [selectedTicket?.id, token, currentUser?.id, triggerAppleNotification, fetchTickets]);

  // Send message
  const handleSendMessage = async (e) => {
    if (e) e.preventDefault();
    if (!messageText.trim() || !selectedTicket || sendingMessage) return;

    const textToSend = messageText.trim();
    setSendingMessage(true);

    try {
      const res = await fetch(API_ENDPOINTS.SUPPORT_TICKET_MESSAGES(selectedTicket.id), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({
          message: textToSend,
          is_internal_note: isInternalNote
        })
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Failed to send message');
      }

      const newMsg = await res.json();
      setSelectedTicket(prev => {
        if (!prev) return prev;
        if (prev.messages?.some(m => m.id === newMsg.id)) return prev;
        return {
          ...prev,
          last_message_at: newMsg.created_at,
          messages: [...(prev.messages || []), newMsg]
        };
      });

      setMessageText('');
      setIsInternalNote(false);
      fetchTickets(true);
    } catch (err) {
      alert(err.message || 'Error sending message');
    } finally {
      setSendingMessage(false);
    }
  };

  // Create new ticket
  const handleCreateTicket = async (e) => {
    e.preventDefault();
    if (!newTitle.trim() || !newDescription.trim() || submittingTicket) return;

    setSubmittingTicket(true);
    try {
      const res = await fetch(API_ENDPOINTS.SUPPORT_TICKETS, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({
          title: newTitle.trim(),
          description: newDescription.trim(),
          category: newCategory,
          priority: newPriority
        })
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Failed to create ticket');
      }

      const created = await res.json();
      setShowCreateModal(false);
      setNewTitle('');
      setNewDescription('');
      setNewCategory('Technical Issue');
      setNewPriority('MEDIUM');

      // Refresh and select new ticket
      await fetchTickets();
      setSelectedTicket(created);
    } catch (err) {
      alert(err.message || 'Error creating ticket');
    } finally {
      setSubmittingTicket(false);
    }
  };

  // Change status
  const handleStatusChange = async (newStatus) => {
    if (!selectedTicket || selectedTicket.status === newStatus) return;

    if (newStatus === 'RESOLVED') {
      setShowResolveModal(true);
      return;
    }

    try {
      const res = await fetch(`${API_ENDPOINTS.SUPPORT_TICKETS}/${selectedTicket.id}`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({ status: newStatus })
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Failed to update status');
      }

      const updated = await res.json();
      setSelectedTicket(prev => ({ ...prev, ...updated }));
      fetchTickets(true);
    } catch (err) {
      alert(err.message || 'Error updating status');
    }
  };

  // Change priority (Admin only)
  const handlePriorityChange = async (newPriorityVal) => {
    if (!selectedTicket || selectedTicket.priority === newPriorityVal || !isAdmin) return;
    try {
      const res = await fetch(`${API_ENDPOINTS.SUPPORT_TICKETS}/${selectedTicket.id}`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({ priority: newPriorityVal })
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Failed to update priority');
      }

      const updated = await res.json();
      setSelectedTicket(prev => ({ ...prev, ...updated }));
      fetchTickets(true);
    } catch (err) {
      alert(err.message || 'Error updating priority');
    }
  };

  // Submit official resolution
  const handleResolveSubmit = async (e) => {
    e.preventDefault();
    if (!selectedTicket || resolvingTicket) return;

    setResolvingTicket(true);
    try {
      const res = await fetch(API_ENDPOINTS.SUPPORT_TICKET_RESOLVE(selectedTicket.id), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({ resolution_summary: resolutionSummary.trim() })
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Failed to resolve ticket');
      }

      const updated = await res.json();
      setSelectedTicket(prev => ({ ...prev, ...updated }));
      setShowResolveModal(false);
      setResolutionSummary('');
      fetchTickets(true);
    } catch (err) {
      alert(err.message || 'Error resolving ticket');
    } finally {
      setResolvingTicket(false);
    }
  };

  const copyTicketCode = (code) => {
    navigator.clipboard.writeText(code);
  };

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden bg-slate-50 dark:bg-slate-950 text-slate-800 dark:text-slate-100 transition-colors duration-200 relative">
      
      {/* ── DSuite-Native Compact Glassmorphic Floating Notification ── */}
      {appleNotification && (
        <div 
          onClick={() => {
            if (appleNotification.ticketId && selectedTicket?.id !== appleNotification.ticketId) {
              fetchTicketDetail(appleNotification.ticketId);
            }
            setAppleNotification(null);
          }}
          className="fixed top-5 right-5 sm:right-7 z-[99999] w-[calc(100vw-2rem)] sm:w-[390px] max-w-[400px] cursor-pointer animate-in fade-in slide-in-from-top-3 duration-300 pointer-events-auto select-none"
          role="alert"
          aria-live="assertive"
        >
          {/* Compact Native DSuite Glass Surface: 18px radius, subtle lavender reflection, soft ambient shadow */}
          <div 
            style={{ backdropFilter: 'blur(20px) saturate(135%)', WebkitBackdropFilter: 'blur(20px) saturate(135%)' }}
            className="relative overflow-hidden rounded-[18px] bg-white/[0.90] dark:bg-[#0c1527]/[0.92] border border-white/80 dark:border-white/[0.12] shadow-[0_10px_28px_rgba(28,53,94,0.08),0_2px_6px_rgba(0,0,0,0.04)] dark:shadow-[0_14px_32px_rgba(0,0,0,0.4),0_2px_8px_rgba(0,0,0,0.2)] hover:shadow-[0_14px_34px_rgba(28,53,94,0.11),0_4px_10px_rgba(0,0,0,0.05)] p-3.5 transition-all duration-300 group"
          >
            {/* Extremely Subtle Lavender/Purple Sheen Reflection */}
            <div className="absolute inset-0 bg-gradient-to-br from-purple-500/[0.03] via-transparent to-indigo-500/[0.02] pointer-events-none rounded-[18px]" />
            <div className="absolute inset-x-0 top-0 h-[1px] bg-gradient-to-r from-transparent via-white/90 dark:via-white/20 to-transparent pointer-events-none" />

            {/* ── 1. Top Source Row: Ticket Icon, Timestamp, Minimal Close ── */}
            <div className="relative flex items-center justify-between mb-2">
              <div className="flex items-center gap-1.5 min-w-0">
                <div className="w-4 h-4 rounded-md bg-purple-600/15 dark:bg-purple-500/25 border border-purple-500/30 flex items-center justify-center text-purple-600 dark:text-purple-400 shrink-0">
                  <Ticket className="w-2.5 h-2.5" />
                </div>
                <span className="text-[11.5px] font-semibold text-slate-600 dark:text-slate-300 tracking-tight">
                  DSuite Support
                </span>
                <span className="text-[10px] text-slate-300 dark:text-slate-600 font-bold">•</span>
                <span className="text-[11px] text-slate-400 dark:text-slate-500 font-normal">
                  now
                </span>
              </div>

              {/* Understated Minimal Close Action */}
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  setAppleNotification(null);
                }}
                className="text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 transition-colors p-0.5 rounded-md hover:bg-black/5 dark:hover:bg-white/10 flex items-center gap-1 text-[11px] font-medium cursor-pointer shrink-0"
                title="Close"
              >
                <span>Close</span>
                <X className="w-3 h-3" />
              </button>
            </div>

            {/* ── 2. User Identity & Message Area ── */}
            <div className="relative flex items-start gap-2.5">
              {/* DSuite Purple Gradient Avatar */}
              <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-purple-600 to-indigo-600 text-white font-bold text-xs flex items-center justify-center shadow-xs shrink-0 ring-2 ring-purple-100 dark:ring-purple-950/60">
                {formatSenderName(appleNotification.senderName)[0]?.toUpperCase() || 'A'}
              </div>

              <div className="flex-1 min-w-0">
                {/* Admin (soft slate-800) + Super Admin + ticket ID */}
                <div className="flex items-center gap-1.5 flex-wrap">
                  <span className="text-[13.5px] font-semibold text-slate-800 dark:text-slate-100 tracking-tight">
                    {formatSenderName(appleNotification.senderName)}
                  </span>

                  <span className="px-1.5 py-0.2 rounded-full text-[9.5px] font-semibold bg-purple-50 dark:bg-purple-950/60 text-purple-700 dark:text-purple-300 border border-purple-200/80 dark:border-purple-800/80">
                    {appleNotification.senderRole}
                  </span>

                  <span className="text-[10.5px] font-mono text-slate-400 dark:text-slate-500">
                    {appleNotification.ticketCode}
                  </span>
                </div>

                {/* Message preview: strictly clamped to 2 lines max to keep notification sleek and compact */}
                <div 
                  style={{ display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}
                  className="pt-0.5 text-[12.5px] text-slate-600 dark:text-slate-300 leading-snug font-normal break-words"
                  title={appleNotification.message}
                >
                  {appleNotification.isInternalNote && (
                    <span className="inline-flex items-center gap-1 text-amber-600 dark:text-amber-400 font-medium mr-1 text-[11px] shrink-0">
                      <Lock className="w-2.5 h-2.5" />
                      <span>Note:</span>
                    </span>
                  )}
                  <span>{appleNotification.message}</span>
                </div>
              </div>
            </div>

            {/* ── 3. Context & Action Row: Compact Topic Context & Lightweight Action ── */}
            <div className="relative flex items-center justify-between gap-2 pt-2 mt-2 border-t border-slate-200/50 dark:border-slate-800/50 text-[11px]">
              <div className="flex items-center gap-1.5 text-slate-400 dark:text-slate-500 font-medium truncate max-w-[230px]" title={appleNotification.ticketTitle}>
                <span className="w-1.5 h-1.5 rounded-full bg-purple-500/70 shrink-0" />
                <span className="truncate">{appleNotification.ticketTitle}</span>
              </div>

              {/* Lightweight DSuite Action: Open Ticket → */}
              <span className="font-semibold text-purple-600 dark:text-purple-400 group-hover:text-purple-700 dark:group-hover:text-purple-300 transition-colors flex items-center gap-1 shrink-0 text-xs">
                <span>Open Ticket</span>
                <span className="transition-transform duration-200 group-hover:translate-x-0.5">→</span>
              </span>
            </div>
          </div>
        </div>
      )}

      {/* ── Unified Sleek Toolbar (Merged Header + Metrics in One Single 40px Row) ── */}
      <div className="flex-shrink-0 px-4 py-2 border-b border-slate-200 dark:border-slate-800 bg-white/80 dark:bg-slate-950/60 backdrop-blur-md flex items-center justify-between gap-3 min-w-0 text-xs">
        {/* Left: Hub Icon + Title + Live Dot */}
        <div className="flex items-center gap-2.5 min-w-0 shrink-0">
          <div className="p-1.5 rounded-lg bg-purple-500/10 dark:bg-purple-600/20 border border-purple-300 dark:border-purple-500/30 text-purple-600 dark:text-purple-400 shrink-0">
            <LifeBuoy className="w-4 h-4" />
          </div>
          <div className="flex items-center gap-2 min-w-0">
            <h1 className="text-sm font-bold text-slate-900 dark:text-white tracking-tight truncate">
              Support Hub
            </h1>
            <span className={`inline-flex items-center gap-1 px-1.5 py-0.2 rounded-full text-[9.5px] font-semibold border shrink-0 ${
              isWsConnected 
                ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-300/60 dark:border-emerald-500/30'
                : 'bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-300/60 dark:border-blue-500/30'
            }`}>
              <span className={`w-1 h-1 rounded-full ${isWsConnected ? 'bg-emerald-500 animate-pulse' : 'bg-blue-500 animate-ping'}`} />
              {isWsConnected ? 'Live' : 'Syncing'}
            </span>
          </div>
        </div>

        {/* Center: Compact Metric Badges (Single Row) */}
        <div className="flex items-center gap-1.5 sm:gap-2 flex-nowrap overflow-x-auto custom-scrollbar shrink min-w-0">
          <div className="flex items-center gap-1.5 px-2 py-0.5 rounded-md bg-slate-100 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700/60">
            <span className="text-[10px] font-medium text-slate-500 dark:text-slate-400">Total</span>
            <span className="font-bold text-slate-900 dark:text-white text-[10px]">{stats.total}</span>
          </div>

          <div className="flex items-center gap-1.5 px-2 py-0.5 rounded-md bg-emerald-500/10 border border-emerald-500/20 text-emerald-700 dark:text-emerald-300">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
            <span className="text-[10px] font-medium">Open</span>
            <span className="font-bold text-emerald-600 dark:text-emerald-400 text-[10px]">{stats.open}</span>
          </div>

          <div className="flex items-center gap-1.5 px-2 py-0.5 rounded-md bg-blue-500/10 border border-blue-500/20 text-blue-700 dark:text-blue-300">
            <span className="w-1.5 h-1.5 rounded-full bg-blue-500" />
            <span className="text-[10px] font-medium hidden xs:inline">In Progress</span>
            <span className="text-[10px] font-medium xs:hidden">Prog</span>
            <span className="font-bold text-blue-600 dark:text-blue-400 text-[10px]">{stats.in_progress}</span>
          </div>

          <div className="flex items-center gap-1.5 px-2 py-0.5 rounded-md bg-purple-500/10 border border-purple-500/20 text-purple-700 dark:text-purple-300">
            <span className="w-1.5 h-1.5 rounded-full bg-purple-500" />
            <span className="text-[10px] font-medium hidden xs:inline">Resolved</span>
            <span className="text-[10px] font-medium xs:hidden">Done</span>
            <span className="font-bold text-purple-600 dark:text-purple-400 text-[10px]">{stats.resolved}</span>
          </div>

          {stats.urgent > 0 && (
            <div className="flex items-center gap-1.5 px-2 py-0.5 rounded-md bg-rose-500/10 border border-rose-500/20 text-rose-700 dark:text-rose-300 animate-pulse">
              <Flame className="w-2.5 h-2.5 text-rose-500" />
              <span className="text-[10px] font-medium">Urgent</span>
              <span className="font-bold text-rose-600 dark:text-rose-400 text-[10px]">{stats.urgent}</span>
            </div>
          )}
        </div>

        {/* Right: Actions */}
        <div className="flex items-center gap-1.5 shrink-0">
          <button
            onClick={() => fetchTickets()}
            disabled={loading}
            className="p-1.5 rounded-lg bg-white dark:bg-slate-800/80 hover:bg-slate-100 dark:hover:bg-slate-700/80 border border-slate-300 dark:border-slate-700 text-slate-600 dark:text-slate-300 transition-all cursor-pointer"
            title="Refresh tickets"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          </button>

          <button
            onClick={() => setShowCreateModal(true)}
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white text-[11px] font-bold shadow-xs transition-all cursor-pointer active:scale-95 shrink-0"
          >
            <Plus className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Raise Ticket</span>
          </button>
        </div>
      </div>

      {/* ── Main Workspace: Split View (Queue + Thread) ── */}
      <div className="flex-1 flex overflow-hidden min-w-0">
        
        {/* ── Left Column: Ticket Queue & Filters ── */}
        <div className={`w-full md:w-72 lg:w-80 shrink-0 flex flex-col border-r border-slate-200 dark:border-slate-800 bg-white/70 dark:bg-slate-950/40 ${selectedTicket ? 'hidden md:flex' : 'flex'}`}>
          
          {/* Search & Filter Toolbar */}
          <div className="p-3 border-b border-slate-200 dark:border-slate-800/80 space-y-2">
            <div className="relative">
              <Search className="w-3.5 h-3.5 absolute left-2.5 top-2.5 text-slate-400" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search ticket code, title..."
                className="w-full pl-8 pr-2.5 py-1.5 text-xs bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700/80 rounded-lg text-slate-800 dark:text-slate-100 placeholder-slate-400 dark:placeholder-slate-500 focus:outline-none focus:border-purple-500 transition-colors shadow-xs"
              />
            </div>

            <div className="grid grid-cols-2 gap-1.5">
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="w-full px-2 py-1.5 text-[11px] bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-lg text-slate-700 dark:text-slate-200 focus:outline-none focus:border-purple-500 shadow-xs truncate cursor-pointer"
              >
                <option value="ALL">All Statuses</option>
                {STATUSES.map(s => (
                  <option key={s.id} value={s.id}>{s.label}</option>
                ))}
              </select>

              <select
                value={priorityFilter}
                onChange={(e) => setPriorityFilter(e.target.value)}
                className="w-full px-2 py-1.5 text-[11px] bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-lg text-slate-700 dark:text-slate-200 focus:outline-none focus:border-purple-500 shadow-xs truncate cursor-pointer"
              >
                <option value="ALL">All Priorities</option>
                {PRIORITIES.map(p => (
                  <option key={p.id} value={p.id}>{p.label}</option>
                ))}
              </select>
            </div>
          </div>

          {/* Ticket Cards List */}
          <div className="flex-1 overflow-y-auto p-2.5 space-y-2 divide-y-0 custom-scrollbar">
            {loading && tickets.length === 0 ? (
              <div className="p-8 text-center text-slate-500 dark:text-slate-400 text-xs flex flex-col items-center gap-2">
                <RefreshCw className="w-5 h-5 animate-spin text-purple-600 dark:text-purple-400" />
                <span>Loading tickets...</span>
              </div>
            ) : tickets.length === 0 ? (
              <div className="p-8 text-center text-slate-500 dark:text-slate-400 text-xs flex flex-col items-center gap-3">
                <div className="p-3 rounded-full bg-slate-100 dark:bg-slate-800/80 text-slate-400 dark:text-slate-500">
                  <LifeBuoy className="w-6 h-6" />
                </div>
                <div>
                  <p className="font-semibold text-slate-700 dark:text-slate-300">No support tickets found</p>
                  <p className="text-[11px] text-slate-500 mt-1">Raise a new ticket or adjust your filters.</p>
                </div>
              </div>
            ) : (
              tickets.map((t) => {
                const isSelected = selectedTicket?.id === t.id;
                const catObj = CATEGORIES.find(c => c.id === t.category);
                const prioObj = PRIORITIES.find(p => p.id === t.priority);
                const statusObj = STATUSES.find(s => s.id === t.status);

                return (
                  <div
                    key={t.id}
                    onClick={() => handleSelectTicket(t)}
                    className={`p-3 rounded-xl border transition-all cursor-pointer relative group ${
                      isSelected
                        ? 'bg-purple-50/80 dark:bg-purple-950/25 border-purple-500/60 dark:border-purple-500/50 shadow-md ring-1 ring-purple-500/20'
                        : 'bg-white dark:bg-slate-900/70 hover:bg-slate-50 dark:hover:bg-slate-800/60 border-slate-200 dark:border-slate-800/90 shadow-xs'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-1.5 mb-1.5">
                      <div className="flex items-center gap-1.5 min-w-0">
                        {t.unread && (
                          <span className="w-2 h-2 rounded-full bg-blue-500 shrink-0 ring-2 ring-blue-500/20 animate-pulse" title="Unread new message" />
                        )}
                        <span className="font-mono text-[11px] font-bold text-purple-700 dark:text-purple-300 tracking-wider truncate">
                          {t.ticket_code}
                        </span>
                      </div>
                      <div className="flex items-center gap-1 shrink-0">
                        <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold border ${prioObj?.color || ''}`}>
                          {prioObj?.label || t.priority}
                        </span>
                        <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold border ${statusObj?.color || ''}`}>
                          {statusObj?.label || t.status}
                        </span>
                      </div>
                    </div>

                    <h4 className="text-xs font-semibold text-slate-900 dark:text-white line-clamp-1 group-hover:text-purple-600 dark:group-hover:text-purple-200 transition-colors">
                      {t.title}
                    </h4>

                    <p className="text-[11px] text-slate-600 dark:text-slate-400 line-clamp-2 mt-1 leading-snug">
                      {t.description}
                    </p>

                    <div className="mt-2.5 pt-2 border-t border-slate-100 dark:border-slate-800/60 flex items-center justify-between text-[10px] text-slate-500">
                      <div className="flex items-center gap-1 truncate max-w-[130px]">
                        <span>{catObj?.icon || '🏷️'}</span>
                        <span className="truncate">{t.category}</span>
                      </div>
                      <span className="shrink-0">
                        {t.last_message_at ? new Date(t.last_message_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) : ''}
                      </span>
                    </div>

                    {isSuperAdmin && t.organization_name && (
                      <div className="mt-1 text-[10px] text-purple-600 dark:text-purple-400 font-medium truncate flex items-center gap-1">
                        <Building2 className="w-2.5 h-2.5 shrink-0" />
                        <span className="truncate">{t.organization_name}</span>
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* ── Right Column: Active Ticket Conversation Thread ── */}
        <div className={`flex-1 min-w-0 flex flex-col bg-slate-50/50 dark:bg-slate-900/30 overflow-hidden ${selectedTicket ? 'flex' : 'hidden md:flex'}`}>
          {selectedTicket ? (
            <div className="flex-1 min-w-0 flex flex-col h-full overflow-hidden">
              
              {/* Thread Header - Ultra Compact Sleek Bar (reclaims 100px+ vertical height) */}
              <div className="flex-shrink-0 px-3 sm:px-4 py-2 border-b border-slate-200 dark:border-slate-800 bg-white/95 dark:bg-slate-950/70 backdrop-blur-md flex items-center justify-between gap-2.5 min-w-0">
                
                {/* Left: Code, Title, Badges & Metadata */}
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5 flex-wrap min-w-0">
                    <button 
                      onClick={() => setSelectedTicket(null)}
                      className="md:hidden p-1 rounded-md bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 mr-0.5 border border-slate-300 dark:border-slate-700 shrink-0"
                    >
                      <ArrowLeft className="w-3.5 h-3.5" />
                    </button>
                    
                    <button
                      onClick={() => copyTicketCode(selectedTicket.ticket_code)}
                      className="inline-flex items-center gap-1 font-mono text-[11px] font-bold px-1.5 py-0.5 rounded bg-purple-50 dark:bg-purple-500/15 text-purple-700 dark:text-purple-300 border border-purple-200 dark:border-purple-500/30 hover:bg-purple-100 transition-colors cursor-pointer shrink-0"
                      title="Click to copy ticket code"
                    >
                      <span>{selectedTicket.ticket_code}</span>
                      <Copy className="w-2.5 h-2.5 text-purple-600 dark:text-purple-400" />
                    </button>

                    <h2 className="text-xs sm:text-sm font-bold text-slate-900 dark:text-white tracking-tight truncate max-w-[180px] sm:max-w-xs md:max-w-sm lg:max-w-md" title={selectedTicket.title}>
                      {selectedTicket.title}
                    </h2>

                    <span className={`px-1.5 py-0.2 rounded text-[9.5px] font-bold border shrink-0 ${STATUSES.find(s => s.id === selectedTicket.status)?.color}`}>
                      {selectedTicket.status}
                    </span>

                    <span className={`px-1.5 py-0.2 rounded text-[9.5px] font-bold border shrink-0 ${PRIORITIES.find(p => p.id === selectedTicket.priority)?.color}`}>
                      {selectedTicket.priority}
                    </span>
                  </div>

                  {/* Single subtle line for reporter & metadata */}
                  <div className="flex items-center gap-2 text-[10.5px] text-slate-500 dark:text-slate-400 truncate mt-0.5">
                    <span className="truncate max-w-[160px]">
                      By <strong className="text-slate-700 dark:text-slate-300 font-medium" title={selectedTicket.created_by?.email}>{formatSenderName(selectedTicket.created_by?.email)}</strong>
                    </span>
                    {selectedTicket.organization_name && (
                      <span className="inline-flex items-center gap-0.5 text-purple-600 dark:text-purple-400 font-medium shrink-0">
                        <Building2 className="w-2.5 h-2.5" />
                        <span>{selectedTicket.organization_name}</span>
                      </span>
                    )}
                    <span className="shrink-0">• {selectedTicket.category}</span>
                    <span className="shrink-0">• {new Date(selectedTicket.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</span>
                  </div>
                </div>

                {/* Right: Status & Resolution Controls in one tight row */}
                <div className="flex items-center gap-1.5 shrink-0">
                  {isAdmin && (
                    <select
                      value={selectedTicket.priority}
                      onChange={(e) => handlePriorityChange(e.target.value)}
                      className="px-2 py-1 text-[11px] bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg text-slate-800 dark:text-slate-200 focus:outline-none focus:border-purple-500 font-medium shadow-2xs cursor-pointer"
                    >
                      {PRIORITIES.map(p => (
                        <option key={p.id} value={p.id}>{p.label}</option>
                      ))}
                    </select>
                  )}

                  <select
                    value={selectedTicket.status}
                    onChange={(e) => handleStatusChange(e.target.value)}
                    className="px-2 py-1 text-[11px] bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg text-slate-800 dark:text-slate-200 focus:outline-none focus:border-purple-500 font-medium shadow-2xs cursor-pointer"
                  >
                    {STATUSES.map(s => (
                      <option key={s.id} value={s.id}>{s.label}</option>
                    ))}
                  </select>

                  {selectedTicket.status !== 'RESOLVED' && selectedTicket.status !== 'CLOSED' && (
                    <button
                      onClick={() => setShowResolveModal(true)}
                      className="flex items-center gap-1 px-2.5 py-1 text-[11px] font-bold rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white shadow-xs transition-all cursor-pointer shrink-0 active:scale-95"
                    >
                      <CheckCircle className="w-3 h-3" />
                      <span>Resolve</span>
                    </button>
                  )}
                </div>
              </div>

              {/* Resolution Banner if Resolved */}
              {selectedTicket.status === 'RESOLVED' && selectedTicket.resolution_summary && (
                <div className="mx-3 mt-2 p-2 rounded-lg bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-500/30 flex items-start gap-2 shadow-2xs">
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400 shrink-0 mt-0.5" />
                  <div className="text-xs">
                    <p className="font-bold text-emerald-800 dark:text-emerald-300 text-[11px]">Ticket Resolved</p>
                    <p className="text-slate-700 dark:text-slate-300 text-[11px] leading-snug">{selectedTicket.resolution_summary}</p>
                    {selectedTicket.resolved_by && (
                      <p className="text-[10px] text-slate-500 dark:text-slate-400 mt-0.5">
                        By {selectedTicket.resolved_by.email} on {new Date(selectedTicket.resolved_at).toLocaleString()}
                      </p>
                    )}
                  </div>
                </div>
              )}

              {/* Conversation Messages Thread - Spacious scroll viewport */}
              <div className="flex-1 overflow-y-auto px-3 sm:px-4 py-2.5 space-y-2.5 custom-scrollbar min-w-0">
                
                {/* Compact Original Request Quote */}
                {selectedTicket.description && (
                  <div className="px-3 py-2 rounded-lg bg-white/90 dark:bg-slate-900/80 border border-slate-200 dark:border-slate-800 text-xs shadow-2xs mb-2">
                    <div className="flex items-center justify-between gap-1.5 text-[10.5px] font-semibold text-slate-600 dark:text-slate-400 mb-0.5">
                      <span className="flex items-center gap-1 text-purple-700 dark:text-purple-300">
                        <FileText className="w-3 h-3" />
                        <span>Issue Description</span>
                      </span>
                      <span className="font-normal text-slate-400 text-[10px]">{new Date(selectedTicket.created_at).toLocaleDateString()}</span>
                    </div>
                    <p className="text-[11.5px] text-slate-700 dark:text-slate-300 whitespace-pre-wrap leading-snug break-words">
                      {selectedTicket.description}
                    </p>
                  </div>
                )}

                {ticketLoading ? (
                  <div className="py-8 text-center text-slate-500 dark:text-slate-400 text-xs flex flex-col items-center gap-1.5">
                    <RefreshCw className="w-4 h-4 animate-spin text-purple-600 dark:text-purple-400" />
                    <span>Loading conversation history...</span>
                  </div>
                ) : selectedTicket.messages && selectedTicket.messages.length > 0 ? (
                  selectedTicket.messages.map((msg) => {
                    const isCurrentUser = msg.sender_user_id === currentUser?.id;
                    const isSenderSuper = msg.sender?.is_super_admin;
                    const isSenderOrgAdmin = msg.sender?.is_org_admin;

                    return (
                      <div
                        key={msg.id}
                        className={`flex gap-2 max-w-full ${isCurrentUser ? 'ml-auto flex-row-reverse justify-start' : 'justify-start'}`}
                      >
                        {/* Compact Avatar */}
                        <div className={`w-6 h-6 sm:w-7 sm:h-7 rounded-full flex items-center justify-center text-[10px] font-bold shrink-0 shadow-2xs ${
                          isCurrentUser
                            ? 'bg-gradient-to-tr from-purple-600 to-indigo-600 text-white ring-1 ring-purple-200 dark:ring-purple-950/60'
                            : isSenderSuper
                              ? 'bg-purple-100 dark:bg-purple-900/40 text-purple-700 dark:text-purple-300 border border-purple-200 dark:border-purple-800'
                              : isSenderOrgAdmin
                                ? 'bg-emerald-100 dark:bg-emerald-900/40 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800'
                                : 'bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 border border-slate-200 dark:border-slate-700'
                        }`}>
                          {msg.sender?.email ? msg.sender.email[0].toUpperCase() : 'U'}
                        </div>

                        <div className={`flex flex-col space-y-0.5 min-w-0 max-w-[90%] sm:max-w-xl ${isCurrentUser ? 'items-end' : 'items-start'}`}>
                          {/* Sender Info & Role Badge */}
                          <div className="flex items-center gap-1 flex-wrap text-[10.5px] px-0.5">
                            <span className="font-semibold text-slate-800 dark:text-slate-200 truncate max-w-[150px]" title={msg.sender?.email || 'User'}>
                              {isCurrentUser ? 'You' : formatSenderName(msg.sender?.email)}
                            </span>

                            {isSenderSuper ? (
                              <span className="inline-flex items-center gap-0.5 px-1 py-0.2 rounded text-[9px] font-bold bg-purple-100 dark:bg-purple-500/20 text-purple-700 dark:text-purple-300 border border-purple-200 dark:border-purple-500/30">
                                <Shield className="w-2 h-2" />
                                Super Admin
                              </span>
                            ) : isSenderOrgAdmin ? (
                              <span className="inline-flex items-center gap-0.5 px-1 py-0.2 rounded text-[9px] font-bold bg-emerald-100 dark:bg-emerald-500/20 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-500/30">
                                <Building2 className="w-2 h-2" />
                                Org Admin
                              </span>
                            ) : null}

                            {msg.is_internal_note && (
                              <span className="inline-flex items-center gap-0.5 px-1 py-0.2 rounded text-[9px] font-bold bg-amber-100 dark:bg-amber-500/20 text-amber-800 dark:text-amber-300 border border-amber-200 dark:border-amber-500/30">
                                <Lock className="w-2 h-2" />
                                Note
                              </span>
                            )}

                            <span className="text-slate-400 dark:text-slate-500 text-[9.5px] shrink-0">
                              {new Date(msg.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                            </span>
                          </div>

                          {/* Message Bubble */}
                          <div className={`px-3 py-2 rounded-2xl text-xs leading-relaxed break-words shadow-2xs ${
                            msg.is_internal_note
                              ? 'bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-500/30 text-amber-900 dark:text-amber-200'
                              : isCurrentUser
                                ? 'bg-gradient-to-r from-purple-600 to-indigo-600 text-white rounded-tr-xs shadow-purple-600/10'
                                : 'bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-800 dark:text-slate-100 rounded-tl-xs'
                          }`}>
                            <div className="whitespace-pre-wrap break-words">
                              {msg.message}
                            </div>
                          </div>
                        </div>
                      </div>
                    );
                  })
                ) : (
                  <div className="py-8 text-center text-slate-400 text-xs">
                    No messages yet in this ticket thread.
                  </div>
                )}

                {/* Typing Indicator */}
                {Object.keys(typingUsers).length > 0 && (
                  <div className="text-[10px] text-slate-500 dark:text-slate-400 flex items-center gap-1 italic animate-pulse">
                    <span className="w-1.5 h-1.5 rounded-full bg-purple-500 dark:bg-purple-400" />
                    <span>{Object.keys(typingUsers).join(', ')} is typing...</span>
                  </div>
                )}

                <div ref={messagesEndRef} />
              </div>

              {/* Chat Composer - Compact Single Row (reclaims 80px+ vertical height) */}
              <div className="flex-shrink-0 px-3 py-2 sm:px-4 sm:py-2 border-t border-slate-200 dark:border-slate-800 bg-white/95 dark:bg-slate-950/90 backdrop-blur-md">
                <form onSubmit={handleSendMessage} className="flex items-center gap-2">
                  
                  {/* Admin Note Toggle Chip */}
                  {isAdmin && (
                    <label 
                      className={`inline-flex items-center gap-1 px-2 py-1.5 rounded-lg border text-[11px] font-semibold cursor-pointer select-none shrink-0 transition-colors ${
                        isInternalNote 
                          ? 'bg-amber-100 dark:bg-amber-950/60 border-amber-300 dark:border-amber-700 text-amber-800 dark:text-amber-300' 
                          : 'bg-slate-100 dark:bg-slate-800/80 border-slate-200 dark:border-slate-700 text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'
                      }`}
                      title={isInternalNote ? "Sending as internal admin note (hidden from reporter)" : "Click to toggle internal note"}
                    >
                      <input
                        type="checkbox"
                        checked={isInternalNote}
                        onChange={(e) => setIsInternalNote(e.target.checked)}
                        className="sr-only"
                      />
                      <Lock className={`w-3 h-3 ${isInternalNote ? 'text-amber-600' : 'text-slate-400'}`} />
                      <span>{isInternalNote ? 'Note' : 'Public'}</span>
                    </label>
                  )}

                  {/* Input Box */}
                  <div className={`flex-1 relative rounded-xl border transition-all duration-150 bg-slate-50 dark:bg-slate-900 flex items-center shadow-2xs ${
                    isInternalNote 
                      ? 'border-amber-400 dark:border-amber-500/60 ring-1 ring-amber-500/20' 
                      : 'border-slate-200 dark:border-slate-700/80 focus-within:border-purple-500 focus-within:ring-1 focus-within:ring-purple-500/20'
                  }`}>
                    <textarea
                      rows={1}
                      value={messageText}
                      onChange={(e) => setMessageText(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' && !e.shiftKey) {
                          e.preventDefault();
                          handleSendMessage();
                        }
                      }}
                      placeholder={isInternalNote ? "Write internal note (hidden from reporter)..." : "Write a reply... (Enter to send, Shift+Enter for newline)"}
                      className="w-full px-3 py-2 text-xs bg-transparent placeholder-slate-400 dark:placeholder-slate-500 text-slate-900 dark:text-white focus:outline-none resize-none leading-normal"
                      style={{ minHeight: '36px', maxHeight: '90px' }}
                    />
                  </div>

                  {/* Send Button */}
                  <button
                    type="submit"
                    disabled={!messageText.trim() || sendingMessage}
                    className={`h-9 px-3.5 rounded-xl font-bold flex items-center justify-center gap-1.5 transition-all cursor-pointer shadow-xs active:scale-95 shrink-0 ${
                      isInternalNote
                        ? 'bg-amber-600 hover:bg-amber-500 text-white shadow-amber-600/20'
                        : 'bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white disabled:opacity-40 disabled:cursor-not-allowed shadow-purple-600/20'
                    }`}
                    title="Send message (Enter)"
                  >
                    <Send className="w-3.5 h-3.5" />
                    <span className="text-xs font-semibold">Send</span>
                  </button>
                </form>
              </div>
            </div>
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center p-8 text-center text-slate-500 dark:text-slate-400 space-y-3">
              <div className="p-4 rounded-2xl bg-white dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700/60 text-purple-600 dark:text-purple-400 shadow-sm">
                <LifeBuoy className="w-8 h-8" />
              </div>
              <h3 className="text-sm font-bold text-slate-800 dark:text-slate-200">No Ticket Selected</h3>
              <p className="text-xs text-slate-500 dark:text-slate-400 max-w-sm">
                Select a ticket from the left panel to inspect conversation history, chat in real-time, or raise a new support request.
              </p>
              <button
                onClick={() => setShowCreateModal(true)}
                className="mt-2 inline-flex items-center gap-2 px-3.5 py-1.5 rounded-lg bg-purple-600 hover:bg-purple-500 text-white text-xs font-semibold shadow-sm transition-all cursor-pointer"
              >
                <Plus className="w-3.5 h-3.5" />
                <span>Raise Support Ticket</span>
              </button>
            </div>
          )}
        </div>
      </div>

      {/* ── Modal: Raise Support Ticket ── */}
      {showCreateModal && (
        <div 
          className="fixed inset-0 z-[9999] flex items-center justify-center p-3 sm:p-4 bg-slate-950/70 backdrop-blur-sm animate-in fade-in duration-200"
          onClick={(e) => {
            if (e.target === e.currentTarget) setShowCreateModal(false);
          }}
        >
          <div className="w-full max-w-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl shadow-2xl overflow-hidden max-h-[90vh] flex flex-col my-auto animate-in zoom-in-95 duration-200">
            
            {/* Modal Header */}
            <div className="shrink-0 px-6 py-4 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between bg-slate-50/70 dark:bg-slate-800/40">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-purple-500/15 to-indigo-500/25 border border-purple-200 dark:border-purple-500/30 text-purple-600 dark:text-purple-400 flex items-center justify-center shadow-sm">
                  <LifeBuoy className="w-5 h-5" />
                </div>
                <div>
                  <span className="text-[10px] font-bold uppercase tracking-wider text-purple-600 dark:text-purple-400">
                    Direct Helpdesk
                  </span>
                  <h3 className="text-base font-bold text-slate-900 dark:text-white leading-tight">
                    Raise Support Ticket
                  </h3>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setShowCreateModal(false)}
                className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors cursor-pointer"
                title="Close modal"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Modal Scrollable Body */}
            <form id="raise-ticket-form" onSubmit={handleCreateTicket} className="flex-1 overflow-y-auto custom-scrollbar p-6 space-y-4">
              {/* Ticket Title */}
              <div>
                <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1.5 flex items-center gap-1.5">
                  <Tag className="w-3.5 h-3.5 text-purple-500" />
                  Ticket Subject / Title <span className="text-rose-500">*</span>
                </label>
                <input
                  type="text"
                  required
                  value={newTitle}
                  onChange={(e) => setNewTitle(e.target.value)}
                  placeholder="e.g. Need agent quota expansion for Q3 release"
                  className="w-full px-3.5 py-2.5 text-xs font-medium rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-white placeholder-slate-400 dark:placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-purple-500/20 focus:border-purple-500 transition-all shadow-sm"
                />
              </div>

              {/* Category Selection */}
              <div>
                <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1.5">
                  Category <span className="text-rose-500">*</span>
                </label>
                <div className="grid grid-cols-2 gap-2">
                  {CATEGORIES.map(cat => {
                    const isSelected = newCategory === cat.id;
                    return (
                      <button
                        key={cat.id}
                        type="button"
                        onClick={() => setNewCategory(cat.id)}
                        className={`p-2.5 rounded-xl text-left border text-xs font-medium flex items-center justify-between gap-2 transition-all cursor-pointer ${
                          isSelected
                            ? 'bg-purple-50 dark:bg-purple-950/40 border-purple-500 text-purple-900 dark:text-purple-200 ring-1 ring-purple-500/30 shadow-sm'
                            : 'bg-slate-50/70 dark:bg-slate-950/50 border-slate-200/80 dark:border-slate-800/80 text-slate-700 dark:text-slate-400 hover:border-slate-300 dark:hover:border-slate-700 hover:bg-white dark:hover:bg-slate-900'
                        }`}
                      >
                        <div className="flex items-center gap-2 min-w-0">
                          <span className="text-base shrink-0">{cat.icon}</span>
                          <span className="truncate text-xs font-semibold">{cat.label}</span>
                        </div>
                        {isSelected && <Check className="w-3.5 h-3.5 text-purple-600 dark:text-purple-400 shrink-0" />}
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Priority Selection */}
              <div>
                <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1.5 flex items-center gap-1.5">
                  <Flame className="w-3.5 h-3.5 text-orange-500" />
                  Priority Level <span className="text-rose-500">*</span>
                </label>
                <div className="grid grid-cols-4 gap-2">
                  {PRIORITIES.map(prio => {
                    const isSelected = newPriority === prio.id;
                    return (
                      <button
                        key={prio.id}
                        type="button"
                        onClick={() => setNewPriority(prio.id)}
                        className={`py-2 px-2 rounded-xl text-center text-xs font-bold border transition-all cursor-pointer flex items-center justify-center gap-1.5 ${
                          isSelected
                            ? prio.color + ' ring-2 ring-purple-500/50 shadow-sm'
                            : 'bg-slate-50/70 dark:bg-slate-950/50 border-slate-200/80 dark:border-slate-800/80 text-slate-600 dark:text-slate-400 hover:border-slate-300 dark:hover:border-slate-700'
                        }`}
                      >
                        <span className={`w-1.5 h-1.5 rounded-full ${
                          prio.id === 'URGENT' ? 'bg-rose-500 animate-ping' :
                          prio.id === 'HIGH' ? 'bg-orange-500' :
                          prio.id === 'MEDIUM' ? 'bg-amber-500' : 'bg-slate-400'
                        }`} />
                        <span>{prio.label}</span>
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Detailed Description */}
              <div>
                <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1.5 flex items-center gap-1.5">
                  <FileText className="w-3.5 h-3.5 text-purple-500" />
                  Detailed Description <span className="text-rose-500">*</span>
                </label>
                <textarea
                  rows={3}
                  required
                  value={newDescription}
                  onChange={(e) => setNewDescription(e.target.value)}
                  placeholder="Provide all relevant details, error messages, project tokens, or background information..."
                  className="w-full p-3 text-xs font-medium rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-white placeholder-slate-400 dark:placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-purple-500/20 focus:border-purple-500 resize-none shadow-sm transition-all"
                />
              </div>
            </form>

            {/* Modal Footer */}
            <div className="shrink-0 px-6 py-3.5 border-t border-slate-100 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-800/40 flex items-center justify-between">
              <span className="text-[11px] text-slate-400 dark:text-slate-500 flex items-center gap-1">
                <Lock className="w-3 h-3 text-slate-400" />
                Visible to Org & Super Admins
              </span>
              <div className="flex items-center gap-2.5">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="px-4 py-2 text-xs font-semibold text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white hover:bg-slate-200/60 dark:hover:bg-slate-800 rounded-xl transition-colors cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  form="raise-ticket-form"
                  disabled={submittingTicket || !newTitle.trim() || !newDescription.trim()}
                  className="px-5 py-2 text-xs font-bold bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white rounded-xl shadow-lg shadow-purple-600/25 active:scale-[0.98] transition-all flex items-center gap-1.5 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {submittingTicket && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
                  <span>Submit Ticket</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── Modal: Mark Ticket as Resolved ── */}
      {showResolveModal && (
        <div 
          className="fixed inset-0 z-[9999] flex items-center justify-center p-3 sm:p-4 bg-slate-950/70 backdrop-blur-sm animate-in fade-in duration-200"
          onClick={(e) => {
            if (e.target === e.currentTarget) setShowResolveModal(false);
          }}
        >
          <div className="w-full max-w-md bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl shadow-2xl overflow-hidden max-h-[90vh] flex flex-col my-auto animate-in zoom-in-95 duration-200">
            
            {/* Modal Header */}
            <div className="shrink-0 px-6 py-4 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between bg-slate-50/70 dark:bg-slate-800/40">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-500/15 to-teal-500/25 border border-emerald-200 dark:border-emerald-500/30 text-emerald-600 dark:text-emerald-400 flex items-center justify-center shadow-sm">
                  <CheckCircle className="w-5 h-5" />
                </div>
                <div>
                  <span className="text-[10px] font-bold uppercase tracking-wider text-emerald-600 dark:text-emerald-400 font-mono">
                    {selectedTicket?.ticket_code}
                  </span>
                  <h3 className="text-base font-bold text-slate-900 dark:text-white leading-tight">
                    Resolve Support Ticket
                  </h3>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setShowResolveModal(false)}
                className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors cursor-pointer"
                title="Close modal"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Modal Body */}
            <form id="resolve-ticket-form" onSubmit={handleResolveSubmit} className="flex-1 overflow-y-auto custom-scrollbar p-6 space-y-4">
              <div>
                <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1.5 flex items-center gap-1.5">
                  <FileText className="w-3.5 h-3.5 text-emerald-500" />
                  Resolution Summary / Notes <span className="text-rose-500">*</span>
                </label>
                <textarea
                  rows={3}
                  required
                  value={resolutionSummary}
                  onChange={(e) => setResolutionSummary(e.target.value)}
                  placeholder="Explain how the issue was resolved (e.g. Quota was increased, fix deployed to production, credentials re-issued)..."
                  className="w-full p-3 text-xs font-medium rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-white placeholder-slate-400 dark:placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-emerald-500/20 focus:border-emerald-500 resize-none shadow-sm transition-all"
                />
              </div>
            </form>

            {/* Modal Footer */}
            <div className="shrink-0 px-6 py-3.5 border-t border-slate-100 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-800/40 flex items-center justify-between">
              <span className="text-[11px] text-slate-400 dark:text-slate-500 flex items-center gap-1">
                <CheckCircle2 className="w-3 h-3 text-emerald-500" />
                Notifies reporter & admins
              </span>
              <div className="flex items-center gap-2.5">
                <button
                  type="button"
                  onClick={() => setShowResolveModal(false)}
                  className="px-4 py-2 text-xs font-semibold text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white hover:bg-slate-200/60 dark:hover:bg-slate-800 rounded-xl transition-colors cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  form="resolve-ticket-form"
                  disabled={resolvingTicket}
                  className="px-5 py-2 text-xs font-bold bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl shadow-lg shadow-emerald-600/25 active:scale-[0.98] transition-all flex items-center gap-1.5 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {resolvingTicket && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
                  <span>Confirm Resolution</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}
