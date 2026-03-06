import React, { useState, useEffect } from 'react';
import { Users, Trash2, Activity, Clock, CheckCircle, AlertCircle, RefreshCw, Filter } from 'lucide-react';
import { API_ENDPOINTS } from '../config';

/**
 * AgentsPage – Full‑screen view of all agents for the current organization / project.
 * It lists shared and dedicated agents separately and allows deletion of dedicated agents only.
 */
export default function AgentsPage({ selectedProjectKey }) {
  const [sharedAgents, setSharedAgents] = useState([]);
  const [dedicatedAgents, setDedicatedAgents] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [deletingId, setDeletingId] = useState(null);
  const [filter, setFilter] = useState('all'); // 'all', 'shared', 'dedicated'

  const fetchAgents = async () => {
    setLoading(true);
    setError(null);
    
    const token = localStorage.getItem('token');
    
    try {
      // Fetch shared agents (no project_token)
      const sharedUrl = new URL(API_ENDPOINTS.AGENTS);
      const sharedRes = await fetch(sharedUrl.toString(), {
        headers: { Authorization: `Bearer ${token}` },
      });

      // Fetch dedicated agents (with project_token)
      const dedicatedUrl = new URL(API_ENDPOINTS.AGENTS);
      if (selectedProjectKey) {
        dedicatedUrl.searchParams.set('project_token', selectedProjectKey);
      }
      const dedicatedRes = selectedProjectKey 
        ? await fetch(dedicatedUrl.toString(), {
            headers: { Authorization: `Bearer ${token}` },
          })
        : { ok: true, json: async () => ({ agents: [] }) };

      if (!sharedRes.ok) {
        throw new Error(`Failed to fetch shared agents: ${sharedRes.status}`);
      }
      if (!dedicatedRes.ok) {
        throw new Error(`Failed to fetch dedicated agents: ${dedicatedRes.status}`);
      }

      const sharedData = await sharedRes.json();
      const dedicatedData = await dedicatedRes.json();

      const sharedList = Array.isArray(sharedData) 
        ? sharedData 
        : (sharedData?.agents || sharedData?.results || sharedData?.data || []);
      
      const dedicatedList = Array.isArray(dedicatedData)
        ? dedicatedData
        : (dedicatedData?.agents || dedicatedData?.results || dedicatedData?.data || []);

      // Mark agents with their type
      const sharedWithType = sharedList.map(agent => ({ ...agent, agentType: 'shared' }));
      const dedicatedWithType = dedicatedList.map(agent => ({ ...agent, agentType: 'dedicated' }));

      setSharedAgents(sharedWithType);
      setDedicatedAgents(dedicatedWithType);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAgents();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedProjectKey]);

  const handleDeleteAgent = async (agentId) => {
    setDeletingId(agentId);
    const token = localStorage.getItem('token');
    try {
      const res = await fetch(API_ENDPOINTS.AGENT_REMOVE(agentId), {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error('Failed to delete agent');
      
      // Remove from dedicated agents list and refetch
      setDedicatedAgents((prev) => prev.filter((a) => a.id !== agentId));
      // Refetch to ensure consistency
      await fetchAgents();
    } catch (e) {
      setError(e.message);
    } finally {
      setDeletingId(null);
    }
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case 'running':
        return <Activity className="w-4 h-4 text-green-500 animate-pulse" />;
      case 'idle':
        return <CheckCircle className="w-4 h-4 text-blue-500" />;
      case 'error':
      case 'failed':
        return <AlertCircle className="w-4 h-4 text-red-500" />;
      default:
        return <Clock className="w-4 h-4 text-gray-400" />;
    }
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'running':
        return 'bg-green-500/10 border-green-500/30 text-green-400';
      case 'idle':
        return 'bg-blue-500/10 border-blue-500/30 text-blue-400';
      case 'error':
      case 'failed':
        return 'bg-red-500/10 border-red-500/30 text-red-400';
      default:
        return 'bg-gray-500/10 border-gray-500/30 text-gray-400';
    }
  };

  const getTypeColor = (type) => {
    const colors = {
      validator: 'bg-purple-500/20 text-purple-400',
      risk: 'bg-amber-500/20 text-amber-400',
      estimator: 'bg-cyan-500/20 text-cyan-400',
    };
    return colors[type] || 'bg-gray-500/20 text-gray-400';
  };

  // Filter agents based on selected filter
  const getFilteredAgents = () => {
    const allAgents = [...sharedAgents, ...dedicatedAgents];
    switch (filter) {
      case 'shared':
        return sharedAgents;
      case 'dedicated':
        return dedicatedAgents;
      default:
        return allAgents;
    }
  };

  const filteredAgents = getFilteredAgents();
  const totalAgents = sharedAgents.length + dedicatedAgents.length;

  return (
    <div className="h-full w-full flex flex-col bg-app-bg-page text-app-text-main">
      {/* Header */}
      <div className="flex-shrink-0 flex items-center justify-between px-6 py-4 border-b border-app-border-light bg-app-bg-card/50">
        <h1 className="text-2xl font-bold flex items-center">
          <Users className="w-6 h-6 mr-2" /> Agents
        </h1>
        <div className="flex items-center space-x-3">
          <span className="text-sm text-app-text-muted">
            {totalAgents} agent{totalAgents !== 1 ? 's' : ''} ({sharedAgents.length} shared, {dedicatedAgents.length} dedicated)
          </span>
          <button
            onClick={fetchAgents}
            disabled={loading}
            className="flex items-center px-4 py-2 text-sm font-medium text-app-text-main bg-app-text-label/20 rounded-lg hover:bg-app-text-label/30 transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Filter Buttons */}
      <div className="flex-shrink-0 px-6 py-3 border-b border-app-border-light bg-app-bg-card/30">
        <div className="flex items-center space-x-2">
          <Filter className="w-4 h-4 text-app-text-muted" />
          <span className="text-sm font-medium text-app-text-muted mr-2">Filter:</span>
          <button
            onClick={() => setFilter('all')}
            className={`px-3 py-1 text-sm font-medium rounded-lg transition-colors ${
              filter === 'all'
                ? 'bg-blue-500 text-white'
                : 'bg-app-text-label/20 text-app-text-main hover:bg-app-text-label/30'
            }`}
          >
            All ({totalAgents})
          </button>
          <button
            onClick={() => setFilter('shared')}
            className={`px-3 py-1 text-sm font-medium rounded-lg transition-colors ${
              filter === 'shared'
                ? 'bg-blue-500 text-white'
                : 'bg-app-text-label/20 text-app-text-main hover:bg-app-text-label/30'
            }`}
          >
            Shared ({sharedAgents.length})
          </button>
          <button
            onClick={() => setFilter('dedicated')}
            className={`px-3 py-1 text-sm font-medium rounded-lg transition-colors ${
              filter === 'dedicated'
                ? 'bg-blue-500 text-white'
                : 'bg-app-text-label/20 text-app-text-main hover:bg-app-text-label/30'
            }`}
          >
            Dedicated ({dedicatedAgents.length})
          </button>
        </div>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 flex min-h-0">
        {/* Agents List - Scrollable */}
        <div className="flex-1 overflow-y-auto overflow-x-hidden p-6">
          {/* Loading State */}
          {loading && filteredAgents.length === 0 && (
            <div className="flex items-center justify-center h-full">
              <div className="flex flex-col items-center">
                <RefreshCw className="w-8 h-8 text-app-primary animate-spin mb-4" />
                <p className="text-app-text-muted">Loading agents...</p>
              </div>
            </div>
          )}

          {/* Error State */}
          {error && (
            <div className="mb-6 p-4 bg-red-500/10 border border-red-500/30 rounded-lg">
              <p className="text-red-400 flex items-center">
                <AlertCircle className="w-5 h-5 mr-2" />
                {error}
              </p>
            </div>
          )}

          {/* Agents List */}
          {!loading && !error && (
            <div className="space-y-4">
              {filteredAgents.length > 0 ? (
                filteredAgents.map((agent, index) => (
                  <div
                    key={agent.id}
                    className={`p-4 rounded-xl border transition-all duration-300 hover:shadow-lg hover:shadow-app-text-label/5 ${getStatusColor(
                      agent.status
                    )}`}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center space-x-4">
                        {/* Status Icon */}
                        <div className="p-2 rounded-lg bg-app-bg-card/50">
                          {getStatusIcon(agent.status)}
                        </div>

                        {/* Agent Info */}
                        <div>
                          <div className="flex items-center space-x-2">
                            <h3 className="font-semibold text-lg">{agent.name}</h3>
                            <span
                              className={`px-2 py-0.5 text-xs font-medium rounded-full ${
                                agent.agentType === 'shared'
                                  ? 'bg-green-500/20 text-green-400'
                                  : 'bg-orange-500/20 text-orange-400'
                              }`}
                            >
                              {agent.agentType === 'shared' ? 'Shared' : 'Dedicated'}
                            </span>
                          </div>
                          <div className="flex items-center space-x-3 mt-1">
                            <span
                              className={`px-2 py-0.5 text-xs font-medium rounded-full ${getTypeColor(
                                agent.type
                              )}`}
                            >
                              {agent.type}
                            </span>
                            <span className="flex items-center text-xs text-app-text-muted">
                              {getStatusIcon(agent.status)}
                              <span className="ml-1 capitalize">{agent.status}</span>
                            </span>
                          </div>
                        </div>
                      </div>

                      {/* Actions */}
                      <div className="flex items-center space-x-2">
                        {/* Progress indicator if running */}
                        {agent.status === 'running' && agent.progress > 0 && (
                          <div className="w-24 h-2 bg-app-bg-card rounded-full overflow-hidden">
                            <div
                              className="h-full bg-green-500 transition-all duration-300"
                              style={{ width: `${agent.progress}%` }}
                            />
                          </div>
                        )}

                        {/* Delete Button - Only for dedicated agents */}
                        {agent.agentType === 'dedicated' && (
                          <button
                            onClick={() => handleDeleteAgent(agent.id)}
                            disabled={deletingId === agent.id}
                            className="p-2 rounded-lg bg-app-bg-card/50 text-red-400 hover:text-red-300 hover:bg-red-500/10 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                            title="Delete dedicated agent"
                          >
                            {deletingId === agent.id ? (
                              <RefreshCw className="w-4 h-4 animate-spin" />
                            ) : (
                              <Trash2 className="w-4 h-4" />
                            )}
                          </button>
                        )}
                        {agent.agentType === 'shared' && (
                          <span className="text-xs text-app-text-muted px-2 py-1">
                            Cannot delete shared agents
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Additional Details */}
                    {agent.progress_message && (
                      <div className="mt-3 pt-3 border-t border-app-border-light/30">
                        <p className="text-sm text-app-text-muted flex items-center">
                          <Activity className="w-3 h-3 mr-2" />
                          {agent.progress_message}
                        </p>
                      </div>
                    )}

                    {/* Last Run Info */}
                    {agent.last_run && (
                      <div className="mt-2 text-xs text-app-text-muted flex items-center">
                        <Clock className="w-3 h-3 mr-1" />
                        Last run: {new Date(agent.last_run).toLocaleString()}
                      </div>
                    )}
                  </div>
                ))
              ) : (
                <div className="flex flex-col items-center justify-center h-full text-app-text-muted">
                  <Users className="w-16 h-16 mb-4 opacity-30" />
                  <p className="text-lg">No agents available</p>
                  <p className="text-sm mt-1">
                    {filter === 'shared' && 'No shared agents found'}
                    {filter === 'dedicated' && 'No dedicated agents found'}
                    {filter === 'all' && 'Agents will appear here once configured'}
                  </p>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Summary Stats Sidebar */}
        {filteredAgents.length > 0 && (
          <div className="w-64 flex-shrink-0 border-l border-app-border-light p-4 overflow-y-auto bg-app-bg-card/30">
            <h3 className="font-semibold mb-4 text-sm text-app-text-muted uppercase tracking-wider">
              Summary
            </h3>
            <div className="space-y-3">
              <div className="p-3 bg-app-text-label/10 rounded-lg border border-app-border-light/30">
                <p className="text-2xl font-bold">{filteredAgents.length}</p>
                <p className="text-xs text-app-text-muted">Showing</p>
              </div>
              <div className="p-3 bg-green-500/10 rounded-lg border border-green-500/30">
                <p className="text-2xl font-bold text-green-400">
                  {filteredAgents.filter((a) => a.status === 'running').length}
                </p>
                <p className="text-xs text-green-400/70">Running</p>
              </div>
              <div className="p-3 bg-blue-500/10 rounded-lg border border-blue-500/30">
                <p className="text-2xl font-bold text-blue-400">
                  {filteredAgents.filter((a) => a.status === 'idle').length}
                </p>
                <p className="text-xs text-blue-400/70">Idle</p>
              </div>
              <div className="p-3 bg-red-500/10 rounded-lg border border-red-500/30">
                <p className="text-2xl font-bold text-red-400">
                  {filteredAgents.filter((a) => a.status === 'error' || a.status === 'failed').length}
                </p>
                <p className="text-xs text-red-400/70">Error</p>
              </div>
              <div className="p-3 bg-purple-500/10 rounded-lg border border-purple-500/30">
                <p className="text-2xl font-bold text-purple-400">
                  {filteredAgents.filter((a) => a.agentType === 'shared').length}
                </p>
                <p className="text-xs text-purple-400/70">Shared</p>
              </div>
              <div className="p-3 bg-orange-500/10 rounded-lg border border-orange-500/30">
                <p className="text-2xl font-bold text-orange-400">
                  {filteredAgents.filter((a) => a.agentType === 'dedicated').length}
                </p>
                <p className="text-xs text-orange-400/70">Dedicated</p>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}