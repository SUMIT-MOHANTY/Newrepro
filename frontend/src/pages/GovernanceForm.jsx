import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { API_ENDPOINTS } from '../config';
import {
    Send, AlertCircle, CheckCircle2, AlertTriangle,
    ChevronRight, ChevronLeft, ArrowRight, Check
} from 'lucide-react';
import RoadmapHeader from '../components/RoadmapHeader';

/* ─────────────────────────────────────────────────────────
   STEP INDICATOR  (compact, responsive)
───────────────────────────────────────────────────────── */
/* ─────────────────────────────────────────────────────────
   STEP INDICATOR  (responsive: vertical on desktop, horizontal on mobile)
   Now accepts a `vertical` prop to switch layout modes.
───────────────────────────────────────────────────────── */
const StepIndicator = ({ steps, currentStep, vertical = false }) => {
    // ── VERTICAL LAYOUT (Desktop Sidebar) ──
    if (vertical) {
        return (
            <div className="flex flex-col w-full">
                <div className="space-y-1">
                    {steps.map((step, idx) => {
                        const done = idx < currentStep;
                        const active = idx === currentStep;
                        return (
                            <div key={step} className="flex items-center gap-3 py-2 group">
                                {/* Indicator Circle */}
                                <div className={`relative z-10 flex items-center justify-center w-8 h-8 rounded-full text-xs font-bold border-2 transition-all duration-300
                                    ${done ? 'bg-blue-600 border-blue-600 text-white'
                                        : active ? 'bg-white border-blue-600 text-blue-600 ring-4 ring-blue-50'
                                            : 'bg-white border-gray-200 text-gray-400 group-hover:border-gray-300'}`}
                                >
                                    {done ? <Check className="w-4 h-4" /> : idx + 1}
                                </div>
                                {/* Label */}
                                <div className="flex flex-col">
                                    <span className={`text-xs font-bold uppercase tracking-wider transition-colors duration-200
                                        ${active ? 'text-blue-700' : done ? 'text-gray-700' : 'text-gray-400'}`}
                                    >
                                        Step {idx + 1}
                                    </span>
                                    <span className={`text-sm font-medium transition-colors duration-200
                                        ${active ? 'text-gray-900' : 'text-gray-500'}`}
                                    >
                                        {step}
                                    </span>
                                </div>
                                {/* Vertical Line Connection (visual only, handled by parent spacing, but could be added here if needed) */}
                            </div>
                        );
                    })}
                </div>
            </div>
        );
    }

    // ── HORIZONTAL LAYOUT (Mobile / Tablet) ──
    return (
        <div className="w-full mb-6">
            <div className="flex items-center justify-between text-xs mb-2">
                <span className="font-bold text-blue-600">Step {currentStep + 1} of {steps.length}</span>
                <span className="text-gray-500 font-medium truncate ml-2">{steps[currentStep]}</span>
            </div>
            <div className="w-full bg-gray-100 rounded-full h-2 overflow-hidden">
                <div
                    className="bg-blue-600 h-full rounded-full transition-all duration-500 ease-out"
                    style={{ width: `${((currentStep + 1) / steps.length) * 100}%` }}
                />
            </div>
        </div>
    );
};

/* ─────────────────────────────────────────────────────────
   MAIN FORM COMPONENT
───────────────────────────────────────────────────────── */
const GovernanceForm = () => {
    const navigate = useNavigate();
    const [questions, setQuestions] = useState([]);
    const [answers, setAnswers] = useState({});
    const [projectName, setProjectName] = useState('');
    const [loading, setLoading] = useState(true);
    const [submitting, setSubmitting] = useState(false);
    const [error, setError] = useState('');
    const [result, setResult] = useState(null);

    // Step state: 0 = Project Name, 1…N = dimension steps, N+1 = review
    const [currentStep, setCurrentStep] = useState(0);

    /* ── helpers ── */
    const getStoredJson = (key) => {
        const raw = sessionStorage.getItem(key) || localStorage.getItem(key);
        if (!raw) return null;
        try { return JSON.parse(raw); } catch { return null; }
    };

    const normalizeDimensionScores = (dimensionScores = {}) => ({
        'Business Value & Urgency': dimensionScores['Business Value & Urgency'] ?? dimensionScores.business_value ?? 0,
        'Data Sensitivity': dimensionScores['Data Sensitivity'] ?? dimensionScores.data_sensitivity ?? 0,
        'Integration & Architecture Complexity': dimensionScores['Integration & Architecture Complexity'] ?? dimensionScores.integration_complexity ?? 0,
        'Operational Impact': dimensionScores['Operational Impact'] ?? dimensionScores.operational_impact ?? 0,
        'AI Risk': dimensionScores['AI Risk'] ?? dimensionScores.ai_risk ?? 0,
        'Ownership & Support': dimensionScores['Ownership & Support'] ?? dimensionScores.ownership ?? 0,
    });

    const persistGovernanceData = (ctx, res) => {
        sessionStorage.setItem('governanceContext', JSON.stringify(ctx));
        sessionStorage.setItem('governanceResult', JSON.stringify(res));
        localStorage.setItem('governanceContext', JSON.stringify(ctx));
        localStorage.setItem('governanceResult', JSON.stringify(res));
    };

    /* ── mount ── */
    useEffect(() => {
        fetchQuestions();

        const savedContext = getStoredJson('governanceContext');
        if (savedContext) {
            if (savedContext.project_name) setProjectName(savedContext.project_name);
            if (Array.isArray(savedContext.answers)) {
                const r = {};
                savedContext.answers.forEach((a) => {
                    if (a?.question_id !== undefined && a?.score !== undefined)
                        r[a.question_id] = a.score;
                });
                setAnswers(r);
            }
        }

        const savedResult = getStoredJson('governanceResult');
        if (savedResult) setResult(savedResult);
    }, []);

    /* ── API: questions ── */
    const fetchQuestions = async () => {
        try {
            const res = await fetch(API_ENDPOINTS.GOVERNANCE_QUESTIONS);
            if (!res.ok) throw new Error('Failed to load questions');
            const data = await res.json();
            setQuestions(data.questions);
            setLoading(false);
        } catch (err) {
            setError('Failed to load governance questions: ' + err.message);
            setLoading(false);
        }
    };



    const handleAnswer = (questionId, score) =>
        setAnswers((prev) => ({ ...prev, [questionId]: score }));

    /* ── submit ── */
    const handleSubmit = async (e) => {
        e?.preventDefault();

        if (!projectName.trim()) { setError('Please enter a project name'); return; }
        if (Object.keys(answers).length !== questions.length) {
            setError('Please answer all questions before submitting');
            return;
        }

        setSubmitting(true);
        setError('');
        try {
            const formattedAnswers = questions.map((q) => ({
                question_id: q.id,
                question: q.question,
                dimension: q.dimension,
                score: answers[q.id],
                selected_option: q.options.find((o) => o.score === answers[q.id])?.label || '',
            }));

            const submission = {
                project_name: projectName,
                answers: formattedAnswers.map((a) => ({
                    question_id: a.question_id,
                    score: a.score,
                    selected_option: a.selected_option,
                })),
            };

            const token = localStorage.getItem('token');
            const res = await fetch(API_ENDPOINTS.GOVERNANCE_SUBMIT, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
                body: JSON.stringify(submission),
            });
            if (!res.ok) {
                const e = await res.json();
                throw new Error(e.detail || 'Submission failed');
            }
            const resultData = await res.json();
            const normalizedDS = normalizeDimensionScores(resultData.dimension_scores);
            const normalizedResultData = { ...resultData, dimension_scores: normalizedDS };
            const ctx = {
                project_name: projectName,
                result_id: resultData.id,
                submission_date: resultData.submission_date,
                classification: resultData.classification,
                classification_description: resultData.classification_description,
                weighted_score: resultData.weighted_score,
                recommendation: resultData.recommendation,
                hard_stops: resultData.hard_stops || [],
                answers: formattedAnswers,
                dimension_scores: normalizedDS,
            };
            persistGovernanceData(ctx, normalizedResultData);
            setResult(normalizedResultData);
        } catch (err) {
            setError('Submission error: ' + err.message);
        } finally {
            setSubmitting(false);
        }
    };

    /* ── loading / result screens ── */
    if (loading) {
        return (
            <div className="flex items-center justify-center min-h-screen bg-gray-50">
                <div className="flex flex-col items-center gap-4">
                    <div className="w-12 h-12 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin" />
                    <p className="text-gray-500 font-medium">Loading governance questionnaire…</p>
                </div>
            </div>
        );
    }

    if (result) {
        return <GovernanceResult result={result} onBack={() => setResult(null)} />;
    }

    /* ── build dimension list ── */
    const questionsByDimension = {};
    questions.forEach((q) => {
        if (!questionsByDimension[q.dimension]) questionsByDimension[q.dimension] = [];
        questionsByDimension[q.dimension].push(q);
    });
    const dimensions = Object.keys(questionsByDimension);

    // steps: 0 = Project Name, 1..N = dimensions, N+1 = Review & Submit
    const TOTAL_STEPS = dimensions.length + 2; // +1 project name, +1 review
    const stepLabels = ['Project', ...dimensions.map((d) => d.split(' ')[0]), 'Review'];
    const isDimensionStep = currentStep >= 1 && currentStep <= dimensions.length;
    const isReviewStep = currentStep === dimensions.length + 1;
    const activeDimension = isDimensionStep ? dimensions[currentStep - 1] : null;
    const activeQuestions = activeDimension ? questionsByDimension[activeDimension] : [];



    const canProceed = () => {
        if (currentStep === 0) return projectName.trim().length > 0;
        if (isDimensionStep) return activeQuestions.every((q) => answers[q.id] !== undefined);
        return true;
    };

    const goNext = () => {
        if (!canProceed()) {
            if (currentStep === 0) setError('Please enter a project name before continuing.');
            else setError('Please answer all questions in this section before continuing.');
            return;
        }
        setError('');
        setCurrentStep((s) => Math.min(s + 1, TOTAL_STEPS - 1));
    };

    const goPrev = () => {
        setError('');
        setCurrentStep((s) => Math.max(s - 1, 0));
    };


    /* ── render ── */
    return (
        <div className="min-h-screen bg-gray-50">


            {/* ── MAIN AREA ── */}
            <div className="px-3 sm:px-4 lg:px-6 py-4 lg:py-6 max-w-[1440px] mx-auto">

                {/* Page header — compact */}
                <div className="flex items-start justify-between gap-3 mb-5">
                    <div>
                        <h1 className="text-xl sm:text-2xl lg:text-3xl font-extrabold text-gray-900 tracking-tight">
                            Governance Questionnaire
                        </h1>
                        <p className="text-gray-400 text-sm mt-0.5">
                            {questions.length} questions · {dimensions.length} dimensions
                        </p>
                    </div>

                </div>

                {/* ── Roadmap / Timeline Header ── */}
                <RoadmapHeader steps={stepLabels} currentStep={currentStep} />

                <div className="flex gap-5 items-start">

                    {/* ── DESKTOP SIDEBAR (≥1024px) ── */}
                    <aside className="hidden lg:block w-64 xl:w-72 flex-shrink-0 sticky top-6 self-start">
                        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
                            <h2 className="text-xs font-bold uppercase tracking-widest text-gray-500 mb-6">Progress</h2>
                            <StepIndicator steps={stepLabels} currentStep={currentStep} vertical={true} />
                        </div>
                    </aside>

                    {/* ── MAIN CONTENT: Step Wizard ── */}
                    <div className="flex-1 min-w-0 max-w-4xl">
                        {/* Error banner */}
                        {error && (
                            <div className="rounded-lg bg-red-50 p-4 border border-red-200 text-red-700 mb-5 flex items-start gap-3">
                                <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
                                <div>{error}</div>
                            </div>
                        )}

                        {/* Mobile Step indicator (horizontal) */}
                        <div className="lg:hidden">
                            <StepIndicator steps={stepLabels} currentStep={currentStep} />
                        </div>

                        {/* Wrapper: fixed min-height so nav buttons stay at a consistent position */}
                        <div className="flex flex-col min-h-[calc(100vh-14rem)]">
                            {/* Step card */}
                            <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">

                                {/* ── STEP 0: Project Name ── */}
                                {currentStep === 0 && (
                                    <div className="p-5 sm:p-6">
                                        <div className="mb-5">
                                            <h2 className="text-xl font-bold text-gray-900 mb-1">Project Details</h2>
                                            <p className="text-gray-400 text-sm">Give your project a descriptive name.</p>
                                        </div>
                                        <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">
                                            Project Name <span className="text-red-500">*</span>
                                        </label>
                                        <input
                                            type="text"
                                            value={projectName}
                                            onChange={(e) => setProjectName(e.target.value)}
                                            onKeyDown={(e) => e.key === 'Enter' && goNext()}
                                            placeholder="e.g. Customer Analytics Platform"
                                            className="w-full px-4 py-2.5 border border-gray-200 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm bg-gray-50 text-gray-900 transition"
                                        />
                                    </div>
                                )}

                                {/* ── STEP 1…N: Dimension questions ── */}
                                {isDimensionStep && (
                                    <div className="p-5 sm:p-6">
                                        {/* Dimension header */}
                                        <div className="mb-5">
                                            <div className="flex items-center gap-3 mb-1">
                                                <h2 className="text-xl font-bold text-gray-900">{activeDimension}</h2>
                                                <span className="text-xs text-gray-400 bg-gray-100 px-2 py-0.5 rounded font-medium">
                                                    {activeQuestions.filter((q) => answers[q.id] !== undefined).length}/{activeQuestions.length}
                                                </span>
                                            </div>
                                            {/* mini progress bar */}
                                            <div className="w-full bg-gray-100 rounded-full h-1 mt-2">
                                                <div
                                                    className="bg-blue-500 h-1 rounded-full transition-all duration-300"
                                                    style={{ width: `${(activeQuestions.filter((q) => answers[q.id] !== undefined).length / activeQuestions.length) * 100}%` }}
                                                />
                                            </div>
                                        </div>

                                        {/* Questions */}
                                        <div className="space-y-5">
                                            {activeQuestions.map((question, qIdx) => {
                                                const answered = answers[question.id] !== undefined;
                                                return (
                                                    <div
                                                        key={question.id}
                                                        className={`rounded-lg border p-4 transition-all duration-200 ${answered ? 'border-blue-200 bg-blue-50/30' : 'border-gray-200 bg-white'}`}
                                                    >
                                                        <div className="flex items-start gap-2.5 mb-3">
                                                            <span className={`flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center text-[11px] font-bold ${answered ? 'bg-blue-600 text-white' : 'bg-gray-200 text-gray-500'}`}>
                                                                {answered ? <Check className="w-3.5 h-3.5" /> : qIdx + 1}
                                                            </span>
                                                            <h3 className="text-gray-900 font-medium text-sm leading-snug pt-0.5">{question.question}</h3>
                                                        </div>

                                                        {/* Options — 2 cols on wider screens */}
                                                        <div className="ml-8 grid grid-cols-1 sm:grid-cols-2 gap-1.5">
                                                            {question.options.map((option) => {
                                                                const selected = answers[question.id] === option.score;
                                                                return (
                                                                    <label
                                                                        key={option.label}
                                                                        className={`flex items-center gap-2 cursor-pointer rounded-lg px-3 py-2 border text-sm transition-all duration-150 ${selected
                                                                            ? 'border-blue-500 bg-blue-50 text-blue-900 font-medium'
                                                                            : 'border-gray-200 bg-white text-gray-600 hover:border-blue-300 hover:bg-blue-50/20'}`}
                                                                    >
                                                                        <input
                                                                            type="radio"
                                                                            name={`question-${question.id}`}
                                                                            value={option.score}
                                                                            checked={selected}
                                                                            onChange={() => handleAnswer(question.id, option.score)}
                                                                            className="w-3.5 h-3.5 text-blue-600 border-gray-300 focus:ring-blue-500"
                                                                        />
                                                                        <span>{option.label}</span>
                                                                    </label>
                                                                );
                                                            })}
                                                        </div>
                                                    </div>
                                                );
                                            })}
                                        </div>
                                    </div>
                                )}

                                {/* ── REVIEW STEP ── */}
                                {isReviewStep && (
                                    <div className="p-5 sm:p-6">
                                        <div className="mb-5">
                                            <h2 className="text-xl font-bold text-gray-900 mb-1">Review & Submit</h2>
                                            <p className="text-gray-400 text-sm">Verify your answers, then submit.</p>
                                        </div>

                                        {/* Summary grid */}
                                        <div className="space-y-2.5 mb-5">
                                            <div className="rounded-lg border border-gray-200 bg-gray-50 px-4 py-3">
                                                <p className="text-[10px] font-bold uppercase tracking-widest text-gray-400 mb-0.5">Project</p>
                                                <p className="text-gray-900 font-semibold text-sm">{projectName}</p>
                                            </div>

                                            {dimensions.map((dim, idx) => {
                                                const qs = questionsByDimension[dim];
                                                const allDone = qs.every((q) => answers[q.id] !== undefined);
                                                const answered = qs.filter((q) => answers[q.id] !== undefined).length;
                                                return (
                                                    <div
                                                        key={dim}
                                                        className={`rounded-lg border px-4 py-3 flex items-center gap-3 ${allDone ? 'border-green-200 bg-green-50/30' : 'border-red-200 bg-red-50/30'}`}
                                                    >
                                                        <div className={`w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0 ${allDone ? 'bg-green-500 text-white' : 'bg-red-400 text-white'}`}>
                                                            {allDone ? <Check className="w-3 h-3" /> : <AlertCircle className="w-3 h-3" />}
                                                        </div>
                                                        <div className="flex-1 min-w-0">
                                                            <p className="text-sm font-semibold text-gray-800 truncate">{dim}</p>
                                                            <p className="text-[11px] text-gray-500">{answered}/{qs.length} answered</p>
                                                        </div>
                                                        {!allDone && (
                                                            <button type="button" onClick={() => { setError(''); setCurrentStep(idx + 1); }} className="text-[11px] text-blue-600 font-semibold hover:underline flex-shrink-0">Fix →</button>
                                                        )}
                                                    </div>
                                                );
                                            })}
                                        </div>

                                        <button
                                            type="button"
                                            onClick={handleSubmit}
                                            disabled={submitting || Object.keys(answers).length !== questions.length}
                                            className="w-full inline-flex items-center justify-center py-3 px-6 text-sm font-bold rounded-xl text-white bg-blue-600 hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-all active:scale-[0.98] shadow-md gap-2"
                                        >
                                            <Send className="w-4 h-4" />
                                            {submitting ? 'Submitting…' : 'Submit & Score'}
                                        </button>
                                    </div>
                                )}
                            </div>
                            {/* end of step card */}

                            {/* ── NAV BUTTONS (pushed to bottom of min-height wrapper) ── */}
                            {/* ── NAV BUTTONS (pushed to bottom of min-height wrapper) ── */}
                            <div className="flex items-center justify-end gap-3 mt-auto pt-4 px-1">
                                {currentStep === 0 ? (
                                    <button type="button" onClick={() => navigate('/dashboard')} className="inline-flex items-center gap-1.5 py-2.5 px-5 text-sm font-semibold rounded-xl text-gray-500 bg-white border border-gray-200 hover:bg-gray-50 transition shadow-sm">
                                        <ChevronLeft className="w-4 h-4" /> Dashboard
                                    </button>
                                ) : (
                                    <button type="button" onClick={goPrev} className="inline-flex items-center gap-1.5 py-2.5 px-5 text-sm font-semibold rounded-xl text-gray-500 bg-white border border-gray-200 hover:bg-gray-50 transition shadow-sm">
                                        <ChevronLeft className="w-4 h-4" /> Back
                                    </button>
                                )}

                                {!isReviewStep && (
                                    <button
                                        type="button"
                                        onClick={goNext}
                                        disabled={!canProceed()}
                                        className={`inline-flex items-center gap-1.5 py-2.5 px-6 text-sm font-bold rounded-xl text-white transition-all shadow-sm ${canProceed()
                                            ? 'bg-blue-600 hover:bg-blue-700 active:scale-[0.97]'
                                            : 'bg-gray-300 cursor-not-allowed'
                                            }`}
                                    >
                                        {currentStep === dimensions.length ? 'Review' : 'Next'}
                                        <ChevronRight className="w-4 h-4" />
                                    </button>
                                )}
                            </div>
                        </div>
                        {/* end of min-height wrapper */}
                    </div>
                </div>
            </div>
        </div>
    );
};

/* ─────────────────────────────────────────────────────────
   RESULT COMPONENT  — Premium, user-friendly redesign
───────────────────────────────────────────────────────── */
const CLASSIFICATION_THEME = {
    SANDBOX: {
        gradient: 'from-teal-600 to-teal-700',
        bg: 'bg-teal-50', border: 'border-teal-200', text: 'text-teal-700',
        badge: 'bg-teal-100 text-teal-800',
        label: 'Sandbox Approved', emoji: '✅',
    },
    CONTROLLED_SANDBOX: {
        gradient: 'from-slate-500 to-indigo-600',
        bg: 'bg-slate-50', border: 'border-slate-200', text: 'text-slate-700',
        badge: 'bg-slate-100 text-slate-800',
        label: 'Controlled Sandbox', emoji: '⚠️',
    },
    ENTERPRISE: {
        gradient: 'from-rose-600 to-rose-800',
        bg: 'bg-rose-50', border: 'border-rose-200', text: 'text-rose-700',
        badge: 'bg-rose-100 text-rose-800',
        label: 'Enterprise Build', emoji: '🔴',
    },
};

const ScoreRing = ({ score, max = 10, size = 120, stroke = 10 }) => {
    const radius = (size - stroke) / 2;
    const circumference = 2 * Math.PI * radius;
    const pct = Math.min(score / max, 1);
    const offset = circumference * (1 - pct);
    const color = score <= 3.5 ? '#0d9488' : score <= 6.5 ? '#6366f1' : '#e11d48';
    return (
        <div className="relative flex items-center justify-center" style={{ width: size, height: size }}>
            <svg width={size} height={size} className="-rotate-90">
                <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="#e5e7eb" strokeWidth={stroke} />
                <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke={color} strokeWidth={stroke}
                    strokeLinecap="round" strokeDasharray={circumference} strokeDashoffset={offset}
                    style={{ transition: 'stroke-dashoffset 1s ease-out' }} />
            </svg>
            <div className="absolute flex flex-col items-center">
                <span className="text-2xl font-extrabold text-gray-900">{score}</span>
                <span className="text-[10px] font-semibold text-gray-400 uppercase tracking-wide">/ {max}</span>
            </div>
        </div>
    );
};

const GovernanceResult = ({ result, onBack }) => {
    if (!result) {
        return <div className="text-red-700 p-6">Error: No result data available.</div>;
    }

    const {
        classification = 'UNKNOWN',
        classification_description = 'No description available',
        project_name = 'Project',
        weighted_score = 0,
        dimension_scores = {},
        recommendation = '',
        hard_stops = [],
    } = result;

    const theme = CLASSIFICATION_THEME[classification] || {
        gradient: 'from-gray-400 to-gray-500', bg: 'bg-gray-50', border: 'border-gray-200',
        text: 'text-gray-700', badge: 'bg-gray-100 text-gray-800', label: classification, emoji: '📋',
    };


    return (
        <div className="min-h-screen bg-gray-50 p-3 sm:p-4 md:p-8">
            <div className="max-w-5xl mx-auto">

                {/* ── Back link ── */}
                <button onClick={onBack} className="inline-flex items-center gap-1.5 text-sm font-semibold text-gray-500 hover:text-gray-800 mb-6 transition-colors group">
                    <ChevronLeft className="w-4 h-4 group-hover:-translate-x-0.5 transition-transform" /> Back to Form
                </button>

                {/* ══════════════════════════════════════════════
                   HERO + DIMENSION SCORES — Side by Side
                ══════════════════════════════════════════════ */}
                <div className="flex flex-col lg:flex-row gap-4 mb-6">
                    {/* LEFT: Hero Banner */}
                    <div className={`relative rounded-2xl overflow-hidden bg-gradient-to-br ${theme.gradient} text-white p-6 sm:p-8 shadow-lg flex-1`}>
                        <div className="relative z-10 flex flex-col sm:flex-row items-start sm:items-center gap-5">
                            {/* Score ring */}
                            <div className="bg-white/20 backdrop-blur-sm rounded-2xl p-3 flex-shrink-0">
                                <ScoreRing score={weighted_score} />
                            </div>

                            <div className="flex-1 min-w-0">
                                <p className="text-white/70 text-xs font-semibold uppercase tracking-widest mb-1">Governance Result</p>
                                <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight mb-1 truncate">
                                    {theme.emoji} {theme.label}
                                </h1>
                                <p className="text-white/80 text-sm mb-3 line-clamp-2">{classification_description}</p>
                                <div className="flex flex-wrap items-center gap-2">
                                    <span className="bg-white/20 backdrop-blur-sm text-white text-xs font-bold px-3 py-1 rounded-full">
                                        {project_name}
                                    </span>
                                    <span className="bg-white/20 backdrop-blur-sm text-white text-xs font-semibold px-3 py-1 rounded-full">
                                        Score: {weighted_score}/10
                                    </span>
                                    <span className="bg-white/20 backdrop-blur-sm text-white text-xs font-semibold px-3 py-1 rounded-full">
                                        {weighted_score <= 3.5 ? 'Low Governance' : weighted_score <= 6.5 ? 'Moderate Governance' : 'High Governance'}
                                    </span>
                                </div>
                            </div>
                        </div>
                        {/* decorative circles */}
                        <div className="absolute -top-10 -right-10 w-40 h-40 bg-white/5 rounded-full" />
                        <div className="absolute -bottom-8 -left-8 w-32 h-32 bg-white/5 rounded-full" />
                    </div>

                    {/* RIGHT: Dimension Pie Charts — vertical 2×3 */}
                    <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-4 sm:p-5 lg:w-[340px] xl:w-[380px] flex-shrink-0">
                        <h3 className="text-gray-900 font-bold text-sm mb-3 flex items-center gap-2">
                            📊 Dimensions
                        </h3>
                        <div className="grid grid-cols-3 gap-x-3 gap-y-4">
                            {Object.entries(dimension_scores).map(([dimension, score]) => {
                                const sz = 64, sw = 5;
                                const r = (sz - sw) / 2;
                                const circ = 2 * Math.PI * r;
                                const pct = Math.min(score / 10, 1);
                                const off = circ * (1 - pct);
                                const clr = score <= 3 ? '#0d9488' : score <= 6 ? '#6366f1' : '#e11d48';
                                return (
                                    <div key={dimension} className="flex flex-col items-center group">
                                        <div className="relative mb-1.5" style={{ width: sz, height: sz }}>
                                            <svg width={sz} height={sz} className="-rotate-90">
                                                <circle cx={sz / 2} cy={sz / 2} r={r} fill="none" stroke="#f3f4f6" strokeWidth={sw} />
                                                <circle cx={sz / 2} cy={sz / 2} r={r} fill="none" stroke={clr} strokeWidth={sw}
                                                    strokeLinecap="round" strokeDasharray={circ} strokeDashoffset={off}
                                                    style={{ transition: 'stroke-dashoffset 1s ease-out' }}
                                                    className="drop-shadow-sm" />
                                            </svg>
                                            <div className="absolute inset-0 flex flex-col items-center justify-center">
                                                <span className="text-sm font-extrabold text-gray-900">{score}</span>
                                                <span className="text-[8px] font-semibold text-gray-400">/10</span>
                                            </div>
                                        </div>
                                        <span className="text-[10px] font-semibold text-gray-500 text-center capitalize leading-tight group-hover:text-blue-600 transition-colors max-w-[90px]">
                                            {dimension.replace(/_/g, ' ')}
                                        </span>
                                    </div>
                                );
                            })}
                        </div>
                    </div>
                </div>

                {/* ── Hard Stops ── */}
                {hard_stops?.length > 0 && (
                    <div className="bg-red-50 border border-red-200 rounded-xl p-4 mb-6">
                        <h3 className="text-red-800 font-bold text-sm mb-2 flex items-center gap-2">
                            <AlertCircle className="w-4 h-4" /> Hard Stops Triggered
                        </h3>
                        <ul className="space-y-1 text-red-700 text-sm">
                            {hard_stops.map((stop, idx) => <li key={idx} className="flex gap-2"><span className="text-red-400">•</span>{stop}</li>)}
                        </ul>
                    </div>
                )}

                {/* ══════════════════════════════════════════════
                   RECOMMENDATION
                ══════════════════════════════════════════════ */}
                <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5 sm:p-6 mb-6">
                    <h3 className="text-gray-900 font-bold text-base mb-3 flex items-center gap-2">
                        💡 Recommendation
                    </h3>
                    <div className="text-gray-600 space-y-2 text-sm leading-relaxed">
                        {recommendation
                            ? recommendation.split('\n').map((line, idx) => {
                                if (line.includes('**')) {
                                    const parts = line.split(/\*\*(.*?)\*\*/g);
                                    return (
                                        <div key={idx} className="whitespace-pre-wrap">
                                            {parts.map((part, i) =>
                                                i % 2 === 1 ? <strong key={i} className="font-bold text-gray-900">{part}</strong> : part
                                            )}
                                        </div>
                                    );
                                }
                                if (line.trim().startsWith('-'))
                                    return (
                                        <div key={idx} className="ml-3 flex gap-2 items-start">
                                            <span className="text-blue-500 mt-1 flex-shrink-0">›</span>
                                            <span>{line.trim().substring(1).trim()}</span>
                                        </div>
                                    );
                                if (!line.trim()) return <div key={idx} className="h-1.5" />;
                                return <div key={idx}>{line}</div>;
                            })
                            : <p className="text-gray-400 italic">No recommendation available.</p>
                        }
                    </div>
                </div>

                {/* ══════════════════════════════════════════════
                   NEXT STEPS + RESOURCES (side-by-side cards)
                ══════════════════════════════════════════════ */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
                    {classification === 'SANDBOX' && (
                        <>
                            <div className="bg-green-50 rounded-2xl p-5 border border-green-200">
                                <h3 className="text-green-800 font-bold text-sm mb-3 flex items-center gap-2">
                                    <CheckCircle2 className="w-4 h-4" /> Auto-Provisioned Resources
                                </h3>
                                <ul className="text-gray-700 space-y-2 text-sm">
                                    <li className="flex gap-2"><span className="text-green-500">✓</span> Azure Dev Subscription</li>
                                    <li className="flex gap-2"><span className="text-green-500">✓</span> Git Repository (Ready)</li>
                                    <li className="flex gap-2"><span className="text-green-500">✓</span> App Service Template</li>
                                    <li className="flex gap-2"><span className="text-green-500">✓</span> 90-Day Auto-Review</li>
                                </ul>
                            </div>
                            <div className="bg-blue-50 rounded-2xl p-5 border border-blue-200">
                                <h3 className="text-blue-800 font-bold text-sm mb-3 flex items-center gap-2">
                                    <ArrowRight className="w-4 h-4" /> Next Steps
                                </h3>
                                <ol className="text-gray-700 space-y-2 text-sm list-none">
                                    <li className="flex gap-2"><span className="bg-blue-200 text-blue-800 rounded-full w-5 h-5 flex items-center justify-center text-[10px] font-bold flex-shrink-0">1</span> Get credentials from email</li>
                                    <li className="flex gap-2"><span className="bg-blue-200 text-blue-800 rounded-full w-5 h-5 flex items-center justify-center text-[10px] font-bold flex-shrink-0">2</span> Clone your repository</li>
                                    <li className="flex gap-2"><span className="bg-blue-200 text-blue-800 rounded-full w-5 h-5 flex items-center justify-center text-[10px] font-bold flex-shrink-0">3</span> Start development immediately</li>
                                    <li className="flex gap-2"><span className="bg-blue-200 text-blue-800 rounded-full w-5 h-5 flex items-center justify-center text-[10px] font-bold flex-shrink-0">4</span> Submit review at 90 days</li>
                                </ol>
                            </div>
                        </>
                    )}
                    {classification === 'CONTROLLED_SANDBOX' && (
                        <>
                            <div className="bg-amber-50 rounded-2xl p-5 border border-amber-200">
                                <h3 className="text-amber-800 font-bold text-sm mb-3 flex items-center gap-2">
                                    <AlertTriangle className="w-4 h-4" /> Requirements
                                </h3>
                                <ul className="text-gray-700 space-y-2 text-sm">
                                    <li className="flex gap-2"><span className="text-amber-500">•</span> Use Azure DevOps template</li>
                                    <li className="flex gap-2"><span className="text-amber-500">•</span> Use .NET scaffold</li>
                                    <li className="flex gap-2"><span className="text-amber-500">•</span> Submit for IT check</li>
                                    <li className="flex gap-2"><span className="text-amber-500">•</span> Follow CI/CD pipeline</li>
                                </ul>
                            </div>
                            <div className="bg-blue-50 rounded-2xl p-5 border border-blue-200">
                                <h3 className="text-blue-800 font-bold text-sm mb-3 flex items-center gap-2">
                                    <ArrowRight className="w-4 h-4" /> Next Steps
                                </h3>
                                <ol className="text-gray-700 space-y-2 text-sm list-none">
                                    <li className="flex gap-2"><span className="bg-blue-200 text-blue-800 rounded-full w-5 h-5 flex items-center justify-center text-[10px] font-bold flex-shrink-0">1</span> Request Azure DevOps project</li>
                                    <li className="flex gap-2"><span className="bg-blue-200 text-blue-800 rounded-full w-5 h-5 flex items-center justify-center text-[10px] font-bold flex-shrink-0">2</span> Set up standard repository</li>
                                    <li className="flex gap-2"><span className="bg-blue-200 text-blue-800 rounded-full w-5 h-5 flex items-center justify-center text-[10px] font-bold flex-shrink-0">3</span> Submit for architecture review</li>
                                    <li className="flex gap-2"><span className="bg-blue-200 text-blue-800 rounded-full w-5 h-5 flex items-center justify-center text-[10px] font-bold flex-shrink-0">4</span> Proceed after approval</li>
                                </ol>
                            </div>
                        </>
                    )}
                    {classification === 'ENTERPRISE' && (
                        <>
                            <div className="bg-red-50 rounded-2xl p-5 border border-red-200">
                                <h3 className="text-red-800 font-bold text-sm mb-3 flex items-center gap-2">
                                    <AlertCircle className="w-4 h-4" /> Required Processes
                                </h3>
                                <ul className="text-gray-700 space-y-2 text-sm">
                                    <li className="flex gap-2"><span className="text-red-400">•</span> Architecture board review</li>
                                    <li className="flex gap-2"><span className="text-red-400">•</span> Threat modeling</li>
                                    <li className="flex gap-2"><span className="text-red-400">•</span> Full security assessment</li>
                                    <li className="flex gap-2"><span className="text-red-400">•</span> SDLC compliance</li>
                                </ul>
                            </div>
                            <div className="bg-blue-50 rounded-2xl p-5 border border-blue-200">
                                <h3 className="text-blue-800 font-bold text-sm mb-3 flex items-center gap-2">
                                    <ArrowRight className="w-4 h-4" /> Next Steps
                                </h3>
                                <ol className="text-gray-700 space-y-2 text-sm list-none">
                                    <li className="flex gap-2"><span className="bg-blue-200 text-blue-800 rounded-full w-5 h-5 flex items-center justify-center text-[10px] font-bold flex-shrink-0">1</span> Contact enterprise architecture team</li>
                                    <li className="flex gap-2"><span className="bg-blue-200 text-blue-800 rounded-full w-5 h-5 flex items-center justify-center text-[10px] font-bold flex-shrink-0">2</span> Prepare threat model documentation</li>
                                    <li className="flex gap-2"><span className="bg-blue-200 text-blue-800 rounded-full w-5 h-5 flex items-center justify-center text-[10px] font-bold flex-shrink-0">3</span> Schedule architecture board review</li>
                                    <li className="flex gap-2"><span className="bg-blue-200 text-blue-800 rounded-full w-5 h-5 flex items-center justify-center text-[10px] font-bold flex-shrink-0">4</span> Complete security assessment</li>
                                </ol>
                            </div>
                        </>
                    )}
                </div>

                {/* ══════════════════════════════════════════════
                   ACTION BUTTONS
                ══════════════════════════════════════════════ */}
                <div className="flex flex-col sm:flex-row gap-3 pb-8">
                    <button
                        onClick={onBack}
                        className="inline-flex items-center justify-center gap-2 py-3 px-6 text-sm font-semibold rounded-xl text-gray-600 bg-white border border-gray-200 hover:bg-gray-50 transition-all active:scale-[0.97] shadow-sm"
                    >
                        <ChevronLeft className="w-4 h-4" /> Back to Form
                    </button>
                    {classification !== 'ENTERPRISE' && (
                        <button
                            onClick={() => {
                                sessionStorage.setItem('governanceResult', JSON.stringify(result));
                                window.location.href = '/dashboard?tab=upload&governance=' + result.id;
                            }}
                            className="inline-flex items-center justify-center gap-2 flex-1 py-3 px-6 text-sm font-bold rounded-xl text-white bg-blue-600 hover:bg-blue-700 transition-all active:scale-[0.97] shadow-md"
                        >
                            <ArrowRight className="w-4 h-4" /> Proceed to Upload BRD
                        </button>
                    )}
                    <button
                        onClick={() => {
                            if (window.confirm('Are you sure you want to reset your governance assessment? All answers will be cleared.')) {
                                localStorage.removeItem('governanceResult');
                                localStorage.removeItem('governanceContext');
                                localStorage.removeItem('governancePassed');
                                sessionStorage.removeItem('governanceResult');
                                sessionStorage.removeItem('governanceContext');
                                window.location.reload();
                            }
                        }}
                        className="inline-flex items-center justify-center gap-2 py-3 px-6 text-sm font-semibold rounded-xl text-orange-700 bg-orange-50 border border-orange-200 hover:bg-orange-100 transition-all active:scale-[0.97]"
                    >
                        Reset Assessment
                    </button>
                </div>
            </div>
        </div>
    );
};

export default GovernanceForm;
