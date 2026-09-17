import React, { useState, useEffect, useRef, useMemo } from 'react';
import { MessageSquare, X, Send, Minimize2, Maximize2, Sparkles, Loader2, ChevronDown, Bot, Mic, MicOff, RefreshCw } from 'lucide-react';
import { useLocation } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { API_ENDPOINTS } from '../config';

// Add CSS animations
const styles = `
  @keyframes fadeIn {
    from {
      opacity: 0;
      transform: translateY(10px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }
  
  .animate-fadeIn {
    animation: fadeIn 0.3s ease-out forwards;
  }
  
  @keyframes blink {
    0%, 90%, 100% {
      transform: scaleY(1);
    }
    95% {
      transform: scaleY(0.1);
    }
  }
  
  .blinking .eyelid {
    animation: blink 0.15s ease-in-out;
  }
  
  .border-b-3 {
    border-bottom-width: 3px;
  }
`;

// Route-to-context mapping with comprehensive application knowledge
const ROUTE_CONTEXTS = {
  '/': {
    title: 'Landing Page',
    description: 'Welcome to the AI-powered project management platform. Start by signing up or logging in.',
  },
  '/signup': {
    title: 'Organization Registration',
    description: 'Create your organization account. You\'ll become the admin and can invite team members later.',
  },
  '/invite': {
    title: 'Team Invitation',
    description: 'You\'ve been invited to join an organization. Complete your account setup here.',
  },
  '/login': {
    title: 'Sign In',
    description: 'Access your organization\'s projects and AI agents.',
  },
  '/forgot-password': {
    title: 'Forgot Password',
    description: 'Reset your account password.',
  },
  '/reset-password': {
    title: 'Reset Password',
    description: 'Set a new password for your account.',
  },
  '/how-it-works': {
    title: 'How It Works',
    description: 'Learn how the AI-powered project management platform works end-to-end.',
  },
  '/dashboard': {
    title: 'Project Dashboard',
    description: 'Your main project hub — view progress, roadmap steps, and navigate to any stage.',
  },
  '/new-project/governance': {
    title: 'Governance Questionnaire',
    description: 'Answer questions across 6 dimensions to classify your project and extract requirements.',
  },
  '/new-project': {
    title: 'New Project',
    description: 'Start a new project by providing basic information and governance details.',
  },
  '/prerequisites': {
    title: 'Prerequisite Classification',
    description: 'Review AI-extracted prerequisites and provide the necessary information for your project.',
  },
  '/agent-analysis': {
    title: 'Agent Analysis',
    description: 'The AI is analyzing your project requirements and governance answers to build a comprehensive understanding.',
  },
  '/task-creation': {
    title: 'Task Generation',
    description: 'AI generates a comprehensive task plan with sprints, milestones, and individual tasks.',
  },
  '/resource-onboarding': {
    title: 'AI Agent Onboarding',
    description: 'Request AI agents to work on your project tasks.',
  },
  '/status-dashboard': {
    title: 'Project Status Dashboard',
    description: 'Monitor your project progress, agent execution, and task completion in real-time.',
  },
  '/agents': {
    title: 'Agents Overview',
    description: 'View and manage all AI agents across your organization.',
  },
  '/organization-admin': {
    title: 'Organization Admin',
    description: 'Manage your organization — users, roles, quotas, and settings.',
  },
  '/governance-management': {
    title: 'Governance Management',
    description: 'Configure and manage governance templates and scoring dimensions for your organization.',
  },
  '/plugins': {
    title: 'Plugins',
    description: 'Connect and manage integrations like GitHub, Azure DevOps, and other tools.',
  },
  '/a/': {
    title: 'Project View',
    description: 'Viewing a specific project\'s live status and agent activity.',
  },
};

const AssistantBot = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [isMinimized, setIsMinimized] = useState(false);
  const [messages, setMessages] = useState([]);
  const [inputValue, setInputValue] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [currentContext, setCurrentContext] = useState(null);
  const [eyePosition, setEyePosition] = useState({ x: 0, y: 0 });
  const [isListening, setIsListening] = useState(false);
  const [lastActivity, setLastActivity] = useState(Date.now());
  const [hasShownPageWelcome, setHasShownPageWelcome] = useState(false);
  const hasShownWelcomeRef = useRef(false);
  const [idleMessageShown, setIdleMessageShown] = useState(false);
  const [isUserIdle, setIsUserIdle] = useState(false);
  const messagesEndRef = useRef(null);
  const location = useLocation();

  const handleIdleMessage = () => {
    const idleMsg = {
      id: Date.now(),
      type: 'bot',
      text: "👋 Hey! I noticed you've been idle. Need any help? I'm here if you have questions!",
      timestamp: new Date(),
      isIdle: true
    };
    setMessages(prev => [...prev, idleMsg]);

    if (!isOpen) {
      setIsOpen(true);
    }
  };
  // Animated eyes effect for the floating ball
  useEffect(() => {
    if (!isOpen) {
      const interval = setInterval(() => {
        const randomX = (Math.random() - 0.5) * 6;
        const randomY = (Math.random() - 0.5) * 4;
        setEyePosition({ x: randomX, y: randomY });
      }, 2000 + Math.random() * 3000);

      return () => clearInterval(interval);
    }
  }, [isOpen]);

  // Add blinking animation
  useEffect(() => {
    if (!isOpen) {
      const blinkInterval = setInterval(() => {
        // Trigger blink animation by adding a class temporarily
        const ball = document.querySelector('.bot-face');
        if (ball) {
          ball.classList.add('blinking');
          setTimeout(() => {
            ball.classList.remove('blinking');
          }, 150);
        }
      }, 3000 + Math.random() * 4000); // Random blink every 3-7 seconds

      return () => clearInterval(blinkInterval);
    }
  }, [isOpen]);

  // Shared streaming helper — calls the stream endpoint and appends chunks to a message by id
  const streamToMessage = async (msgId, prompt, context) => {
    const token = localStorage.getItem('token');
    try {
      const response = await fetch(API_ENDPOINTS.AI_CHAT_STREAM, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({ message: prompt, context })
      });

      if (response.status === 402) {
        const errorMsg = "⚠️ **Token Quota Exhausted**: Your allocated token balance has run out. Please request a quota top-up to continue chatting with the AI Assistant.";
        setMessages(prev => prev.map(m => m.id === msgId ? { ...m, text: errorMsg, isError: true } : m));
        return errorMsg;
      }

      if (response.status === 403) {
        const errData = await response.json().catch(() => ({}));
        const detail = errData?.detail || 'Access Denied';
        const errorMsg = `⚠️ **Access Denied**: ${detail}`;
        setMessages(prev => prev.map(m => m.id === msgId ? { ...m, text: errorMsg, isError: true } : m));
        return errorMsg;
      }

      if (response.ok && response.body) {
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let accumulated = '';
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          const lines = decoder.decode(value, { stream: true }).split('\n');
          for (const line of lines) {
            if (!line.startsWith('data: ')) continue;
            const data = line.slice(6).trim();
            if (data === '[DONE]') continue;
            try {
              const parsed = JSON.parse(data);
              if (parsed.error) {
                const isExhausted = typeof parsed.error === 'string' && (parsed.error.includes('EXHAUSTED') || parsed.error.includes('quota') || parsed.error.includes('402'));
                const errorMsg = isExhausted
                  ? "⚠️ **Token Quota Exhausted**: Your allocated token balance has run out. Please request a quota top-up to continue chatting with the AI Assistant."
                  : `⚠️ **AI Error**: ${parsed.error}`;
                accumulated = errorMsg;
                setMessages(prev => prev.map(m => m.id === msgId ? { ...m, text: errorMsg, isError: true } : m));
                return accumulated;
              }
              if (parsed.content) {
                accumulated += parsed.content;
                setMessages(prev => prev.map(m => m.id === msgId ? { ...m, text: accumulated } : m));
              }
            } catch { /* skip malformed chunks */ }
          }
        }
        return accumulated;
      } else {
        // fallback: non-streaming
        const data = await response.json().catch(() => null);
        const detail = data?.detail || data?.error || data?.response || '';
        if (detail && typeof detail === 'string' && (detail.includes('EXHAUSTED') || detail.includes('quota') || detail.includes('402'))) {
          const text = "⚠️ **Token Quota Exhausted**: Your allocated token balance has run out. Please request a quota top-up to continue chatting with the AI Assistant.";
          setMessages(prev => prev.map(m => m.id === msgId ? { ...m, text, isError: true } : m));
          return text;
        }
        const text = data?.response || data?.detail || '';
        setMessages(prev => prev.map(m => m.id === msgId ? { ...m, text, isError: !response.ok } : m));
        return text;
      }
    } catch (err) {
      console.error('Stream error:', err);
      const errorMsg = "⚠️ Unable to reach the AI Assistant service. Please verify your network connection and try again.";
      setMessages(prev => prev.map(m => m.id === msgId ? { ...m, text: errorMsg, isError: true } : m));
      return errorMsg;
    }
  };

  // Get current route context and show AI-generated page welcome
  useEffect(() => {
    const path = location.pathname;
    const matchedRoute = Object.keys(ROUTE_CONTEXTS)
      .sort((a, b) => b.length - a.length)
      .find(route => path === route || path.startsWith(route + '/') || (route.endsWith('/') && path.startsWith(route)));
    const context = matchedRoute ? ROUTE_CONTEXTS[matchedRoute] : null;

    setCurrentContext(context);
    hasShownWelcomeRef.current = false;
    setIdleMessageShown(false);
    setMessages([]);
  }, [location.pathname]);

  const showPageWelcome = () => { hasShownWelcomeRef.current = false; };

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSend = async () => {
    if (!inputValue.trim()) return;

    const userMsg = { id: Date.now(), type: 'user', text: inputValue, timestamp: new Date() };
    const botId = Date.now() + 1;
    const sentInput = inputValue;

    setMessages(prev => [...prev, userMsg, { id: botId, type: 'bot', text: '', timestamp: new Date() }]);
    setInputValue('');
    setIsTyping(true);

    const context = currentContext || ROUTE_CONTEXTS['/'];
    const result = await streamToMessage(botId, sentInput, { currentStep: context?.title, currentPath: location.pathname });

    if (!result) {
      setMessages(prev => prev.map(m => m.id === botId ? { ...m, text: `I'm here to help with **${context?.title}**. What would you like to know?` } : m));
    }

    setIsTyping(false);
  };
  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const clearChat = async () => {
    hasShownWelcomeRef.current = false;
    const context = currentContext;
    if (!context) { setMessages([]); return; }
    const msgId = Date.now();
    setMessages([{ id: msgId, type: 'bot', text: '', timestamp: new Date(), isWelcome: true }]);
    const prompt = `I just navigated to the "${context.title}" page (path: ${location.pathname}). Based on the platform context you know, describe what this page is about, what I can do here, and why it matters in the workflow. Be specific and practical.`;
    const result = await streamToMessage(msgId, prompt, { currentStep: context.title, currentPath: location.pathname });
    if (!result) {
      setMessages([{ id: msgId, type: 'bot', text: `**${context.title}** — ${context.description}\n\nAsk me anything!`, timestamp: new Date(), isWelcome: true }]);
    }
  };

  const handleBotClick = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsOpen(true);
  };

  const toggleVoiceInput = () => {
    setIsListening(!isListening);
  };

  // Animated floating ball component with realistic face
  const FloatingBall = () => (
    <div
      onClick={() => setIsOpen(true)}
      className="fixed bottom-6 right-6 z-[250] cursor-pointer group"
      style={{ pointerEvents: 'auto' }}
    >
      {/* Glow effect - enhanced when idle */}
      <div className={`absolute inset-0 bg-gradient-to-r from-violet-600 to-purple-600 rounded-full blur-xl transition-opacity duration-300 ${isUserIdle ? 'opacity-90 animate-pulse' : 'opacity-60 group-hover:opacity-80'
        }`}></div>

      {/* Main ball */}
      <div className={`bot-face relative w-12 h-12 bg-gradient-to-br from-violet-400 via-purple-500 to-indigo-600 rounded-full shadow-2xl hover:shadow-violet-500/50 hover:scale-110 transition-all duration-300 flex items-center justify-center overflow-hidden ${isUserIdle ? 'animate-bounce' : ''
        }`}>
        {/* Shine effect */}
        <div className="absolute top-1.5 left-1.5 w-3 h-3 bg-white/40 rounded-full blur-sm"></div>
        <div className="absolute top-2 left-2 w-1 h-1 bg-white/60 rounded-full"></div>

        {/* Face container */}
        <div className="relative w-full h-full flex flex-col items-center justify-center">
          {/* Eyes container */}
          <div className="flex items-center gap-1 mb-0.5">
            {/* Left eye */}
            <div className="w-2.5 h-2.5 bg-white rounded-full relative overflow-hidden shadow-inner">
              <div
                className={`w-2 h-2 bg-gray-800 rounded-full absolute top-0.5 left-0.5 transition-all duration-500 ease-out ${isUserIdle ? 'animate-pulse' : ''
                  }`}
                style={{
                  transform: `translate(${eyePosition.x * 0.5}px, ${eyePosition.y * 0.5}px)`
                }}
              >
                <div className="w-0.5 h-0.5 bg-white rounded-full absolute top-0.5 left-0.5"></div>
              </div>
              <div className="eyelid absolute inset-0 bg-violet-500 rounded-full transform -translate-y-full transition-transform duration-150"></div>
            </div>

            {/* Right eye */}
            <div className="w-2.5 h-2.5 bg-white rounded-full relative overflow-hidden shadow-inner">
              <div
                className={`w-2 h-2 bg-gray-800 rounded-full absolute top-0.5 left-0.5 transition-all duration-500 ease-out ${isUserIdle ? 'animate-pulse' : ''
                  }`}
                style={{
                  transform: `translate(${eyePosition.x * 0.5}px, ${eyePosition.y * 0.5}px)`
                }}
              >
                <div className="w-0.5 h-0.5 bg-white rounded-full absolute top-0.5 left-0.5"></div>
              </div>
              <div className="eyelid absolute inset-0 bg-violet-500 rounded-full transform -translate-y-full transition-transform duration-150"></div>
            </div>
          </div>

          {/* Mouth */}
          <div className="w-4 h-2 border-b-2 border-white/80 rounded-full"></div>
        </div>

        {/* Idle indicator */}
        {isUserIdle && (
          <div className="absolute -top-2 -left-2 w-5 h-5 bg-orange-400 text-white text-xs rounded-full flex items-center justify-center font-bold animate-bounce shadow-lg">
            💭
          </div>
        )}

        <div className="absolute inset-0 rounded-full bg-gradient-to-br from-yellow-300/20 to-pink-300/20 opacity-0 group-hover:opacity-100 transition-opacity duration-300"></div>
      </div>

      {/* Notification badge */}
      {messages.length > 0 && (
        <div className="absolute -top-1 -right-1 w-6 h-6 bg-red-500 text-white text-xs rounded-full flex items-center justify-center font-bold animate-bounce shadow-lg border-2 border-white">
          {messages.filter(m => m.isIdle || m.isWelcome).length > 0 ? '💡' : '!'}
        </div>
      )}

      {/* Idle message tooltip */}
      {isUserIdle && (
        <div className="absolute bottom-full right-0 mb-3 bg-gray-800 text-white text-xs px-4 py-2 rounded-lg shadow-xl animate-fadeIn max-w-48">
          I have something to tell you! 💭
          <div className="absolute top-full right-6 w-0 h-0 border-l-4 border-r-4 border-t-4 border-l-transparent border-r-transparent border-t-gray-800"></div>
        </div>
      )}

      {/* Click ripple effect */}
      <div className="absolute inset-0 rounded-full bg-white/30 scale-0 group-active:scale-150 transition-transform duration-200 pointer-events-none"></div>
    </div>
  );
  return (
    <>
      {!isOpen && <FloatingBall />}

      {isOpen && (
        <div
          className={`fixed z-[250] backdrop-blur-xl border shadow-2xl transition-all duration-300 ${isMinimized
              ? 'bottom-6 right-6 w-72 h-14'
              : 'bottom-6 right-6 w-[360px] h-[520px] flex flex-col'
            }`}
          style={{
            borderRadius: '20px',
            background: 'rgba(255, 255, 255, 0.95)',
            border: '1px solid rgba(139, 92, 246, 0.2)',
            boxShadow: '0 25px 80px rgba(0, 0, 0, 0.15), 0 0 0 1px rgba(139, 92, 246, 0.1)'
          }}
        >
          <div className="flex items-center justify-between p-4 border-b border-app-text-label/20 bg-gradient-to-r from-violet-600 via-purple-600 to-indigo-600 text-white rounded-t-[20px] relative overflow-hidden">
            <div className="flex items-center gap-3 relative z-10">
              <div className="w-10 h-10 rounded-full bg-white/20 backdrop-blur-sm flex items-center justify-center border border-white/30">
                <Bot className="w-6 h-6 animate-pulse" />
              </div>
              <div>
                <h3 className="font-bold text-base flex items-center gap-2">
                  AI Assistant
                  <div className="w-2 h-2 bg-green-400 rounded-full animate-pulse"></div>
                </h3>
                <p className="text-xs text-white/80 font-medium">
                  {currentContext?.title || 'Ready to help'} • {messages.length} messages
                </p>
              </div>
            </div>
            <div className="flex items-center gap-1 relative z-10">
              <button
                onClick={clearChat}
                className="p-2 rounded-lg hover:bg-white/20 transition-all duration-200 hover:scale-110"
                title="Clear chat"
              >
                <RefreshCw className="w-4 h-4" />
              </button>
              <button
                onClick={() => setIsMinimized(!isMinimized)}
                className="p-2 rounded-lg hover:bg-white/20 transition-all duration-200 hover:scale-110"
                title={isMinimized ? "Maximize" : "Minimize"}
              >
                {isMinimized ? <Maximize2 className="w-4 h-4" /> : <Minimize2 className="w-4 h-4" />}
              </button>
              <button
                onClick={() => setIsOpen(false)}
                className="p-2 rounded-lg hover:bg-red-500/30 transition-all duration-200 hover:scale-110"
                title="Close chat"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>
          {!isMinimized && (
            <>
              <div className="flex-1 overflow-y-auto p-4 space-y-4 min-h-0 bg-gradient-to-b from-transparent to-app-bg-card/30">
                {messages.map((msg, index) => (
                  <div
                    key={msg.id}
                    className={`flex ${msg.type === 'user' ? 'justify-end' : 'justify-start'} animate-fadeIn`}
                    style={{ animationDelay: `${index * 0.1}s` }}
                  >
                    <div className={`flex items-end gap-2 max-w-[85%] ${msg.type === 'user' ? 'flex-row-reverse' : 'flex-row'}`}>
                      <div className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 ${msg.type === 'user'
                          ? 'bg-gradient-to-r from-violet-600 to-purple-600 text-white'
                          : msg.isWelcome
                            ? 'bg-gradient-to-r from-green-500 to-emerald-500 text-white'
                            : msg.isIdle
                              ? 'bg-gradient-to-r from-orange-500 to-amber-500 text-white'
                              : 'bg-gradient-to-r from-blue-500 to-cyan-500 text-white'
                        }`}>
                        {msg.type === 'user' ? (
                          <div className="w-5 h-5 bg-white/30 rounded-full"></div>
                        ) : msg.isWelcome ? (
                          <span className="text-sm">👋</span>
                        ) : msg.isIdle ? (
                          <span className="text-sm">💭</span>
                        ) : (
                          <Bot className="w-5 h-5" />
                        )}
                      </div>

                      <div
                        className={`rounded-2xl px-4 py-3 text-sm relative ${msg.type === 'user'
                            ? 'bg-gradient-to-r from-violet-600 to-purple-600 text-white shadow-lg shadow-violet-500/30'
                            : msg.isWelcome
                              ? 'bg-gradient-to-r from-green-50 to-emerald-50 text-green-800 border border-green-200 shadow-lg'
                              : msg.isIdle
                                ? 'bg-gradient-to-r from-orange-50 to-amber-50 text-orange-800 border border-orange-200 shadow-lg'
                                : 'bg-white/90 backdrop-blur-sm text-gray-800 border border-gray-200/50 shadow-lg'
                          }`}
                      >
                        {(msg.isWelcome || msg.isIdle) && (
                          <div className={`text-xs font-semibold mb-2 ${msg.isWelcome ? 'text-green-600' : 'text-orange-600'
                            }`}>
                            {msg.isWelcome ? '🎉 Welcome Guide' : '💭 Friendly Check-in'}
                          </div>
                        )}

                        <div className="prose prose-sm max-w-none leading-relaxed
                          prose-p:my-1 prose-ul:my-1 prose-ol:my-1 prose-li:my-0
                          prose-headings:my-1 prose-strong:font-semibold
                          prose-code:bg-black/10 prose-code:px-1 prose-code:rounded
                          prose-a:text-violet-600 prose-a:underline">
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>
                            {msg.text}
                          </ReactMarkdown>
                        </div>
                        <div
                          className={`text-xs mt-2 ${msg.type === 'user' ? 'text-white/70' : 'text-gray-500'
                            }`}
                        >
                          {msg.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
                {isTyping && messages[messages.length - 1]?.text === '' && (
                  <div className="flex justify-start animate-fadeIn">
                    <div className="flex items-end gap-2">
                      <div className="w-8 h-8 rounded-full bg-gradient-to-r from-blue-500 to-cyan-500 text-white flex items-center justify-center">
                        <Bot className="w-5 h-5" />
                      </div>
                      <div className="bg-white/90 backdrop-blur-sm rounded-2xl px-4 py-3 flex items-center gap-2 shadow-lg border border-gray-200/50">
                        <div className="flex gap-1">
                          <div className="w-2 h-2 bg-violet-500 rounded-full animate-bounce"></div>
                          <div className="w-2 h-2 bg-violet-500 rounded-full animate-bounce" style={{ animationDelay: '0.1s' }}></div>
                          <div className="w-2 h-2 bg-violet-500 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }}></div>
                        </div>
                        <span className="text-xs text-gray-500 ml-2">Thinking...</span>
                      </div>
                    </div>
                  </div>
                )}
                <div ref={messagesEndRef} />
              </div>

              <div className="p-4 bg-gradient-to-r from-gray-50 to-white border-t border-gray-200/50 flex-shrink-0" style={{ borderRadius: '0 0 20px 20px' }}>
                <div className="flex items-center gap-3">
                  <div className="flex-1 relative">
                    <input
                      type="text"
                      value={inputValue}
                      onChange={(e) => setInputValue(e.target.value)}
                      onKeyPress={handleKeyPress}
                      placeholder="Type your message..."
                      className="w-full bg-white border-2 border-gray-200 rounded-xl px-4 py-3 text-sm text-gray-800 placeholder-gray-400 focus:outline-none focus:border-violet-500 focus:ring-4 focus:ring-violet-500/20 transition-all duration-200 pr-12"
                    />
                    {inputValue && (
                      <button
                        onClick={() => setInputValue('')}
                        className="absolute right-3 top-1/2 transform -translate-y-1/2 text-gray-400 hover:text-gray-600 transition-colors"
                      >
                        <X className="w-4 h-4" />
                      </button>
                    )}
                  </div>

                  <button
                    onClick={toggleVoiceInput}
                    className={`p-3 rounded-xl transition-all duration-200 hover:scale-110 ${isListening
                        ? 'bg-red-500 text-white shadow-lg shadow-red-500/40'
                        : 'bg-gray-200 text-gray-600 hover:bg-gray-300'
                      }`}
                    title={isListening ? "Stop listening" : "Voice input"}
                  >
                    {isListening ? <MicOff className="w-5 h-5" /> : <Mic className="w-5 h-5" />}
                  </button>

                  <button
                    onClick={handleSend}
                    disabled={!inputValue.trim()}
                    className="p-3 bg-gradient-to-r from-violet-600 to-purple-600 text-white rounded-xl hover:shadow-lg hover:shadow-violet-500/40 hover:scale-110 disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:scale-100 disabled:hover:shadow-none transition-all duration-200"
                    title="Send message"
                  >
                    <Send className="w-5 h-5" />
                  </button>
                </div>

                <div className="flex items-center justify-between mt-3 text-xs text-gray-500">
                  <div className="flex items-center gap-2">
                    <div className="flex items-center gap-1">
                      <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
                      <span>Online</span>
                    </div>
                    {isListening && (
                      <div className="flex items-center gap-1 text-red-500">
                        <div className="w-2 h-2 bg-red-500 rounded-full animate-pulse"></div>
                        <span>Listening...</span>
                      </div>
                    )}
                  </div>
                  <div className="text-right">
                    <span>Press Enter to send</span>
                  </div>
                </div>
              </div>
            </>
          )}
        </div>
      )}
    </>
  );
};

export default AssistantBot;