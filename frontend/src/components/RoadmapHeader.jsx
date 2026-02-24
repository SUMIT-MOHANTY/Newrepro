import React from 'react';
import {
    CheckCircle2, Circle, AlertCircle, Loader2,
    FolderOpen, ShieldCheck, Brain, ListChecks, Bot, Flag
} from 'lucide-react';

/**
 * Step icon mapping — maps each step label to a meaningful icon.
 */
const STEP_ICONS = {
    'Project Setup': FolderOpen,
    'Governance': ShieldCheck,
    'AI Analysis': Brain,
    'Task Creation': ListChecks,
    'Agent Execution': Bot,
    'Complete': Flag,
};

/**
 * RoadmapHeader — A dynamic, project-level progress stepper.
 *
 * ### Props
 *   - steps: string[]            — label for each step
 *   - currentStep: number        — index of the currently active step
 *   - stepStatuses: string[]     — per-step status ("completed"|"active"|"pending"|"failed")
 *   - failedStep: number | null  — index of a failed step (if any)
 *
 * If `stepStatuses` is not supplied, statuses are derived from `currentStep`.
 */
const RoadmapHeader = ({ steps = [], currentStep = 0, stepStatuses, failedStep }) => {
    if (!steps.length) return null;

    // Build derived statuses when the backend hasn't provided them
    const statuses =
        stepStatuses && stepStatuses.length === steps.length
            ? stepStatuses
            : steps.map((_, i) => {
                if (failedStep !== null && failedStep !== undefined && i === failedStep) return 'failed';
                if (i < currentStep) return 'completed';
                if (i === currentStep) return 'active';
                return 'pending';
            });

    return (
        <div className="w-full py-4 sm:py-5 overflow-x-auto">
            <div className="relative min-w-[640px] px-4 mx-auto max-w-6xl">

                {/* ── Connecting line ── */}
                <div
                    className="absolute left-0 right-0 mx-auto"
                    style={{
                        top: '22px',
                        left: '8%',
                        right: '8%',
                        height: '3px',
                        background: 'linear-gradient(90deg, #e5e7eb 0%, #e5e7eb 100%)',
                        borderRadius: '2px',
                    }}
                />
                {/* ── Progress fill on the connecting line ── */}
                <div
                    className="absolute"
                    style={{
                        top: '22px',
                        left: '8%',
                        width: `${Math.min(((currentStep) / (steps.length - 1)) * 84, 84)}%`,
                        height: '3px',
                        background: failedStep !== null && failedStep !== undefined
                            ? `linear-gradient(90deg, #2563eb 0%, #2563eb ${Math.min((failedStep / (steps.length - 1)) * 100, 100)}%, #ef4444 ${Math.min((failedStep / (steps.length - 1)) * 100, 100)}%)`
                            : 'linear-gradient(90deg, #2563eb, #6366f1)',
                        borderRadius: '2px',
                        transition: 'width 0.6s ease-out',
                    }}
                />

                <div className="flex justify-between items-start w-full relative">
                    {steps.map((step, index) => {
                        const status = statuses[index];
                        const StepIcon = STEP_ICONS[step] || Circle;
                        return (
                            <StepNode
                                key={index}
                                index={index}
                                label={step}
                                status={status}
                                Icon={StepIcon}
                            />
                        );
                    })}
                </div>
            </div>
        </div>
    );
};

/**
 * Individual step node with icon, indicator, and label.
 */
const StepNode = ({ index, label, status, Icon }) => {
    // Status-based styling
    const config = {
        completed: {
            ring: 'bg-gradient-to-br from-blue-500 to-indigo-600 shadow-md shadow-blue-200/60',
            iconColor: 'text-white',
            labelColor: 'text-gray-800',
            subColor: 'text-blue-600',
            indicator: <CheckCircle2 className="w-4 h-4" />,
            scale: '',
        },
        active: {
            ring: 'bg-white border-2 border-blue-500 shadow-lg shadow-blue-100 ring-4 ring-blue-50',
            iconColor: 'text-blue-600',
            labelColor: 'text-gray-900 font-bold',
            subColor: 'text-blue-600 font-bold',
            indicator: <Loader2 className="w-4 h-4 animate-spin" />,
            scale: 'scale-110',
        },
        pending: {
            ring: 'bg-gray-100 border border-gray-200',
            iconColor: 'text-gray-400',
            labelColor: 'text-gray-400',
            subColor: 'text-gray-400',
            indicator: <Circle className="w-3.5 h-3.5" />,
            scale: '',
        },
        failed: {
            ring: 'bg-gradient-to-br from-red-500 to-rose-600 shadow-md shadow-red-200/60',
            iconColor: 'text-white',
            labelColor: 'text-red-700 font-bold',
            subColor: 'text-red-600 font-bold',
            indicator: <AlertCircle className="w-4 h-4" />,
            scale: '',
        },
    };

    const c = config[status] || config.pending;

    return (
        <div className={`flex flex-col items-center group relative z-10 transition-transform duration-300 ${c.scale}`}
            style={{ minWidth: '80px', maxWidth: '110px' }}
        >
            {/* Icon circle */}
            <div
                className={`relative flex items-center justify-center w-11 h-11 rounded-full transition-all duration-300 ${c.ring}`}
            >
                {status === 'active' && (
                    <span className="absolute inset-0 rounded-full animate-ping bg-blue-400/20" />
                )}
                {status === 'failed' && (
                    <span className="absolute inset-0 rounded-full animate-pulse bg-red-400/20" />
                )}
                <Icon className={`w-5 h-5 ${c.iconColor} relative z-10`} />
            </div>

            {/* Step label */}
            <div className="mt-2.5 text-center">
                <p className={`text-[9px] sm:text-[10px] uppercase tracking-wider mb-0.5 ${c.subColor}`}>
                    Step {index + 1}
                </p>
                <p className={`text-[10px] sm:text-xs leading-tight mx-auto ${c.labelColor}`}>
                    {label}
                </p>
                {status === 'failed' && (
                    <p className="text-[9px] text-red-500 mt-0.5 font-medium">Failed</p>
                )}
            </div>
        </div>
    );
};

export default RoadmapHeader;
