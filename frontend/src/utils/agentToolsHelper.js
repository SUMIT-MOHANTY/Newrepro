/**
 * agentToolsHelper.js
 * -------------------
 * Central utility to identify agent execution lanes and enforce mandatory tools
 * across ResourceOnboarding, AgentToolPicker, and AgentsPage.
 */

// Canonical lane-to-mandatory tools definitions
export const LANE_MANDATORY_TOOLS = {
  frontend: ['filesystem'], // Read and write tool (File System & Code Editor)
  backend: ['filesystem'],
  qa: ['test_runner'],
  devops: ['filesystem', 'terminal'],
  integration: ['filesystem'],
  governance: ['filesystem'],
  general: ['filesystem']
};

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
 * @param {Object|string} agent - Agent record or configuration object
 * @returns {string[]} Array of tool IDs, e.g. ['filesystem']
 */
export function getMandatoryToolsForAgent(agent) {
  if (!agent) return ['filesystem'];

  // If explicit required_tools are attached from backend adequacy check, include them
  const explicitRequired = Array.isArray(agent.required_tools)
    ? agent.required_tools.map(t => String(t).toLowerCase())
    : [];

  const lane = detectAgentLane(agent);
  const laneTools = LANE_MANDATORY_TOOLS[lane] || ['filesystem'];

  const combined = new Set([...laneTools, ...explicitRequired]);
  return Array.from(combined);
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
