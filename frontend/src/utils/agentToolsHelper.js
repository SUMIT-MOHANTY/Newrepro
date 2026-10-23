/**
 * agentToolsHelper.js
 * -------------------
 * Central utility to identify agent execution lanes and enforce mandatory tools
 * across ResourceOnboarding, AgentToolPicker, and AgentsPage.
 * 
 * Tool requirements are fetched dynamically from the backend tool adequacy engine
 * (TOOL_REQUIREMENTS in tool_adequacy_service.py) via /agents/mandatory-tools.
 * Zero hardcoding.
 */

import { API_ENDPOINTS } from '../config';

// In-memory cache for dynamic mandatory tools loaded from the backend
let _cachedMandatoryTools = null;
let _isFetchingMatrix = false;

/**
 * Fetch the dynamic mandatory tools matrix from the backend tool adequacy service.
 * @param {string} [token] Optional JWT token
 * @returns {Promise<Object>} Map of lane -> mandatory tool array
 */
export async function fetchMandatoryToolsMatrix(token) {
  if (_cachedMandatoryTools) {
    return _cachedMandatoryTools;
  }

  // Attempt to load from sessionStorage first for instant render
  if (typeof sessionStorage !== 'undefined') {
    try {
      const saved = sessionStorage.getItem('agent_mandatory_tools');
      if (saved) {
        _cachedMandatoryTools = JSON.parse(saved);
      }
    } catch (_) {}
  }

  if (_isFetchingMatrix) {
    return _cachedMandatoryTools;
  }

  _isFetchingMatrix = true;
  try {
    const endpoint = API_ENDPOINTS.AGENT_MANDATORY_TOOLS || '/agents/mandatory-tools';
    const headers = { 'Content-Type': 'application/json' };
    const authToken = token || (typeof localStorage !== 'undefined' ? localStorage.getItem('token') : null);
    if (authToken) {
      headers['Authorization'] = `Bearer ${authToken}`;
    }
    const res = await fetch(endpoint, { headers });
    if (res.ok) {
      const data = await res.json();
      if (data && data.mandatory_by_lane) {
        _cachedMandatoryTools = data.mandatory_by_lane;
        if (typeof sessionStorage !== 'undefined') {
          try {
            sessionStorage.setItem('agent_mandatory_tools', JSON.stringify(data.mandatory_by_lane));
          } catch (_) {}
        }
        return _cachedMandatoryTools;
      }
    }
  } catch (err) {
    console.warn('[agentToolsHelper] Failed to fetch dynamic mandatory tools from backend:', err);
  } finally {
    _isFetchingMatrix = false;
  }

  return _cachedMandatoryTools;
}

/**
 * Set or override the dynamic mandatory tools matrix in memory
 */
export function setDynamicMandatoryTools(matrix) {
  if (matrix && typeof matrix === 'object') {
    _cachedMandatoryTools = matrix;
  }
}

/**
 * Detect the agent's primary lane from role, name, lane, tags, specialization, etc.
 * @param {Object|string} agent 
 * @returns {string} One of: 'frontend' | 'backend' | 'qa' | 'devops' | 'integration' | 'governance' | 'general'
 */
export function detectAgentLane(agent) {
  if (!agent) return 'general';

  // If a string was passed directly
  if (typeof agent === 'string') {
    agent = { name: agent };
  }

  // 1. Direct lane property if valid
  if (agent.lane && typeof agent.lane === 'string') {
    const l = agent.lane.toLowerCase().trim();
    if (['frontend', 'backend', 'qa', 'devops', 'governance', 'integration'].includes(l)) {
      return l;
    }
  }

  // 2. Gather text to inspect: role, name, specialization, tags, skills_tags
  const textParts = [];
  if (agent.role) textParts.push(agent.role);
  if (agent.name) textParts.push(agent.name);
  if (agent.specialization) textParts.push(agent.specialization);

  if (Array.isArray(agent.tags)) {
    textParts.push(...agent.tags);
  } else if (typeof agent.tags === 'string') {
    textParts.push(agent.tags);
  }

  if (Array.isArray(agent.skills_tags)) {
    textParts.push(...agent.skills_tags);
  } else if (typeof agent.skills_tags === 'string') {
    textParts.push(agent.skills_tags);
  }

  const combined = textParts.join(' ').toLowerCase();

  // Frontend check (React, Vue, Vite, UI, Web, etc.)
  if (
    combined.includes('front') ||
    combined.includes('react') ||
    combined.includes('vue') ||
    combined.includes('angular') ||
    combined.includes('ui') ||
    combined.includes('ux') ||
    combined.includes('web') ||
    combined.includes('component') ||
    combined.includes('vite') ||
    combined.includes('tailwind') ||
    combined.includes('css')
  ) {
    return 'frontend';
  }

  // QA / Testing check
  if (
    combined.includes('qa') ||
    combined.includes('test') ||
    combined.includes('testing') ||
    combined.includes('quality') ||
    combined.includes('playwright') ||
    combined.includes('cypress') ||
    combined.includes('pytest') ||
    combined.includes('jest') ||
    combined.includes('vitest')
  ) {
    return 'qa';
  }

  // DevOps check
  if (
    combined.includes('devops') ||
    combined.includes('infra') ||
    combined.includes('docker') ||
    combined.includes('deploy') ||
    combined.includes('kubernetes') ||
    combined.includes('ci/cd')
  ) {
    return 'devops';
  }

  // Backend check
  if (
    combined.includes('back') ||
    combined.includes('api') ||
    combined.includes('server') ||
    combined.includes('python') ||
    combined.includes('fastapi') ||
    combined.includes('django') ||
    combined.includes('node') ||
    combined.includes('express') ||
    combined.includes('spring') ||
    combined.includes('java') ||
    combined.includes('dotnet') ||
    combined.includes('c#') ||
    combined.includes('csharp') ||
    combined.includes('golang') ||
    combined.includes('database') ||
    combined.includes('sql')
  ) {
    return 'backend';
  }

  if (combined.includes('integration') || combined.includes('fullstack') || combined.includes('full-stack')) {
    return 'integration';
  }

  if (combined.includes('governance') || combined.includes('compliance')) {
    return 'governance';
  }

  // If specialization is Development, default to developer with filesystem
  const spec = (agent.specialization || '').toLowerCase();
  if (spec.includes('dev')) {
    return 'backend';
  }

  return 'general';
}

/**
 * Returns an array of tool IDs that are mandatory for this agent.
 * Mandatory tools can NEVER be unchecked or removed in the UI.
 * 
 * Precedence:
 * 1. Explicit mandatory_tools / required_tools from backend recommendation or agent record
 * 2. Dynamic lane-specific mandatory tools fetched from /agents/mandatory-tools
 * 3. Graceful offline fallback
 * 
 * @param {Object|string} agent - Agent record or configuration object
 * @returns {string[]} Array of tool IDs, e.g. ['filesystem']
 */
export function getMandatoryToolsForAgent(agent) {
  if (!agent) return ['filesystem'];

  // 1. Direct explicit backend requirements attached to the agent or recommendation
  const explicitMandatory = Array.isArray(agent.mandatory_tools) && agent.mandatory_tools.length > 0
    ? agent.mandatory_tools.map(t => String(t).toLowerCase())
    : (Array.isArray(agent.required_tools) && agent.required_tools.length > 0
        ? agent.required_tools.map(t => String(t).toLowerCase())
        : null);

  if (explicitMandatory && explicitMandatory.length > 0) {
    return explicitMandatory;
  }

  const lane = detectAgentLane(agent);

  // 2. Dynamic requirements from backend cache
  if (_cachedMandatoryTools && _cachedMandatoryTools[lane]) {
    return _cachedMandatoryTools[lane].map(t => String(t).toLowerCase());
  }

  // Check sessionStorage
  if (typeof sessionStorage !== 'undefined') {
    try {
      const saved = sessionStorage.getItem('agent_mandatory_tools');
      if (saved) {
        const parsed = JSON.parse(saved);
        if (parsed && parsed[lane]) {
          _cachedMandatoryTools = parsed;
          return parsed[lane].map(t => String(t).toLowerCase());
        }
      }
    } catch (_) {}
  }

  // 3. Graceful offline fallback matching tool_adequacy_service.py
  const fallback = {
    frontend: ['filesystem'],
    backend: ['filesystem'],
    qa: ['test_runner'],
    devops: ['filesystem', 'terminal'],
    integration: ['filesystem'],
    governance: ['filesystem'],
    general: ['filesystem'],
  };

  return fallback[lane] || ['filesystem'];
}

/**
 * Check if a specific tool is mandatory for an agent
 * @param {string} toolId 
 * @param {Object|string} agent 
 * @returns {boolean}
 */
export function isToolMandatory(toolId, agent) {
  if (!toolId) return false;
  const mandatory = getMandatoryToolsForAgent(agent);
  return mandatory.includes(toolId.toLowerCase());
}

/**
 * Canonical human-friendly labels for tools
 */
export const TOOL_DISPLAY_NAMES = {
  filesystem: 'File System (Read & Write)',
  code_inspector: 'Codebase Inspector (Read-Only)',
  git: 'Git',
  terminal: 'Terminal',
  build_tool: 'Build Tool',
  test_runner: 'Test Runner',
  visual_qa: 'Visual QA',
  database: 'Database',
  database_tools: 'Database & Migration',
  browser: 'Browser',
  docker: 'Docker',
  cloud_cli: 'Cloud CLI',
  web_search: 'Web Search',
};

export function getToolDisplayName(toolId) {
  return TOOL_DISPLAY_NAMES[toolId] || toolId;
}
