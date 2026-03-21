import React, { useState, useEffect } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from './ui/card';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { Checkbox } from './ui/checkbox';
import { Brain, Settings, Zap, User, CheckCircle, AlertCircle } from 'lucide-react';

const AgentCapabilityManager = ({ projectToken }) => {
  const [agents, setAgents] = useState({});
  const [loading, setLoading] = useState(true);
  const [selectedAgent, setSelectedAgent] = useState(null);
  const [availableSkills] = useState(['frontend', 'backend', 'setup', 'integration']);
  const [bulkAction, setBulkAction] = useState('');

  useEffect(() => {
    fetchAgentCapabilities();
  }, [projectToken]);

  const fetchAgentCapabilities = async () => {
    try {
      const response = await fetch(`/api/coordination/agents/bulk-configure?project_token=${projectToken || ''}`);
      if (response.ok) {
        const data = await response.json();
        setAgents(data.agents);
      }
    } catch (error) {
      console.error('Failed to fetch agent capabilities:', error);
    } finally {
      setLoading(false);
    }
  };

  const configureAgent = async (agentId, primarySkills, secondarySkills) => {
    try {
      const response = await fetch(`/api/coordination/agent/${agentId}/configure?project_token=${projectToken || ''}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          primary_skills: primarySkills,
          secondary_skills: secondarySkills
        })
      });
      
      if (response.ok) {
        await fetchAgentCapabilities();
        return true;
      }
    } catch (error) {
      console.error('Failed to configure agent:', error);
    }
    return false;
  };

  const aiAssignAgent = async (agentId) => {
    try {
      const response = await fetch(`/api/coordination/agent/${agentId}/ai-assign?project_token=${projectToken || ''}`, {
        method: 'POST'
      });
      
      if (response.ok) {
        await fetchAgentCapabilities();
        return true;
      }
    } catch (error) {
      console.error('Failed to AI assign agent:', error);
    }
    return false;
  };

  const getAssignmentMethodIcon = (method) => {
    switch (method) {
      case 'explicit_config': return <Settings className="h-4 w-4" />;
      case 'master_agent': return <Brain className="h-4 w-4" />;
      case 'pattern_recognition': return <Zap className="h-4 w-4" />;
      default: return <User className="h-4 w-4" />;
    }
  };

  const getAssignmentMethodColor = (method) => {
    switch (method) {
      case 'explicit_config': return 'bg-blue-500';
      case 'master_agent': return 'bg-purple-500';
      case 'pattern_recognition': return 'bg-green-500';
      default: return 'bg-gray-500';
    }
  };

  const getAssignmentMethodLabel = (method) => {
    switch (method) {
      case 'explicit_config': return 'Manual Config';
      case 'master_agent': return 'AI Assigned';
      case 'pattern_recognition': return 'Auto Pattern';
      default: return 'Default';
    }
  };

  if (loading) {
    return (
      <Card>
        <CardContent className="p-6">
          <div className="flex items-center justify-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
            <span className="ml-2">Loading agent capabilities...</span>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            <div className="flex items-center">
              <Settings className="h-6 w-6 mr-2 text-blue-600" />
              Agent Capability Management
            </div>
            <div className="text-sm text-gray-600">
              {Object.keys(agents).length} agents
            </div>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-4">
            <div className="text-center">
              <div className="text-2xl font-bold text-blue-600">
                {Object.values(agents).filter(a => a.current_capabilities.assigned_by === 'explicit_config').length}
              </div>
              <div className="text-sm text-gray-600">Manual Config</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-purple-600">
                {Object.values(agents).filter(a => a.current_capabilities.assigned_by === 'master_agent').length}
              </div>
              <div className="text-sm text-gray-600">AI Assigned</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-green-600">
                {Object.values(agents).filter(a => a.current_capabilities.assigned_by === 'pattern_recognition').length}
              </div>
              <div className="text-sm text-gray-600">Auto Pattern</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-gray-600">
                {Object.values(agents).filter(a => a.current_capabilities.assigned_by === 'default_fallback').length}
              </div>
              <div className="text-sm text-gray-600">Default</div>
            </div>
          </div>

          {/* Bulk Actions */}
          <div className="flex items-center gap-4 p-4 bg-gray-50 rounded-lg">
            <span className="font-medium">Bulk Actions:</span>
            <Button 
              onClick={() => {
                Object.keys(agents).forEach(agentId => aiAssignAgent(agentId));
              }}
              className="flex items-center"
            >
              <Brain className="h-4 w-4 mr-2" />
              AI Assign All
            </Button>
            <Button 
              variant="outline"
              onClick={fetchAgentCapabilities}
            >
              Refresh
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Agent Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {Object.entries(agents).map(([agentId, agentData]) => (
          <Card key={agentId} className="relative">
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-lg">{agentId}</CardTitle>
                <Badge className={`${getAssignmentMethodColor(agentData.current_capabilities.assigned_by)} text-white`}>
                  <div className="flex items-center">
                    {getAssignmentMethodIcon(agentData.current_capabilities.assigned_by)}
                    <span className="ml-1 text-xs">
                      {getAssignmentMethodLabel(agentData.current_capabilities.assigned_by)}
                    </span>
                  </div>
                </Badge>
              </div>
            </CardHeader>
            <CardContent>
              {/* Current Capabilities */}
              <div className="mb-4">
                <div className="text-sm font-medium mb-2">Primary Skills:</div>
                <div className="flex flex-wrap gap-1 mb-2">
                  {agentData.current_capabilities.primary?.map(skill => (
                    <Badge key={skill} variant="default" className="text-xs">
                      {skill}
                    </Badge>
                  ))}
                </div>
                
                {agentData.current_capabilities.secondary?.length > 0 && (
                  <>
                    <div className="text-sm font-medium mb-2">Secondary Skills:</div>
                    <div className="flex flex-wrap gap-1 mb-2">
                      {agentData.current_capabilities.secondary.map(skill => (
                        <Badge key={skill} variant="outline" className="text-xs">
                          {skill}
                        </Badge>
                      ))}
                    </div>
                  </>
                )}
              </div>

              {/* Pattern Suggestion */}
              {agentData.current_capabilities.assigned_by !== 'pattern_recognition' && 
               JSON.stringify(agentData.current_capabilities.primary) !== JSON.stringify(agentData.suggested_by_pattern.primary) && (
                <div className="mb-4 p-2 bg-yellow-50 rounded border-l-4 border-yellow-400">
                  <div className="text-xs text-yellow-800 mb-1">Pattern Suggestion:</div>
                  <div className="flex flex-wrap gap-1">
                    {agentData.suggested_by_pattern.primary?.map(skill => (
                      <Badge key={skill} variant="outline" className="text-xs border-yellow-400">
                        {skill}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}

              {/* Actions */}
              <div className="flex gap-2">
                <Button
                  size="sm"
                  onClick={() => aiAssignAgent(agentId)}
                  className="flex items-center flex-1"
                >
                  <Brain className="h-3 w-3 mr-1" />
                  AI Assign
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setSelectedAgent(agentId)}
                  className="flex items-center flex-1"
                >
                  <Settings className="h-3 w-3 mr-1" />
                  Configure
                </Button>
              </div>

              {/* AI Decision Info */}
              {agentData.current_capabilities.assigned_by === 'master_agent' && agentData.current_capabilities.reasoning && (
                <div className="mt-2 p-2 bg-purple-50 rounded text-xs">
                  <div className="font-medium text-purple-800">AI Reasoning:</div>
                  <div className="text-purple-700">{agentData.current_capabilities.reasoning}</div>
                  {agentData.current_capabilities.confidence && (
                    <div className="text-purple-600 mt-1">
                      Confidence: {agentData.current_capabilities.confidence}%
                    </div>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Manual Configuration Modal */}
      {selectedAgent && (
        <ManualConfigModal
          agentId={selectedAgent}
          currentCapabilities={agents[selectedAgent]?.current_capabilities}
          availableSkills={availableSkills}
          onSave={configureAgent}
          onClose={() => setSelectedAgent(null)}
        />
      )}
    </div>
  );
};

const ManualConfigModal = ({ agentId, currentCapabilities, availableSkills, onSave, onClose }) => {
  const [primarySkills, setPrimarySkills] = useState(currentCapabilities?.primary || []);
  const [secondarySkills, setSecondarySkills] = useState(currentCapabilities?.secondary || []);
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    const success = await onSave(agentId, primarySkills, secondarySkills);
    setSaving(false);
    if (success) {
      onClose();
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>Configure {agentId}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <label className="text-sm font-medium mb-2 block">Primary Skills:</label>
            <div className="space-y-2">
              {availableSkills.map(skill => (
                <div key={skill} className="flex items-center space-x-2">
                  <Checkbox
                    checked={primarySkills.includes(skill)}
                    onCheckedChange={(checked) => {
                      if (checked) {
                        setPrimarySkills([...primarySkills, skill]);
                      } else {
                        setPrimarySkills(primarySkills.filter(s => s !== skill));
                      }
                    }}
                  />
                  <label className="text-sm capitalize">{skill}</label>
                </div>
              ))}
            </div>
          </div>

          <div>
            <label className="text-sm font-medium mb-2 block">Secondary Skills:</label>
            <div className="space-y-2">
              {availableSkills.map(skill => (
                <div key={skill} className="flex items-center space-x-2">
                  <Checkbox
                    checked={secondarySkills.includes(skill)}
                    onCheckedChange={(checked) => {
                      if (checked) {
                        setSecondarySkills([...secondarySkills, skill]);
                      } else {
                        setSecondarySkills(secondarySkills.filter(s => s !== skill));
                      }
                    }}
                  />
                  <label className="text-sm capitalize">{skill}</label>
                </div>
              ))}
            </div>
          </div>

          <div className="flex gap-2 pt-4">
            <Button onClick={handleSave} disabled={saving} className="flex-1">
              {saving ? 'Saving...' : 'Save Configuration'}
            </Button>
            <Button variant="outline" onClick={onClose} className="flex-1">
              Cancel
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default AgentCapabilityManager;