import { useState } from 'react';
import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/vibecoding';

export const useTaskHandlers = (currentProjectId, messages, setMessages, setLoading, setVerificationStatus) => {
  const [executingTaskId, setExecutingTaskId] = useState(null);

  const handleExecuteTask = async (taskId) => {
    if (!currentProjectId) return;
    
    setExecutingTaskId(taskId);
    setLoading(true);
    
    try {
      const payload = {
        prompt: `TASK:EXECUTE:${taskId.replace('task_', '')}`,
        history: messages,
        project_id: currentProjectId,
        discuss_mode: false,
      };
      
      const response = await axios.post(`${API_BASE_URL}/api/generate`, payload);
      
      const aiMessage = {
        role: 'assistant',
        content: response.data.message,
        code: response.data.code,
        versionId: response.data.version_id,
        summary: response.data.summary,
        metadata: response.data.metadata || {},
        timestamp: new Date().toISOString(),
        id: response.data.message_id
      };
      
      setMessages(prev => [...prev, aiMessage]);
      
      if (response.data.code) {
        setVerificationStatus('checking');
      }
    } catch (error) {
      console.error('Task execution failed:', error);
      const errorMessage = {
        role: 'assistant',
        content: `❌ Failed to execute task: ${error.response?.data?.detail || error.message}`,
        timestamp: new Date().toISOString()
      };
      setMessages(prev => [...prev, errorMessage]);
    } finally {
      setLoading(false);
      setExecutingTaskId(null);
    }
  };

  const handleExecuteAllTasks = async () => {
    if (!currentProjectId) return;
    
    setLoading(true);
    
    try {
      const payload = {
        prompt: 'TASK:START',
        history: messages,
        project_id: currentProjectId,
        discuss_mode: false,
      };
      
      const response = await axios.post(`${API_BASE_URL}/api/generate`, payload);
      
      const aiMessage = {
        role: 'assistant',
        content: response.data.message,
        code: response.data.code,
        versionId: response.data.version_id,
        summary: response.data.summary,
        metadata: response.data.metadata || {},
        timestamp: new Date().toISOString(),
        id: response.data.message_id
      };
      
      setMessages(prev => [...prev, aiMessage]);
      
      if (response.data.code) {
        setVerificationStatus('checking');
      }
    } catch (error) {
      console.error('Task execution failed:', error);
      const errorMessage = {
        role: 'assistant',
        content: `❌ Failed to execute tasks: ${error.response?.data?.detail || error.message}`,
        timestamp: new Date().toISOString()
      };
      setMessages(prev => [...prev, errorMessage]);
    } finally {
      setLoading(false);
    }
  };

  const handleEditTask = async (taskId, newDescription) => {
    // Update task description in the local state
    setMessages(prev => prev.map(msg => {
      if (msg.metadata?.task_plan) {
        const updatedTasks = msg.metadata.task_plan.tasks.map(task => {
          if (task.task_id === taskId) {
            return { ...task, description: newDescription };
          }
          return task;
        });
        return {
          ...msg,
          metadata: {
            ...msg.metadata,
            task_plan: {
              ...msg.metadata.task_plan,
              tasks: updatedTasks
            }
          }
        };
      }
      return msg;
    }));
  };

  return {
    executingTaskId,
    handleExecuteTask,
    handleExecuteAllTasks,
    handleEditTask
  };
};
