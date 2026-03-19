import React, { useState, useEffect, useRef, useMemo } from 'react';
import { MessageSquare, X, Send, Minimize2, Maximize2, Sparkles, Loader2, ChevronDown, Bot, Mic, MicOff, RefreshCw } from 'lucide-react';
import { useLocation } from 'react-router-dom';
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
    tips: [
      'Click "Get Started" to create your organization account',
      'Use "Sign In" if you already have an account',
      'Learn more about AI-powered project management'
    ],
    nextSteps: ['Sign up for a new organization', 'Log in to existing account'],
    workflow: 'Entry Point → Authentication → Project Creation'
  },
  '/signup': {
    title: 'Organization Registration',
    description: 'Create your organization account. You\'ll become the admin and can invite team members later.',
    tips: [
      'Enter your first and last name',
      'Choose a unique organization name',
      'Use your business email address',
      'Create a strong password for security'
    ],
    fields: {
      'First Name': 'Your personal first name',
      'Last Name': 'Your personal last name', 
      'Organization Name': 'Your company or team name - this will be used throughout the platform',
      'Email': 'Your business email - this will be your login username',
      'Password': 'Secure password - you\'ll use this to sign in'
    },
    nextSteps: ['Complete registration', 'Verify email', 'Log in to start first project'],
    workflow: 'Registration → Login → New Project'
  },
  '/login': {
    title: 'Sign In',
    description: 'Access your organization\'s projects and AI agents.',
    tips: [
      'Enter the email you used during registration',
      'Use your organization password',
      'Try SSO if your organization has it configured',
      'Use "Forgot Password" if needed'
    ],
    fields: {
      'Email': 'The email address you registered with',
      'Password': 'Your account password'
    },
    nextSteps: ['Access Status Dashboard', 'Create new project', 'View existing projects'],
    workflow: 'Login → Status Dashboard → Project Management'
  },
  '/new-project': {
    title: 'Project Initiation',
    description: 'Start a new project by providing basic information and governance details.',
    tips: [
      'Enter a descriptive project name',
      'This will create a new project in your organization',
      'You\'ll proceed to governance questionnaire next'
    ],
    fields: {
      'Project Name': 'A clear, descriptive name for your project'
    },
    nextSteps: ['Enter project name', 'Proceed to governance questionnaire'],
    workflow: 'Project Name → Governance Form → Prerequisites → Task Creation'
  },
  '/new-project/governance': {
    title: 'Governance Questionnaire',
    description: 'Answer questions across 6 dimensions to classify your project and extract requirements.',
    tips: [
      'Answer questions about Business Value, Data Sensitivity, Integration Complexity',
      'Consider Operational Impact, AI Risk, and Ownership & Support',
      'You can skip questions if unsure',
      'AI will analyze your answers to extract prerequisites'
    ],
    nextSteps: ['Complete all 6 dimensions', 'Review answers', 'Submit for AI analysis'],
    workflow: 'Governance Questions → AI Analysis → Prerequisites Classification'
  },
  '/prerequisites': {
    title: 'Prerequisite Classification',
    description: 'Review AI-extracted prerequisites and provide the necessary information for your project.',
    tips: [
      'Review prerequisites grouped by category (Credentials, APIs, Infrastructure, etc.)',
      'Provide values for each required prerequisite',
      'Mark sensitive information as "secret" to protect from AI',
      'Configure your Git repository connection',
      'Select the process mode for your team'
    ],
    nextSteps: ['Provide prerequisite values', 'Configure Git repository', 'Select process mode', 'Proceed to task creation'],
    workflow: 'Prerequisites → Git Setup → Process Mode → Task Creation'
  },
  '/task-creation': {
    title: 'Task Generation',
    description: 'AI generates a comprehensive task plan with sprints, milestones, and individual tasks.',
    tips: [
      'Set your project deadline for proper planning',
      'Review the AI-generated task plan',
      'Tasks are organized into sprints and milestones',
      'Download the plan as CSV if needed',
      'Create tasks in your external task management system'
    ],
    nextSteps: ['Set project deadline', 'Review generated tasks', 'Create tasks in system', 'Proceed to resource onboarding'],
    workflow: 'Task Generation → Task Review → Task Creation → Resource Onboarding'
  },
  '/resource-onboarding': {
    title: 'AI Agent Onboarding',
    description: 'Request AI agents to work on your project tasks.',
    tips: [
      'Specify how many Shared Dev and Test agents you need',
      'Request Dedicated agents for exclusive project work',
      'Check your organization\'s agent quota',
      'Shared agents work across multiple projects',
      'Dedicated agents focus only on your project'
    ],
    nextSteps: ['Specify agent requirements', 'Check quota availability', 'Submit agent request', 'Monitor in Status Dashboard'],
    workflow: 'Agent Request → Quota Check → Agent Allocation → Status Dashboard'
  },
  '/status-dashboard': {
    title: 'Project Status Dashboard',
    description: 'Monitor your project progress, agent execution, and task completion in real-time.',
    tips: [
      'View all your agents and their current status',
      'Run agents manually or let them auto-execute',
      'Monitor task progress and completion',
      'View agent logs and error messages',
      'Download progress reports'
    ],
    nextSteps: ['Monitor agent progress', 'Review completed work', 'Handle any failures', 'Download final reports'],
    workflow: 'Agent Monitoring → Progress Tracking → Issue Resolution → Project Completion'
  }
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

  // Get current route context and show proactive welcome
  useEffect(() => {
    const path = location.pathname;
    // Sort routes longest-first so specific routes match before '/'
    const matchedRoute = Object.keys(ROUTE_CONTEXTS)
      .sort((a, b) => b.length - a.length)
      .find(route => path === route || path.startsWith(route + '/'));
    const context = matchedRoute ? ROUTE_CONTEXTS[matchedRoute] : null;
    
    setCurrentContext(context);
    setHasShownPageWelcome(false);
    hasShownWelcomeRef.current = false;
    setIdleMessageShown(false);
    
    if (context) {
      setMessages([]);
      setTimeout(() => {
        showPageWelcome(context, path);
      }, 2000);
    }
  }, [location.pathname]);

  const showPageWelcome = (context, path) => {
    if (hasShownWelcomeRef.current) return;
    hasShownWelcomeRef.current = true;

    const welcomeMessages = {
      '/': "👋 Welcome! This is the entry point to your AI-powered project management platform.\n\nFrom here you can sign up to create a new organization or log in to an existing one. Everything starts here — your projects, your AI agents, and your team all live under the organization you create.",
      '/signup': "� This is the Organization Registration' page — one of the most important steps!\n\nYou're creating the admin account for your organization. The organization name you choose will be used across the entire platform. As admin, you'll be able to invite team members, manage projects, and control agent quotas.\n\nTip: Use your business email — it becomes your login username.",
      '/login': "🔐 This is the Sign In page.\n\nEnter the email and password you registered with to access your organization's projects and AI agents. All your project history, agent statuses, and task progress are waiting for you inside.",
      '/new-project': "🚀 You're starting a new project!\n\nThis is where it all begins. Give your project a clear, descriptive name — it'll be used throughout the platform. After this, you'll go through a governance questionnaire that helps the AI understand your project's complexity and requirements.",
      '/new-project/governance': "📋 This is the Governance Questionnaire — a critical step!\n\nYou'll answer questions across 6 dimensions: Business Value, Data Sensitivity, Integration Complexity, Operational Impact, AI Risk, and Ownership & Support.\n\nYour answers directly shape how the AI classifies your project and extracts the prerequisites it needs. Take your time here — the quality of your answers determines the quality of everything that follows.",
      '/prerequisites': "🔧 This is the Prerequisite Classification page.\n\nThe AI has analyzed your governance answers and extracted everything your project needs — credentials, API keys, infrastructure details, and more. You need to provide values for each item here before the AI agents can start working.\n\nMark anything sensitive as a secret so it stays protected. Also configure your Git repository connection and choose your process mode.",
      '/task-creation': "📝 This is the Task Generation page — where your project plan comes to life!\n\nThe AI generates a full task breakdown with sprints, milestones, and individual tasks based on everything you've provided. Set your project deadline first so the plan is properly scheduled.\n\nReview the tasks carefully, then create them in your external task management system to kick off execution.",
      '/resource-onboarding': "🤖 This is the AI Agent Onboarding page.\n\nHere you request the AI agents that will actually do the work on your project. You can choose Shared agents (cost-effective, work across multiple projects) or Dedicated agents (exclusive to your project, faster execution).\n\nCheck your organization's quota before requesting — once agents are allocated, they'll appear in your Status Dashboard ready to run.",
      '/status-dashboard': "📊 Welcome to your Project Command Center!\n\nThis is where you monitor everything in real-time — agent statuses, task progress, logs, and completion rates. You can trigger agents manually, review their output, handle failures, and track your project all the way to completion.\n\nThis page is your main hub once your project is running."
    };

    // Match the most specific path
    const matchedKey = Object.keys(welcomeMessages)
      .sort((a, b) => b.length - a.length)
      .find(key => path === key || path.startsWith(key + '/'));

    const welcomeText = matchedKey
      ? welcomeMessages[matchedKey]
      : `👋 You're on the ${context?.title} page.\n\n${context?.description}`;

    const welcomeMsg = {
      id: Date.now(),
      type: 'bot',
      text: `${welcomeText}\n\nNeed help with anything? Just ask! 😊`,
      timestamp: new Date(),
      isWelcome: true
    };

    setMessages([welcomeMsg]);
    setHasShownPageWelcome(true);
  };
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const generateResponse = (userMessage) => {
    const lowerMsg = userMessage.toLowerCase();
    const context = currentContext || ROUTE_CONTEXTS['/'];
    
    if (lowerMsg.includes('hello') || lowerMsg.includes('hi')) {
      return `👋 Hello! I'm your AI assistant for **${context?.title}**.\n\n${context?.description || ''}\n\nWhat would you like to know?`;
    }

    if (lowerMsg.includes('help')) {
      return `I can help you with **${context?.title}**:\n\n${context?.tips ? context.tips.map(tip => `• ${tip}`).join('\n') : 'Navigate through the application'}`;
    }

    if (lowerMsg.includes('next') || lowerMsg.includes('what should i do')) {
      return `Your next steps are:\n${context?.nextSteps ? context.nextSteps.map((step, i) => `${i + 1}. ${step}`).join('\n') : 'Follow the on-screen instructions'}`;
    }

    return `I'm here to help you with **${context?.title}**. ${context?.description || ''}\n\nYou can ask me:\n• "What should I do next?"\n• "Help me with this step"\n• "What is [field name]?"`;
  };

  const handleSend = async () => {
    if (!inputValue.trim()) return;

    const userMsg = {
      id: Date.now(),
      type: 'user',
      text: inputValue,
      timestamp: new Date()
    };

    setMessages(prev => [...prev, userMsg]);
    setInputValue('');
    setIsTyping(true);

    try {
      const token = localStorage.getItem('token');
      const context = currentContext || ROUTE_CONTEXTS['/'];
      
      const response = await fetch(API_ENDPOINTS.AI_CHAT || '/api/agent/assistant', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          message: inputValue,
          context: {
            currentStep: context?.title,
            currentPath: location.pathname
          }
        })
      });

      let botResponseText;
      
      if (response.ok) {
        const data = await response.json();
        botResponseText = data.response || generateResponse(inputValue);
      } else {
        botResponseText = generateResponse(inputValue);
      }

      const botMsg = {
        id: Date.now() + 1,
        type: 'bot',
        text: botResponseText,
        timestamp: new Date()
      };
      setMessages(prev => [...prev, botMsg]);
    } catch (error) {
      console.error('AI chat error:', error);
      const botMsg = {
        id: Date.now() + 1,
        type: 'bot',
        text: generateResponse(inputValue),
        timestamp: new Date()
      };
      setMessages(prev => [...prev, botMsg]);
    } finally {
      setIsTyping(false);
    }
  };
  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const clearChat = () => {
    setMessages([]);
    if (currentContext) {
      showPageWelcome(currentContext, location.pathname);
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
      className="fixed bottom-6 right-6 z-[1000] cursor-pointer group"
      style={{ pointerEvents: 'auto' }}
    >
      {/* Glow effect - enhanced when idle */}
      <div className={`absolute inset-0 bg-gradient-to-r from-violet-600 to-purple-600 rounded-full blur-xl transition-opacity duration-300 ${
        isUserIdle ? 'opacity-90 animate-pulse' : 'opacity-60 group-hover:opacity-80'
      }`}></div>
      
      {/* Main ball */}
      <div className={`bot-face relative w-12 h-12 bg-gradient-to-br from-violet-400 via-purple-500 to-indigo-600 rounded-full shadow-2xl hover:shadow-violet-500/50 hover:scale-110 transition-all duration-300 flex items-center justify-center overflow-hidden ${
        isUserIdle ? 'animate-bounce' : ''
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
                className={`w-2 h-2 bg-gray-800 rounded-full absolute top-0.5 left-0.5 transition-all duration-500 ease-out ${
                  isUserIdle ? 'animate-pulse' : ''
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
                className={`w-2 h-2 bg-gray-800 rounded-full absolute top-0.5 left-0.5 transition-all duration-500 ease-out ${
                  isUserIdle ? 'animate-pulse' : ''
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
          className={`fixed z-[1000] backdrop-blur-xl border shadow-2xl transition-all duration-300 ${
            isMinimized
              ? 'bottom-6 right-6 w-80 h-16'
              : 'bottom-6 right-6 w-[420px] h-[650px] flex flex-col'
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
                      <div className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 ${
                        msg.type === 'user' 
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
                        className={`rounded-2xl px-4 py-3 text-sm relative ${
                          msg.type === 'user'
                            ? 'bg-gradient-to-r from-violet-600 to-purple-600 text-white shadow-lg shadow-violet-500/30'
                            : msg.isWelcome
                              ? 'bg-gradient-to-r from-green-50 to-emerald-50 text-green-800 border border-green-200 shadow-lg'
                              : msg.isIdle
                                ? 'bg-gradient-to-r from-orange-50 to-amber-50 text-orange-800 border border-orange-200 shadow-lg'
                                : 'bg-white/90 backdrop-blur-sm text-gray-800 border border-gray-200/50 shadow-lg'
                        }`}
                      >
                        {(msg.isWelcome || msg.isIdle) && (
                          <div className={`text-xs font-semibold mb-2 ${
                            msg.isWelcome ? 'text-green-600' : 'text-orange-600'
                          }`}>
                            {msg.isWelcome ? '🎉 Welcome Guide' : '💭 Friendly Check-in'}
                          </div>
                        )}
                        
                        <div className="whitespace-pre-wrap leading-relaxed">{msg.text}</div>
                        <div
                          className={`text-xs mt-2 ${
                            msg.type === 'user' ? 'text-white/70' : 'text-gray-500'
                          }`}
                        >
                          {msg.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
                {isTyping && (
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
                        <span className="text-xs text-gray-500 ml-2">AI is thinking...</span>
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
                    className={`p-3 rounded-xl transition-all duration-200 hover:scale-110 ${
                      isListening 
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