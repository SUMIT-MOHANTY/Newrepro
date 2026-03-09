import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  CheckCircle,
  XCircle,
  Clock,
  ExternalLink,
  RefreshCw,
  AlertCircle,
  Settings,
  Zap,
  Database,
  GitBranch,
  Cloud,
  Sparkles,
  ArrowRight,
  Plug,
  ChevronDown,
  ChevronUp,
  Link2,
  Activity,
  Shield,
  Star,
  Ticket,
} from 'lucide-react';
import { API_ENDPOINTS } from '../config';
import nxduneLogo from '../assets/logo1.png';
import kaktoxLogo from '../assets/Kaktox.png';
import cloudspxLogo from '../assets/spx-logo 3.png';

const PLUGINS_META = [
  {
    id: 'nxdune',
    name: 'Nxdune',
    category: 'Management',
    tagline: 'Enterprise Orchestration Platform',
    icon: Database,
    logo: nxduneLogo,
    comingSoon: false,
    description:
      'Enterprise management and orchestration platform for your development workflow. Centralize teams, resources, and SSO in one powerful layer.',
    features: [
      { label: 'Organization management', icon: Shield },
      { label: 'SSO integration', icon: Link2 },
      { label: 'Resource orchestration', icon: Activity },
      { label: 'Team collaboration', icon: Star },
    ],
    palette: {
      grad: 'from-app-primary to-app-primary',
      gradAccent: 'from-blue-400 via-app-primary to-purple-500',
      bg: 'bg-app-primary',
      ring: 'ring-blue-300/40',
      border: 'border-blue-400',
      badge: 'bg-app-primary-light text-app-primary-hover border-app-primary-ring',
      badgeDark: 'bg-app-primary/20 text-app-primary-ring border-blue-400/30',
      glow: 'shadow-app-primary-ring/60',
      text: 'text-app-primary',
      featureBg: 'bg-app-primary-light',
      featureText: 'text-app-primary',
      accent: 'blue',
      dot: 'bg-app-primary',
    },
  },
  {
    id: 'jira',
    name: 'Jira',
    category: 'Management',
    tagline: 'Project Management & Issue Tracking',
    icon: Ticket,
    logo: null, // Will use icon instead
    comingSoon: true,
    description:
      'Seamlessly integrate Jira for project management, issue tracking, and agile workflows. Connect your development pipeline with Jira tickets and sprints.',
    features: [
      { label: 'Issue tracking', icon: Ticket },
      { label: 'Sprint management', icon: Activity },
      { label: 'Project boards', icon: Shield },
      { label: 'Workflow automation', icon: Zap },
    ],
    palette: {
      grad: 'from-app-primary to-app-primary',
      gradAccent: 'from-blue-400 via-app-primary to-purple-500',
      bg: 'bg-app-primary',
      ring: 'ring-blue-300/40',
      border: 'border-blue-400',
      badge: 'bg-app-primary-light text-app-primary-hover border-app-primary-ring',
      badgeDark: 'bg-app-primary/20 text-app-primary-ring border-blue-400/30',
      glow: 'shadow-app-primary-ring/60',
      text: 'text-app-primary',
      featureBg: 'bg-app-primary-light',
      featureText: 'text-app-primary',
      accent: 'blue',
      dot: 'bg-app-primary',
    },
  },
  {
    id: 'kaktox',
    name: 'Kaktox',
    category: 'Testing',
    tagline: 'Automated Quality Assurance',
    icon: GitBranch,
    logo: kaktoxLogo,
    comingSoon: false,
    description:
      'Comprehensive testing and quality assurance platform. Automate test execution, track quality metrics, and ship with confidence.',
    features: [
      { label: 'Automated test execution', icon: Zap },
      { label: 'Quality metrics', icon: Activity },
      { label: 'Test case management', icon: Shield },
      { label: 'Performance testing', icon: Star },
    ],
    palette: {
      grad: 'from-violet-500 to-purple-600',
      gradAccent: 'from-violet-400 via-purple-500 to-pink-500',
      bg: 'bg-violet-500',
      ring: 'ring-violet-300/40',
      border: 'border-violet-400',
      badge: 'bg-violet-50 text-violet-700 border-violet-200',
      badgeDark: 'bg-violet-500/20 text-violet-200 border-violet-400/30',
      glow: 'shadow-violet-200/60',
      text: 'text-violet-600',
      featureBg: 'bg-violet-50',
      featureText: 'text-violet-600',
      accent: 'violet',
      dot: 'bg-violet-500',
    },
  },
  {
    id: 'cloudspx',
    name: 'CloudSpx',
    category: 'Deployment',
    tagline: 'Cloud Infrastructure & CI/CD',
    icon: Cloud,
    logo: cloudspxLogo,
    comingSoon: false,
    description:
      'Cloud deployment and infrastructure management for production environments. Pipelines, autoscaling, and live monitoring in one place.',
    features: [
      { label: 'Cloud infrastructure', icon: Cloud },
      { label: 'CI/CD pipelines', icon: GitBranch },
      { label: 'Auto-scaling', icon: Zap },
      { label: 'Monitoring & alerts', icon: Activity },
    ],
    palette: {
      grad: 'from-app-status-success to-teal-600',
      gradAccent: 'from-emerald-400 via-teal-500 to-cyan-500',
      bg: 'bg-app-status-success',
      ring: 'ring-emerald-300/40',
      border: 'border-emerald-400',
      badge: 'bg-app-status-successBg text-app-status-success border-emerald-200',
      badgeDark: 'bg-app-status-success/20 text-emerald-200 border-emerald-400/30',
      glow: 'shadow-emerald-200/60',
      text: 'text-app-status-success',
      featureBg: 'bg-app-status-successBg',
      featureText: 'text-app-status-success',
      accent: 'emerald',
      dot: 'bg-app-status-success',
    },
  },
];

/* ─── Compact Plugin Selector Card ──────────────────────────── */
function SelectorCard({ plugin, isSelected, liveData, onClick }) {
  const p = plugin.palette;
  const connected = liveData?.connected;
  const clickRef = useRef(false);

  const handleClick = (e) => {
    e.preventDefault();
    e.stopPropagation();
    
    // Prevent double clicks
    if (clickRef.current) return;
    clickRef.current = true;
    
    setTimeout(() => {
      clickRef.current = false;
    }, 300);
    
    if (onClick) {
      onClick();
    }
  };

  return (
    <button
      type="button"
      onClick={handleClick}
      className={`w-full text-left group relative rounded-xl border transition-all duration-200 overflow-hidden focus:outline-none cursor-pointer z-10 ${isSelected
          ? `bg-app-bg-card border-2 ${p.border} ring-2 ${p.ring} shadow-lg ${p.glow}`
          : 'bg-app-bg-card/70 border-app-border hover:border-app-border-active hover:bg-app-bg-card hover:shadow-md'
        }`}
      style={{ position: 'relative', zIndex: 10 }}
    >
      {/* top accent bar */}
      <div
        className={`absolute top-0 left-0 right-0 h-[3px] bg-gradient-to-r ${p.gradAccent} transition-opacity duration-200 pointer-events-none ${isSelected ? 'opacity-100' : 'opacity-0 group-hover:opacity-60'
          }`}
      />

      <div className="flex items-center gap-3 p-3 relative z-10">
        {/* logo bubble */}
        <div
          className={`flex-shrink-0 w-14 h-14 rounded-xl flex items-center justify-center shadow-sm border p-2.5 pointer-events-none ${
            p.accent === 'blue' ? 'bg-gradient-to-br from-app-primary-light to-app-primary-light border-app-primary-ring/50' :
            p.accent === 'violet' ? 'bg-gradient-to-br from-violet-100 to-purple-100 border-violet-200/50' :
            'bg-gradient-to-br from-app-status-successBg to-teal-100 border-emerald-200/50'
          }`}
        >
          {plugin.logo ? (
            <img src={plugin.logo} alt={plugin.name} className="w-full h-full object-contain" />
          ) : (
            <plugin.icon className={`w-7 h-7 ${p.text}`} />
          )}
        </div>

        <div className="flex-1 min-w-0 pointer-events-none">
          <div className="flex items-center gap-2">
            <span className="text-sm font-bold text-app-text-main leading-none">{plugin.name}</span>
            <span
              className={`text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded-md border ${p.badge}`}
            >
              {plugin.category}
            </span>
            {plugin.comingSoon && (
              <span className="text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded-md border bg-app-status-warningBg text-app-status-warning border-amber-200">
                Coming Soon
              </span>
            )}
          </div>
          <p className="text-xs text-app-text-muted truncate mt-0.5">{plugin.tagline}</p>
        </div>

        {/* status dot */}
        {!plugin.comingSoon && (
          <div className="flex-shrink-0 flex flex-col items-end gap-1 pointer-events-none">
            <div className="relative flex h-2.5 w-2.5">
              {connected && (
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
              )}
              <div
                className={`relative inline-flex rounded-full h-2.5 w-2.5 ${connected ? 'bg-app-status-success' : 'bg-app-border'
                  }`}
              />
            </div>
            <span className={`text-[9px] font-semibold ${connected ? 'text-app-status-success' : 'text-app-text-light'}`}>
              {connected ? 'Live' : 'Off'}
            </span>
          </div>
        )}
      </div>
    </button>
  );
}

/* ─── Detail Panel ───────────────────────────────────────────── */
function DetailPanel({ plugin, liveData, onConnect, connecting }) {
  const p = plugin.palette;
  const connected = liveData?.connected;
  const isConnecting = connecting === plugin.id;

  return (
    <div className="flex flex-col bg-app-bg-card rounded-2xl border border-app-border overflow-hidden shadow-xl w-full">
      {/* ── Header gradient ── */}
      <div className={`relative bg-gradient-to-br ${p.grad} p-6 overflow-hidden flex-shrink-0`}>
        {/* dot-grid pattern */}
        <div
          className="absolute inset-0 opacity-10"
          style={{
            backgroundImage: 'radial-gradient(circle at 2px 2px, white 1px, transparent 0)',
            backgroundSize: '20px 20px',
          }}
        />
        {/* glow blob */}
        <div className="absolute -top-8 -right-8 w-40 h-40 bg-app-bg-card/10 rounded-full blur-2xl" />

        <div className="relative flex items-center gap-4">
          <div className={`w-20 h-20 rounded-2xl backdrop-blur-md border flex items-center justify-center p-4 shadow-xl flex-shrink-0 ${
            p.accent === 'blue' ? 'bg-app-primary-light/80 border-app-primary-ring/50' :
            p.accent === 'violet' ? 'bg-violet-100/80 border-violet-200/50' :
            'bg-app-status-successBg/80 border-emerald-200/50'
          }`}>
            {plugin.logo ? (
              <img src={plugin.logo} alt={plugin.name} className="w-full h-full object-contain" />
            ) : (
              <plugin.icon className="w-10 h-10 text-app-bg-card" />
            )}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-[10px] font-bold uppercase tracking-widest px-2.5 py-1 rounded-lg bg-app-bg-card/20 backdrop-blur-sm text-app-bg-card border border-app-bg-card/25">
                {plugin.category}
              </span>
              {plugin.comingSoon && (
                <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-1 rounded-lg bg-amber-400/30 text-app-status-warningBg border border-amber-300/30 flex items-center gap-1">
                  <Clock className="w-2.5 h-2.5" />
                  Coming Soon
                </span>
              )}
              {!plugin.comingSoon && connected && (
                <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-1 rounded-lg bg-emerald-400/30 text-app-status-successBg border border-emerald-300/30 flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-300 animate-pulse" />
                  Active
                </span>
              )}
            </div>
            <h2 className="text-2xl font-extrabold text-app-bg-card tracking-tight">{plugin.name}</h2>
            <p className="text-app-bg-card/80 text-xs mt-0.5 leading-relaxed">{plugin.tagline}</p>
          </div>
        </div>
      </div>

      {/* ── Body ── */}
      <div className="p-5 space-y-5">
        {/* Description */}
        <p className="text-sm text-app-text-label leading-relaxed">{plugin.description}</p>

        {/* Features grid */}
        <div>
          <div className="flex items-center gap-2 mb-3">
            <div className={`w-9 h-9 rounded-lg flex items-center justify-center shadow-sm border ${
              p.accent === 'blue' ? 'bg-app-primary-light border-app-primary-ring/50' :
              p.accent === 'violet' ? 'bg-violet-100 border-violet-200/50' :
              'bg-app-status-successBg border-emerald-200/50'
            }`}>
              <Zap className={`w-5 h-5 ${p.text}`} />
            </div>
            <span className="text-xs font-bold text-app-text-muted uppercase tracking-wider">Key Features</span>
          </div>
          <div className="grid grid-cols-2 gap-2">
            {plugin.features.map(({ label, icon: Icon }, idx) => (
              <div
                key={idx}
                className={`flex items-center gap-2 p-2.5 rounded-xl border border-app-border-light ${p.featureBg} group hover:shadow-sm transition-all duration-150`}
              >
                <div className={`w-6 h-6 rounded-lg flex items-center justify-center flex-shrink-0 bg-app-bg-card shadow-sm`}>
                  <CheckCircle className={`w-3.5 h-3.5 ${p.featureText}`} />
                </div>
                <span className="text-xs font-medium text-app-text-label leading-tight">{label}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Status card */}
        {!plugin.comingSoon && (
          <div>
            <div className="flex items-center gap-2 mb-3">
              <div className={`w-9 h-9 rounded-lg flex items-center justify-center shadow-sm border ${
                p.accent === 'blue' ? 'bg-app-primary-light border-app-primary-ring/50' :
                p.accent === 'violet' ? 'bg-violet-100 border-violet-200/50' :
                'bg-app-status-successBg border-emerald-200/50'
              }`}>
                <Settings className={`w-5 h-5 ${p.text}`} />
              </div>
              <span className="text-xs font-bold text-app-text-muted uppercase tracking-wider">Connection Status</span>
            </div>

            <div
              className={`flex items-center justify-between p-3.5 rounded-xl border-2 ${connected ? 'bg-app-status-successBg/60 border-emerald-200' : 'bg-app-bg-page border-app-border-light'
                }`}
            >
              <div className="flex items-center gap-2.5">
                <div className="relative flex h-3 w-3">
                  {connected && (
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                  )}
                  <div
                    className={`relative inline-flex rounded-full h-3 w-3 ${connected ? 'bg-app-status-success' : 'bg-app-border'
                      }`}
                  />
                </div>
                <span className={`text-sm font-semibold ${connected ? 'text-app-status-success' : 'text-app-text-muted'}`}>
                  {connected ? 'Connected' : 'Not Connected'}
                </span>
              </div>
              <span
                className={`text-xs font-bold px-2.5 py-1 rounded-lg border flex items-center gap-1.5 ${connected
                    ? 'bg-app-status-successBg text-app-status-success border-emerald-200'
                    : 'bg-app-bg-muted text-app-text-muted border-app-border'
                  }`}
              >
                {connected ? (
                  <>
                    <span className="w-1.5 h-1.5 rounded-full bg-app-status-success animate-pulse" />
                    Active
                  </>
                ) : (
                  'Inactive'
                )}
              </span>
            </div>

          {/* connected since */}
          {liveData?.connected_at && (
            <div className="flex items-center gap-2 mt-2 text-xs text-app-text-muted bg-app-bg-page px-3 py-2 rounded-lg border border-app-border-light">
              <Clock className="w-3.5 h-3.5 flex-shrink-0" />
              <span>
                Connected since{' '}
                <span className="font-semibold text-app-text-label">
                  {new Date(liveData.connected_at).toLocaleDateString()}
                </span>
              </span>
            </div>
          )}

          {/* connection message */}
          {liveData?.connection_message && (
            <div
              className={`mt-2 p-3 rounded-xl border ${liveData.connection_error
                  ? 'bg-app-status-errorBg border-red-200'
                  : 'bg-app-status-successBg border-emerald-200'
                }`}
            >
              <div className="flex items-start gap-2">
                {liveData.connection_error ? (
                  <AlertCircle className="w-4 h-4 text-app-status-error flex-shrink-0 mt-0.5" />
                ) : (
                  <CheckCircle className="w-4 h-4 text-app-status-success flex-shrink-0 mt-0.5" />
                )}
                <span
                  className={`text-xs ${liveData.connection_error ? 'text-app-status-error' : 'text-app-status-success'}`}
                >
                  {liveData.connection_message}
                </span>
              </div>
            </div>
          )}
          </div>
        )}
      </div>

      {/* ── CTA Button ── */}
      <div className="p-4 border-t border-app-border-light bg-app-bg-muted/50 flex-shrink-0">
        {plugin.comingSoon ? (
          <div className="w-full flex items-center justify-center gap-2.5 py-3.5 px-5 rounded-xl font-bold text-sm bg-app-bg-muted text-app-text-muted border-2 border-dashed border-app-border cursor-not-allowed">
            <Clock className="w-4 h-4" />
            Coming Soon
          </div>
        ) : (
          <button
            type="button"
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              console.log('Connect button clicked for plugin:', plugin.id);
              if (onConnect) {
                onConnect(plugin.id);
              } else {
                console.error('No onConnect handler provided');
              }
            }}
            disabled={isConnecting}
            className={`w-full flex items-center justify-center gap-2.5 py-3.5 px-5 rounded-xl font-bold text-sm text-app-bg-card transition-all duration-200 shadow-md ${isConnecting
                ? 'bg-app-border text-app-text-muted cursor-not-allowed'
                : `bg-gradient-to-r ${p.grad} hover:shadow-lg ${p.glow} hover:-translate-y-0.5 active:translate-y-0`
              }`}
          >
            {isConnecting ? (
              <>
                <RefreshCw className="w-4 h-4 animate-spin" />
                Connecting…
              </>
            ) : (
              <>
                <ExternalLink className="w-4 h-4" />
                {connected ? 'Reconnect Plugin' : 'Connect Plugin'}
                <ArrowRight className="w-3.5 h-3.5" />
              </>
            )}
          </button>
        )}
      </div>
    </div>
  );
}

/* ─── Empty State ────────────────────────────────────────────── */
function EmptyDetailState() {
  return (
    <div className="flex flex-col h-full items-center justify-center bg-app-bg-card rounded-2xl border-2 border-dashed border-app-border-light min-h-[400px] p-8">
      <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-app-primary-light to-app-primary-light flex items-center justify-center mb-4 border border-app-border-light shadow-sm">
        <Sparkles className="w-8 h-8 text-blue-400" />
      </div>
      <h3 className="text-base font-bold text-app-text-main mb-1.5">Select a Plugin</h3>
      <p className="text-sm text-app-text-muted text-center max-w-[220px] leading-relaxed">
        Choose a plugin from the list to view details and manage the connection.
      </p>
    </div>
  );
}

/* ─── Loading State ──────────────────────────────────────────── */
function LoadingState() {
  return (
    <div className="flex items-center justify-center h-72">
      <div className="flex flex-col items-center gap-3">
        <div className="w-10 h-10 rounded-full border-2 border-app-primary border-t-transparent animate-spin" />
        <span className="text-sm text-app-text-muted font-medium">Loading plugins…</span>
      </div>
    </div>
  );
}

/* ─── Stats Bar ──────────────────────────────────────────────── */
function StatsBar({ pluginsData }) {
  const totalConnected = PLUGINS_META.filter((p) => {
    const live = pluginsData.find(
      (d) => d.client_id?.toLowerCase() === p.id.toLowerCase()
    );
    return live?.connected;
  }).length;

  const stats = [
    { label: 'Total Integrations', value: PLUGINS_META.length, icon: Plug, color: 'text-app-primary', bg: 'bg-app-primary-light' },
    { label: 'Connected', value: totalConnected, icon: CheckCircle, color: 'text-app-status-success', bg: 'bg-app-status-successBg' },
    { label: 'Available', value: PLUGINS_META.length - totalConnected, icon: Zap, color: 'text-violet-600', bg: 'bg-violet-50' },
  ];

  return (
    <div className="grid grid-cols-3 gap-3 mb-6">
      {stats.map(({ label, value, icon: Icon, color, bg }) => (
        <div
          key={label}
          className="flex items-center gap-3 bg-app-bg-card rounded-xl border border-app-border-light px-4 py-3 shadow-sm hover:shadow-md transition-shadow duration-150"
        >
          <div className={`w-10 h-10 ${bg} rounded-lg flex items-center justify-center flex-shrink-0 border ${
            bg === 'bg-app-primary-light' ? 'border-app-primary-ring/50' :
            bg === 'bg-app-status-successBg' ? 'border-emerald-200/50' :
            'border-violet-200/50'
          }`}>
            <Icon className={`w-5 h-5 ${color}`} />
          </div>
          <div>
            <div className="text-xl font-extrabold text-app-text-main leading-none">{value}</div>
            <div className="text-[10px] font-semibold text-app-text-muted uppercase tracking-wider mt-0.5">
              {label}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

/* ─── Main Page ──────────────────────────────────────────────── */
export default function Plugins() {
  const [selected, setSelected] = useState(null);
  const [pluginsData, setPluginsData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [connecting, setConnecting] = useState(null);

  useEffect(() => {
    fetchPlugins();
  }, []);


  const handlePluginSelect = useCallback((plugin) => {
    setSelected(plugin);
  }, []);

  const fetchPlugins = async () => {
    const token = localStorage.getItem('token');
    try {
      const res = await fetch(API_ENDPOINTS.OAUTH_CLIENTS, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error('Failed');
      const data = await res.json();
      setPluginsData(data || []);
    } catch (e) {
      console.error('Plugins fetch error:', e);
    } finally {
      setLoading(false);
    }
  };

  const handleConnect = async (clientId) => {
    console.log('handleConnect called for:', clientId);
    setConnecting(clientId);
    const token = localStorage.getItem('token');
    if (!token) {
      console.error('No token found');
      setConnecting(null);
      return;
    }
    try {
      const url = API_ENDPOINTS.OAUTH_PLUGIN_LAUNCH(clientId);
      console.log('Fetching launch URL from:', url);
      const res = await fetch(url, {
        headers: { Authorization: `Bearer ${token}` },
      });
      console.log('Response status:', res.status);
      
      let data;
      const contentType = res.headers.get('content-type');
      if (contentType && contentType.includes('application/json')) {
        data = await res.json();
      } else {
        const errorText = await res.text();
        console.error('Non-JSON response:', errorText);
        throw new Error(`Server error: ${res.status} - ${errorText.substring(0, 200)}`);
      }
      
      if (!res.ok) {
        console.error('Failed to get launch URL:', res.status, data);
        // Check if there's a launch_url in the error response anyway
        if (data.launch_url) {
          console.log('Found launch_url in error response, redirecting anyway:', data.launch_url);
          window.location.href = data.launch_url;
          return;
        }
        throw new Error(data.detail || data.message || `Failed to get launch URL: ${res.status}`);
      }
      
      console.log('Launch data received:', data);
      if (data.launch_url) {
        console.log('Redirecting to:', data.launch_url);
        window.location.href = data.launch_url;
      } else {
        console.error('No launch_url in response:', data);
        throw new Error('No launch URL received from server');
      }
    } catch (e) {
      console.error('Connect error:', e);
      const errorMessage = e.message || 'Unknown error occurred';
      
      // Show user-friendly error message
      if (errorMessage.includes('Nxdune connect failed') || errorMessage.includes('Page not found at /api/organizations/create/')) {
        alert(`Failed to connect to Nxdune:\n\nThe organization creation endpoint is not available (404 error).\n\nPossible solutions:\n1. Check if Nxdune service is running\n2. Verify the organization creation URL in backend config\n3. Ensure SSO settings are configured in Organization Settings\n4. Contact support if the issue persists\n\nError: ${errorMessage.substring(0, 200)}`);
      } else if (errorMessage.includes('SSO settings')) {
        alert(`Configuration Required:\n\n${errorMessage}\n\nPlease configure your Organization SSO settings first:\n1. Go to SSO Configuration\n2. Set Tenant ID, Client ID, and Client Secret\n3. Try connecting again`);
      } else if (errorMessage.includes('400')) {
        alert(`Connection failed (400):\n\n${errorMessage}\n\nThis might be due to:\n- Missing SSO configuration\n- Invalid plugin settings\n- Backend service unavailable\n\nPlease check your settings and try again.`);
      } else {
        alert(`Failed to connect:\n\n${errorMessage}\n\nPlease check the console for more details.`);
      }
    } finally {
      setConnecting(null);
    }
  };

  const getLiveData = (id) =>
    pluginsData.find((p) => p.client_id?.toLowerCase() === id.toLowerCase()) || {};

  const grouped = {
    Management: PLUGINS_META.filter((p) => p.category === 'Management'),
    Testing: PLUGINS_META.filter((p) => p.category === 'Testing'),
    Deployment: PLUGINS_META.filter((p) => p.category === 'Deployment'),
  };

  const categoryIcons = { Management: Database, Testing: GitBranch, Deployment: Cloud };

  return (
    <div className="h-full overflow-y-auto bg-app-bg-page">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-7">

        {/* ── Page Header ── */}
        <div className="mb-6">
          <div className="flex items-center gap-3 mb-1.5">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-app-primary to-app-primary flex items-center justify-center shadow-md shadow-app-primary-ring">
              <Plug className="w-5 h-5 text-app-bg-card" />
            </div>
            <div>
              <h1 className="text-2xl font-extrabold text-app-text-main tracking-tight leading-none">
                Integrations &amp; Plugins
              </h1>
              <p className="text-xs text-app-text-muted mt-0.5">
                Connect and manage your development tools
              </p>
            </div>
          </div>
        </div>

        {loading ? (
          <LoadingState />
        ) : (
          <>
            {/* Stats bar */}
            <StatsBar pluginsData={pluginsData} />

            {/* Main grid */}
            <div className="grid grid-cols-1 lg:grid-cols-5 gap-5">

              {/* ── Sidebar list ── */}
              <div className="lg:col-span-2 space-y-5">
                {Object.entries(grouped).map(([cat, list]) => {
                  const CatIcon = categoryIcons[cat];
                  return (
                    <div key={cat}>
                      <div className="flex items-center gap-2 mb-2.5 px-1">
                        <CatIcon className="w-3.5 h-3.5 text-app-text-muted" />
                        <span className="text-[10px] font-bold text-app-text-muted uppercase tracking-widest">
                          {cat}
                        </span>
                        <div className="flex-1 h-px bg-app-border-light" />
                      </div>
                      <div className="space-y-2">
                        {list.map((plugin) => (
                          <SelectorCard
                            key={plugin.id}
                            plugin={plugin}
                            isSelected={selected?.id === plugin.id}
                            liveData={getLiveData(plugin.id)}
                            onClick={() => handlePluginSelect(plugin)}
                          />
                        ))}
                      </div>
                    </div>
                  );
                })}

                {/* Integration hint */}
                <div className="rounded-xl border border-app-border-light bg-gradient-to-br from-app-primary-light to-app-primary-light p-4">
                  <div className="flex items-start gap-3">
                    <div className="w-8 h-8 rounded-lg bg-app-primary-light flex items-center justify-center flex-shrink-0 mt-0.5">
                      <Sparkles className="w-4 h-4 text-app-primary" />
                    </div>
                    <div>
                      <p className="text-xs font-bold text-app-primary-dark mb-0.5">DSuite Ecosystem</p>
                      <p className="text-[11px] text-app-primary-hover/80 leading-relaxed">
                        All three plugins work together to form the complete DSuite pipeline — manage, test, and deploy from a single platform.
                      </p>
                    </div>
                  </div>
                </div>
              </div>

              {/* ── Detail panel ── */}
              <div className="lg:col-span-3 flex flex-col">
                {selected ? (
                  <DetailPanel
                    key={selected.id}
                    plugin={selected}
                    liveData={getLiveData(selected.id)}
                    onConnect={handleConnect}
                    connecting={connecting}
                  />
                ) : (
                  <EmptyDetailState />
                )}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}