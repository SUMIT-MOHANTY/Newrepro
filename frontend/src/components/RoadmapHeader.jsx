import React from 'react';
import { useNavigate } from 'react-router-dom';
import {
    CheckCircle2, Circle, AlertCircle, Loader2,
    FolderOpen, ShieldCheck, Brain, KeyRound, ListChecks, Bot, Flag
} from 'lucide-react';

/**
 * Step icon mapping — maps each step label to a meaningful icon.
 */
const STEP_ICONS = {
    'Project Setup': FolderOpen,
    'Requirement Screening': ShieldCheck,
    'AI Analysis': Brain,
    'Prerequisite Classification': KeyRound,
    'Task Creation': ListChecks,
    'On Flight': Bot,
    'Complete': Flag,
};

/* ── inline styles (keeps this self-contained) ───────────────────── */
const styles = {
    wrapper: {
        width: '100%',
        padding: '16px 0 16px',
        overflowX: 'auto',
    },
    inner: {
        position: 'relative',
        minWidth: '640px',
        padding: '0 32px',
        margin: '0 auto',
        maxWidth: '1100px',
    },
    /* ── The dashed "railway track" line ── */
    trackLine: () => ({
        position: 'absolute',
        top: '50%',
        left: '5%',
        right: '5%',
        height: '3px',
        transform: 'translateY(-50%)',
        /* grey dashed track */
        backgroundImage:
            'linear-gradient(to right, #c5c9d0 60%, transparent 60%)',
        backgroundSize: '14px 3px',
        backgroundRepeat: 'repeat-x',
        zIndex: 0,
    }),
    trackProgress: (completedPct, failedStep) => {
        let bg = 'linear-gradient(to right, #34d399 60%, transparent 60%)'; // green dashes
        if (failedStep !== null && failedStep !== undefined) {
            bg = 'linear-gradient(to right, #34d399 60%, transparent 60%)';
        }
        return {
            position: 'absolute',
            top: '50%',
            left: '5%',
            width: `${completedPct}%`,
            height: '3px',
            transform: 'translateY(-50%)',
            backgroundImage: bg,
            backgroundSize: '14px 3px',
            backgroundRepeat: 'repeat-x',
            transition: 'width 0.6s ease-out',
            zIndex: 1,
        };
    },
    stepsRow: {
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        position: 'relative',
        zIndex: 2,
        /* this is the reference line for vertical centering of the dots */
        height: '90px',
    },
};

/**
 * RoadmapHeader — Railway-track dotted stepper.
 */
const RoadmapHeader = ({ steps = [], currentStep = 0, stepStatuses, failedStep, activeStepIndex = null }) => {
    const navigate = useNavigate();
    if (!steps.length) return null;

    const baseStatuses =
        stepStatuses && stepStatuses.length === steps.length
            ? stepStatuses
            : steps.map((_, i) => {
                if (failedStep !== null && failedStep !== undefined && i === failedStep) return 'failed';
                if (i < currentStep) return 'completed';
                if (i === currentStep) return 'active';
                return 'pending';
            });

    const statuses = (() => {
        if (activeStepIndex === null || activeStepIndex === undefined) {
            return baseStatuses;
        }
        if (activeStepIndex < 0 || activeStepIndex >= steps.length) {
            return baseStatuses;
        }

        const next = baseStatuses.map((status, idx) => {
            if (status === 'failed') return 'failed';
            if (idx < activeStepIndex) return status === 'pending' ? 'completed' : status;
            if (idx === activeStepIndex) return 'active';
            return status === 'active' ? 'pending' : status;
        });
        return next;
    })();

    // Map step labels to navigable routes
    const STEP_ROUTES = {
        'Requirement Screening': '/governance',
        'Prerequisite Classification': '/prerequisites',
        'Task Creation': '/task-creation',
    };

    const handleStepClick = (stepLabel, status) => {
        const route = STEP_ROUTES[stepLabel];
        if (route && (status === 'active' || status === 'completed')) {
            navigate(route);
        }
    };

    // percentage of the track that is "filled"
    const filledPct = Math.min(
        ((currentStep) / (steps.length - 1)) * 90,
        90
    );

    return (
        <div style={styles.wrapper}>
            <div style={styles.inner}>
                {/* Dashed track — background (grey) */}
                <div style={styles.trackLine()} />
                {/* Dashed track — progress (green) */}
                <div style={styles.trackProgress(filledPct, failedStep, steps.length)} />

                {/* Step nodes */}
                <div style={styles.stepsRow}>
                    {steps.map((step, index) => {
                        const status = statuses[index];
                        const StepIcon = STEP_ICONS[step] || Circle;
                        const labelPosition = index % 2 === 0 ? 'top' : 'bottom';
                        const isClickable = !!(STEP_ROUTES[step] && (status === 'active' || status === 'completed'));
                        return (
                            <StepNode
                                key={index}
                                index={index}
                                label={step}
                                status={status}
                                icon={StepIcon}
                                labelPosition={labelPosition}
                                clickable={isClickable}
                                onClick={() => handleStepClick(step, status)}
                            />
                        );
                    })}
                </div>
            </div>
        </div>
    );
};

/**
 * StepNode — A single "station" dot on the railway track.
 */
const StepNode = ({ label, status, icon, labelPosition, clickable, onClick }) => {
    /**
     * Style map per status.
     */
    const cfgMap = {
        completed: {
            dotSize: 32,
            bg: '#dcfce7',
            border: '2px solid #22c55e',
            iconColor: '#16a34a',
            shadow: '0 0 0 3px rgba(34,197,94,.15)',
            labelWeight: '600',
            labelColor: '#374151',
            stepColor: '#16a34a',
        },
        active: {
            dotSize: 38,
            bg: '#fef3c7',
            border: '3px solid #f59e0b',
            iconColor: '#d97706',
            shadow: '0 0 0 6px rgba(245,158,11,.18), 0 0 18px rgba(245,158,11,.25)',
            labelWeight: '700',
            labelColor: '#111827',
            stepColor: '#d97706',
            glow: true,
        },
        pending: {
            dotSize: 28,
            bg: '#f3f4f6',
            border: '2px solid #d1d5db',
            iconColor: '#9ca3af',
            shadow: 'none',
            labelWeight: '400',
            labelColor: '#9ca3af',
            stepColor: '#9ca3af',
        },
        failed: {
            dotSize: 34,
            bg: '#fee2e2',
            border: '2px solid #ef4444',
            iconColor: '#dc2626',
            shadow: '0 0 0 4px rgba(239,68,68,.15)',
            labelWeight: '700',
            labelColor: '#991b1b',
            stepColor: '#dc2626',
        },
    };

    const c = cfgMap[status] || cfgMap.pending;

    const dotStyle = {
        width: c.dotSize,
        height: c.dotSize,
        borderRadius: '50%',
        background: c.bg,
        border: c.border,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        boxShadow: c.shadow,
        transition: 'all 0.3s ease',
        position: 'relative',
        zIndex: 3,
        cursor: clickable ? 'pointer' : 'default',
    };

    const labelBlock = (
        <div style={{
            textAlign: 'center',
            maxWidth: '90px',
            lineHeight: '1.25',
        }}>
            <p style={{
                fontSize: '11px',
                margin: 0,
                color: c.labelColor,
                fontWeight: c.labelWeight,
            }}>
                {label}
            </p>
            {status === 'failed' && (
                <p style={{ fontSize: '9px', color: '#ef4444', margin: '2px 0 0', fontWeight: 600 }}>
                    Failed
                </p>
            )}
        </div>
    );

    return (
        <div
            style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                gap: '4px',
                position: 'relative',
                flex: '0 0 auto',
            }}
            onClick={clickable ? onClick : undefined}
            title={clickable ? `Click to open ${label}` : undefined}
        >
            {/* Label on TOP if even index */}
            {labelPosition === 'top' && (
                <div style={{ marginBottom: '2px', minHeight: '28px', display: 'flex', alignItems: 'flex-end' }}>
                    {labelBlock}
                </div>
            )}

            {/* Spacer when label is at bottom — keeps the dot vertically centered */}
            {labelPosition === 'bottom' && (
                <div style={{ minHeight: '28px' }} />
            )}

            {/* The dot / station marker */}
            <div style={{ position: 'relative' }}>
                {/* Active glow ring animation */}
                {c.glow && (
                    <span style={{
                        position: 'absolute',
                        inset: '-6px',
                        borderRadius: '50%',
                        border: '2px solid rgba(245,158,11,.4)',
                        animation: 'roadmapPulse 2s ease-in-out infinite',
                    }} />
                )}
                {/* Failed pulse ring */}
                {status === 'failed' && (
                    <span style={{
                        position: 'absolute',
                        inset: '-5px',
                        borderRadius: '50%',
                        border: '2px solid rgba(239,68,68,.35)',
                        animation: 'roadmapPulse 2s ease-in-out infinite',
                    }} />
                )}
                <div style={dotStyle}>
                    {React.createElement(icon, { style: { width: c.dotSize * 0.45, height: c.dotSize * 0.45, color: c.iconColor } })}
                </div>
            </div>

            {/* Label on BOTTOM if odd index */}
            {labelPosition === 'bottom' && (
                <div style={{ marginTop: '2px', minHeight: '28px', display: 'flex', alignItems: 'flex-start' }}>
                    {labelBlock}
                </div>
            )}

            {/* Spacer when label is at top — keeps layout balanced */}
            {labelPosition === 'top' && (
                <div style={{ minHeight: '28px' }} />
            )}
        </div>
    );
};

/* ── Inject keyframes for the pulse animation ── */
const pulseKeyframes = `
@keyframes roadmapPulse {
    0%, 100% { transform: scale(1); opacity: 1; }
    50% { transform: scale(1.35); opacity: 0; }
}
`;

// Inject the keyframes into the document head (runs once)
if (typeof document !== 'undefined') {
    const existingStyle = document.getElementById('roadmap-pulse-style');
    if (!existingStyle) {
        const styleTag = document.createElement('style');
        styleTag.id = 'roadmap-pulse-style';
        styleTag.textContent = pulseKeyframes;
        document.head.appendChild(styleTag);
    }
}

export default RoadmapHeader;
