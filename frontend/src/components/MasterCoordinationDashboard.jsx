import React, { useState, useEffect } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from './ui/card';
import { Badge } from './ui/badge';
import { Progress } from './ui/progress';
import { Clock, Users, FileText, Lock, CheckCircle, AlertCircle } from 'lucide-react';

const MasterCoordinationDashboard = ({ projectToken }) => {
  const [coordinationStatus, setCoordinationStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchCoordinationStatus = async () => {
      try {
        const response = await fetch(`/api/coordination/status?project_token=${projectToken || ''}`);
        if (response.ok) {
          const data = await response.json();
          setCoordinationStatus(data);
        } else {
          setError('Failed to fetch coordination status');
        }
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    fetchCoordinationStatus();
    const interval = setInterval(fetchCoordinationStatus, 5000); // Update every 5 seconds

    return () => clearInterval(interval);
  }, [projectToken]);

  if (loading) {
    return (
      <Card>
        <CardContent className="p-6">
          <div className="flex items-center justify-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
            <span className="ml-2">Loading coordination status...</span>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <CardContent className="p-6">
          <div className="flex items-center text-red-600">
            <AlertCircle className="h-5 w-5 mr-2" />
            <span>Error: {error}</span>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (!coordinationStatus) {
    return (
      <Card>
        <CardContent className="p-6">
          <div className="text-center text-gray-500">
            <Users className="h-12 w-12 mx-auto mb-2 opacity-50" />
            <p>No coordination data available</p>
            <p className="text-sm">Start agents to see coordination status</p>
          </div>
        </CardContent>
      </Card>
    );
  }

  const getStatusColor = (status) => {
    switch (status) {
      case 'idle': return 'bg-gray-500';
      case 'assigned': return 'bg-blue-500';
      case 'working': return 'bg-green-500';
      case 'sync_waiting': return 'bg-yellow-500';
      case 'failed': return 'bg-red-500';
      default: return 'bg-gray-400';
    }
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case 'idle': return <Clock className="h-4 w-4" />;
      case 'assigned': return <FileText className="h-4 w-4" />;
      case 'working': return <Users className="h-4 w-4" />;
      case 'sync_waiting': return <AlertCircle className="h-4 w-4" />;
      case 'failed': return <AlertCircle className="h-4 w-4" />;
      default: return <Clock className="h-4 w-4" />;
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center">
            <Users className="h-6 w-6 mr-2 text-blue-600" />
            🎯 Master Task Manager - Coordinated Execution
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className="text-center">
              <div className="text-2xl font-bold text-blue-600">
                {coordinationStatus.total_tasks}
              </div>
              <div className="text-sm text-gray-600">Total Tasks</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-green-600">
                {coordinationStatus.completed_tasks}
              </div>
              <div className="text-sm text-gray-600">Completed</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-yellow-600">
                {coordinationStatus.in_progress_tasks}
              </div>
              <div className="text-sm text-gray-600">In Progress</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-gray-600">
                {coordinationStatus.pending_tasks}
              </div>
              <div className="text-sm text-gray-600">Pending</div>
            </div>
          </div>
          
          <div className="mt-4">
            <div className="flex justify-between text-sm mb-2">
              <span>Project Progress</span>
              <span>{Math.round(coordinationStatus.completion_percentage)}%</span>
            </div>
            <Progress value={coordinationStatus.completion_percentage} className="h-3" />
          </div>
        </CardContent>
      </Card>

      {/* Agent Status - Optimized for Large Pools */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            <span>Agent Status - Master Controlled</span>
            <div className="text-sm text-gray-600">
              {Object.keys(coordinationStatus.agents).length} agents total
            </div>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {/* Agent Summary Stats */}
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
            {['idle', 'assigned', 'working', 'sync_waiting', 'failed'].map(status => {
              const count = Object.values(coordinationStatus.agents).filter(agent => agent.status === status).length;
              return (
                <div key={status} className="text-center">
                  <div className={`text-2xl font-bold ${getStatusColor(status).replace('bg-', 'text-')}`}>
                    {count}
                  </div>
                  <div className="text-sm text-gray-600 capitalize">{status.replace('_', ' ')}</div>
                </div>
              );
            })}
          </div>

          {/* Agent Grid - Responsive for large numbers */}
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 xl:grid-cols-8 gap-2">
            {Object.entries(coordinationStatus.agents)
              .sort(([a], [b]) => a.localeCompare(b)) // Sort by agent ID
              .map(([agentId, agentData]) => (
              <div key={agentId} className="border rounded p-2 text-sm">
                <div className="flex items-center justify-between mb-1">
                  <span className="font-medium text-xs truncate">{agentId}</span>
                  <div className={`w-3 h-3 rounded-full ${getStatusColor(agentData.status)}`}></div>
                </div>
                {agentData.current_task && (
                  <div className="text-xs text-gray-600 truncate" title={agentData.current_task}>
                    {agentData.current_task}
                  </div>
                )}
                {!agentData.current_task && agentData.status === 'idle' && (
                  <div className="text-xs text-gray-400">
                    Waiting...
                  </div>
                )}
              </div>
            ))}
          </div>

          {/* Show agent details in expandable sections for very large pools */}
          {Object.keys(coordinationStatus.agents).length > 20 && (
            <div className="mt-4">
              <details className="border rounded p-2">
                <summary className="cursor-pointer font-medium">
                  View All Agent Details ({Object.keys(coordinationStatus.agents).length} agents)
                </summary>
                <div className="mt-2 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
                  {Object.entries(coordinationStatus.agents).map(([agentId, agentData]) => (
                    <div key={agentId} className="border rounded p-2 text-sm">
                      <div className="flex items-center justify-between mb-1">
                        <span className="font-medium">{agentId}</span>
                        <Badge className={`${getStatusColor(agentData.status)} text-white text-xs`}>
                          {agentData.status}
                        </Badge>
                      </div>
                      {agentData.current_task && (
                        <div className="text-xs text-gray-600">
                          <strong>Task:</strong> {agentData.current_task}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </details>
            </div>
          )}
        </CardContent>
      </Card>

      {/* File Locks */}
      {Object.keys(coordinationStatus.file_locks).length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center">
              <Lock className="h-5 w-5 mr-2" />
              Active File Locks
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {Object.entries(coordinationStatus.file_locks).map(([filePath, agentId]) => (
                <div key={filePath} className="flex items-center justify-between p-2 bg-yellow-50 rounded">
                  <span className="font-mono text-sm">{filePath}</span>
                  <Badge variant="outline">Locked by {agentId}</Badge>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Sync Points */}
      {coordinationStatus.active_sync_points.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center">
              <CheckCircle className="h-5 w-5 mr-2" />
              Active Sync Points
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {coordinationStatus.active_sync_points.map((syncPoint) => (
                <div key={syncPoint} className="flex items-center p-2 bg-blue-50 rounded">
                  <CheckCircle className="h-4 w-4 mr-2 text-blue-600" />
                  <span>Sync Point: {syncPoint}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Status Legend */}
      <Card>
        <CardHeader>
          <CardTitle>Status Legend</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-2 text-sm">
            <div className="flex items-center">
              <div className="w-3 h-3 bg-gray-500 rounded mr-2"></div>
              <span>Idle</span>
            </div>
            <div className="flex items-center">
              <div className="w-3 h-3 bg-blue-500 rounded mr-2"></div>
              <span>Assigned</span>
            </div>
            <div className="flex items-center">
              <div className="w-3 h-3 bg-green-500 rounded mr-2"></div>
              <span>Working</span>
            </div>
            <div className="flex items-center">
              <div className="w-3 h-3 bg-yellow-500 rounded mr-2"></div>
              <span>Sync Wait</span>
            </div>
            <div className="flex items-center">
              <div className="w-3 h-3 bg-red-500 rounded mr-2"></div>
              <span>Failed</span>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default MasterCoordinationDashboard;