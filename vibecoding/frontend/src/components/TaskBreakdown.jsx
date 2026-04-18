import { CheckCircle2, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';

const TaskCard = ({ task, index, darkMode, isExecuting }) => {
  const isCompleted = task.status === 'completed';
  const isInProgress = task.status === 'in_progress' || isExecuting;

  return (
    <div className={cn(
      'flex items-center gap-3 py-2 px-3 rounded-lg transition-all',
      darkMode ? 'hover:bg-white/5' : 'hover:bg-gray-50'
    )}>
      {/* Task Number and Title */}
      <div className="flex-1 flex items-center gap-3 min-w-0">
        <span className={cn(
          'text-sm font-medium flex-shrink-0',
          darkMode ? 'text-gray-400' : 'text-gray-600'
        )}>
          {index + 1}.
        </span>
        <span className={cn(
          'text-sm truncate',
          darkMode ? 'text-gray-200' : 'text-gray-800'
        )}>
          {task.title}
        </span>
      </div>

      {/* Status Icon */}
      <div className="flex-shrink-0">
        {isCompleted ? (
          <CheckCircle2 className={cn(
            'w-4 h-4',
            darkMode ? 'text-green-400' : 'text-green-600'
          )} />
        ) : isInProgress ? (
          <Loader2 className={cn(
            'w-4 h-4 animate-spin',
            darkMode ? 'text-blue-400' : 'text-blue-600'
          )} />
        ) : null}
      </div>
    </div>
  );
};

const TaskBreakdown = ({ 
  taskPlan, 
  darkMode, 
  onExecuteAll,
  executingTaskId 
}) => {
  if (!taskPlan || !taskPlan.tasks || taskPlan.tasks.length === 0) {
    return null;
  }

  const { tasks, total_tasks } = taskPlan;
  const completedCount = tasks.filter(t => t.status === 'completed').length;
  const progressPercentage = total_tasks > 0 ? Math.round((completedCount / total_tasks) * 100) : 0;

  return (
    <div className={cn(
      'rounded-lg border overflow-hidden',
      darkMode 
        ? 'bg-white/5 border-white/10' 
        : 'bg-gray-50 border-gray-200'
    )}>
      {/* Header */}
      <div className={cn(
        'px-4 py-3 border-b',
        darkMode ? 'border-white/10' : 'border-gray-200'
      )}>
        <div className="flex items-center justify-between gap-3 mb-2">
          <h3 className={cn(
            'text-sm font-semibold',
            darkMode ? 'text-white' : 'text-gray-900'
          )}>
            Tasks ({completedCount}/{total_tasks})
          </h3>
          <span className={cn(
            'text-xs font-medium',
            darkMode ? 'text-gray-400' : 'text-gray-600'
          )}>
            {progressPercentage}%
          </span>
        </div>

        {/* Progress Bar */}
        <div className={cn(
          'h-1.5 rounded-full overflow-hidden',
          darkMode ? 'bg-white/5' : 'bg-gray-200'
        )}>
          <div
            className={cn(
              'h-full transition-all duration-500',
              darkMode
                ? 'bg-gradient-to-r from-blue-500 to-cyan-500'
                : 'bg-gradient-to-r from-blue-600 to-cyan-600'
            )}
            style={{ width: `${progressPercentage}%` }}
          />
        </div>
      </div>

      {/* Task List */}
      <div className="p-2 max-h-[400px] overflow-y-auto">
        {tasks.map((task, index) => (
          <TaskCard
            key={task.task_id}
            task={task}
            index={index}
            darkMode={darkMode}
            isExecuting={executingTaskId === task.task_id}
          />
        ))}
      </div>
    </div>
  );
};

export default TaskBreakdown;
