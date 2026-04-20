const SYSTEM_AGENT_NAMES = {
  G_agent_01: 'Git Manager',
  M_agent_01: 'Master Agent',
  M_agent_02: 'Deploy Agent',
};

const GENERATED_NAME_PATTERNS = [
  /^(shared|dedicated|dev)[ _-]*agent(?:[ _-]*\d+)?$/i,
  /^agent(?:[ _-]*\d+)?$/i,
  /^(requirements validator|risk assessment|resource estimation)$/i,
];

export function getAgentSequence(agentOrId) {
  const agentId = typeof agentOrId === 'string' ? agentOrId : agentOrId?.id;
  const match = String(agentId || '').match(/(\d+)$/);
  if (!match) return null;
  return Number.parseInt(match[1], 10);
}

export function getNeutralAgentName(agentOrId, fallbackName) {
  const agentId = typeof agentOrId === 'string' ? agentOrId : agentOrId?.id;
  if (SYSTEM_AGENT_NAMES[agentId]) {
    return SYSTEM_AGENT_NAMES[agentId];
  }

  const sequence = getAgentSequence(agentId);
  const defaultName = sequence ? `Agent ${sequence}` : 'Agent';
  const rawName = typeof agentOrId === 'object' && agentOrId ? agentOrId.name : fallbackName;
  const cleanedName = String(rawName || '').trim();
  if (!cleanedName) {
    return defaultName;
  }

  const normalizedName = cleanedName.toLowerCase();
  const normalizedId = String(agentId || '').trim().toLowerCase();
  if (normalizedName === normalizedId || normalizedName === normalizedId.replace(/_/g, ' ')) {
    return defaultName;
  }
  if (GENERATED_NAME_PATTERNS.some((pattern) => pattern.test(cleanedName))) {
    return defaultName;
  }

  return cleanedName;
}

export function getNeutralAgentLabel(agentOrId) {
  const agentId = typeof agentOrId === 'string' ? agentOrId : agentOrId?.id;
  if (SYSTEM_AGENT_NAMES[agentId]) {
    return 'SYSTEM AGENT';
  }
  const sequence = getAgentSequence(agentId);
  return sequence ? `AGENT ${sequence}` : 'AGENT';
}
