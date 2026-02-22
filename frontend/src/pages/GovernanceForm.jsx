import { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
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
            <div className="flex flex-col w-full relative">
                {/* Vertical connecting line */}
                <div className="absolute left-[15px] top-4 bottom-4 w-[2px] bg-gradient-to-b from-blue-200 via-gray-200 to-gray-100 rounded-full" />
                <div className="space-y-0.5">
                    {steps.map((step, idx) => {
                        const done = idx < currentStep;
                        const active = idx === currentStep;
                        return (
                            <div key={step} className={`flex items-center gap-3.5 py-2.5 px-2 rounded-xl cursor-default transition-all duration-300 group
                                ${active ? 'bg-gradient-to-r from-blue-50 to-indigo-50/60' : 'hover:bg-gray-50/60'}`}
                            >
                                {/* Indicator Circle */}
                                <div className={`relative z-10 flex items-center justify-center w-8 h-8 rounded-full text-xs font-bold transition-all duration-300 flex-shrink-0
                                    ${done ? 'bg-gradient-to-br from-blue-500 to-indigo-600 text-white shadow-md shadow-blue-200'
                                        : active ? 'bg-white border-2 border-blue-500 text-blue-600 shadow-lg shadow-blue-100 ring-4 ring-blue-50'
                                            : 'bg-gray-100 border border-gray-200 text-gray-400 group-hover:border-gray-300 group-hover:text-gray-500'}`}
                                >
                                    {done ? <Check className="w-3.5 h-3.5" /> : idx + 1}
                                    {active && <span className="absolute inset-0 rounded-full animate-ping bg-blue-400/20" />}
                                </div>
                                {/* Label */}
                                <div className="flex flex-col min-w-0">
                                    <span className={`text-[10px] font-bold uppercase tracking-widest transition-colors duration-200
                                        ${active ? 'text-blue-600' : done ? 'text-blue-500/70' : 'text-gray-400'}`}
                                    >
                                        Step {idx + 1}
                                    </span>
                                    <span className={`text-[13px] font-semibold transition-colors duration-200 truncate
                                        ${active ? 'text-gray-900' : done ? 'text-gray-600' : 'text-gray-400'}`}
                                    >
                                        {step}
                                    </span>
                                </div>
                                {done && <Check className="w-3.5 h-3.5 text-blue-500/60 ml-auto flex-shrink-0" />}
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
            <div className="flex items-center justify-between text-xs mb-2.5">
                <span className="font-bold text-transparent bg-clip-text bg-gradient-to-r from-blue-600 to-indigo-600">Step {currentStep + 1} of {steps.length}</span>
                <span className="text-gray-600 font-semibold truncate ml-2">{steps[currentStep]}</span>
            </div>
            <div className="w-full bg-gray-100 rounded-full h-2.5 overflow-hidden shadow-inner">
                <div
                    className="bg-gradient-to-r from-blue-500 via-indigo-500 to-blue-600 h-full rounded-full transition-all duration-500 ease-out relative overflow-hidden"
                    style={{ width: `${((currentStep + 1) / steps.length) * 100}%` }}
                >
                    <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/30 to-transparent animate-pulse" />
                </div>
            </div>
        </div>
    );
};

/* ─────────────────────────────────────────────────────────
   MAIN FORM COMPONENT
───────────────────────────────────────────────────────── */
const GovernanceForm = () => {
    const navigate = useNavigate();
    const location = useLocation();
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

        const params = new URLSearchParams(location.search);
        const nameFromUrl = params.get('projectName');
        const isNew = params.get('new');

        if (isNew) {
            setProjectName('');
            setAnswers({});
            setCurrentStep(0);
            setResult(null);
            navigate(location.pathname, { replace: true });
            return;
        }

        if (nameFromUrl) {
            setProjectName(decodeURIComponent(nameFromUrl));
            setCurrentStep(1); // Skip Project Name step
            // Also store it so it persists on reload
            sessionStorage.setItem('governanceContext', JSON.stringify({ project_name: decodeURIComponent(nameFromUrl) }));
            // Clean up the URL
            navigate(location.pathname, { replace: true });
        }

        const savedContext = getStoredJson('governanceContext');
        if (savedContext && !nameFromUrl) {
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
    }, [location.search, location.pathname, navigate]);

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

            // ==========================================
            // Generate Project Automatically Using External API
            // ==========================================
            try {
                // 1. Fetch dynamic Token
                const tokenRes = await fetch(API_ENDPOINTS.TASK_TOKEN, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        client_id: import.meta.env.VITE_TASK_API_CLIENT_ID || "org_1_596a6282",
                        client_secret: import.meta.env.VITE_TASK_API_CLIENT_SECRET || "voxtdGRCbutV0qHfRQD_Ky1yd9HeCpMuOFKxeUnYB0E"
                    })
                });

                if (tokenRes.ok) {
                    const tokenData = await tokenRes.json();
                    const taskToken = tokenData.access;

                    // Fetch agents to assign as the team
                    let teamIds = [];
                    try {
                        const agentsUrl = API_ENDPOINTS.TASK_TOKEN.replace('token/task/', 'agents/');
                        const agentsRes = await fetch(agentsUrl, {
                            method: 'GET',
                            headers: {
                                'Content-Type': 'application/json',
                                Authorization: `Bearer ${token}`,
                                'x-task-token': taskToken,
                            }
                        });
                        if (agentsRes.ok) {
                            const agentsData = await agentsRes.json();
                            if (Array.isArray(agentsData) && agentsData.length > 0) {
                                teamIds = agentsData.map(a => a.user_id || a.id).filter(Boolean);
                            } else if (agentsData.results && Array.isArray(agentsData.results)) {
                                teamIds = agentsData.results.map(a => a.user_id || a.id).filter(Boolean);
                            }
                        }
                    } catch (err) {
                        console.error("Failed to fetch team members:", err);
                    }

                    // 2. Create the Project
                    // Provide defaults for team and deadline
                    const projectCreationUrl = `${API_ENDPOINTS.AGENT_PROJECT_INFO.replace('project-info/', 'projects/')}`;

                    const projectDeadline = new Date();
                    projectDeadline.setFullYear(projectDeadline.getFullYear() + 1);

                    await fetch(projectCreationUrl, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            Authorization: `Bearer ${token}`,
                            'x-task-token': taskToken,
                        },
                        body: JSON.stringify({
                            name: projectName,
                            deadline: projectDeadline.toISOString().split('T')[0],
                            project_wallet: 1000,
                            team: teamIds.length > 0 ? teamIds : [24],
                            project_token: resultData.project_token
                        }),
                    });
                } else {
                    console.error("Failed to fetch task API token for project creation.");
                }
            } catch (projErr) {
                console.error("Project generation error:", projErr);
                // We choose not to block the UI if project creation fails, just log it.
            }

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
            <div className="flex items-center justify-center min-h-screen bg-gradient-to-br from-slate-50 via-gray-50 to-blue-50/30">
                <div className="flex flex-col items-center gap-5">
                    <div className="relative">
                        <div className="w-14 h-14 border-4 border-blue-100 border-t-blue-600 rounded-full animate-spin" />
                        <div className="absolute inset-0 w-14 h-14 border-4 border-transparent border-b-indigo-400 rounded-full animate-spin" style={{ animationDirection: 'reverse', animationDuration: '1.5s' }} />
                    </div>
                    <p className="text-gray-500 font-semibold text-sm tracking-wide">Loading governance questionnaire…</p>
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
        <div className="h-full overflow-y-auto bg-gradient-to-br from-slate-50 via-gray-50 to-blue-50/30">

            {/* ── MAIN AREA ── */}
            <div className="px-3 sm:px-4 lg:px-6 py-4 lg:py-6 max-w-[1440px] mx-auto">

                {/* Page header — premium */}
                {/* <div className="flex items-start justify-between gap-3 mb-5"> */}
                <div>
                    {/* <div className="flex items-center gap-3 mb-1">
                            <div className="w-1 h-8 rounded-full bg-gradient-to-b from-blue-500 to-indigo-600" />
                            <h1 className="text-xl sm:text-2xl lg:text-3xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-gray-900 via-gray-800 to-gray-700 tracking-tight">
                                Governance Questionnaire
                            </h1>
                        </div> */}
                    {/* <p className="text-gray-400 text-sm mt-0.5 ml-4">
                            <span className="inline-flex items-center gap-1.5">
                                <span className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse" />
                                {questions.length} questions · {dimensions.length} dimensions
                            </span>
                        </p> */}
                </div>
                {/* </div> */}

                {/* ── Roadmap / Timeline Header ── */}
                <RoadmapHeader steps={stepLabels} currentStep={currentStep} />

                <div className="flex gap-5 items-start">

                    {/* ── DESKTOP SIDEBAR (≥1024px) ── */}
                    <aside className="hidden lg:block w-64 xl:w-72 flex-shrink-0 sticky top-6 self-start">
                        <div className="bg-white/80 backdrop-blur-xl rounded-2xl shadow-lg shadow-gray-200/50 border border-white/60 p-5 relative overflow-hidden">
                            {/* Decorative gradient accent */}
                            <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-blue-500 via-indigo-500 to-purple-500 rounded-t-2xl" />
                            <h2 className="text-[10px] font-bold uppercase tracking-[0.15em] text-gray-400 mb-5 mt-1 flex items-center gap-2">
                                <span className="w-4 h-[2px] bg-gradient-to-r from-blue-400 to-indigo-400 rounded-full" />
                                Progress
                            </h2>
                            <StepIndicator steps={stepLabels} currentStep={currentStep} vertical={true} />
                        </div>
                    </aside>

                    {/* ── MAIN CONTENT: Step Wizard ── */}
                    <div className="flex-1 min-w-0 max-w-4xl">
                        {/* Error banner */}
                        {error && (
                            <div className="rounded-xl bg-red-50/80 backdrop-blur-sm p-4 border border-red-200/60 text-red-700 mb-5 flex items-start gap-3 shadow-sm">
                                <div className="w-8 h-8 rounded-lg bg-red-100 flex items-center justify-center flex-shrink-0">
                                    <AlertCircle className="w-4 h-4 text-red-500" />
                                </div>
                                <div className="text-sm font-medium pt-1">{error}</div>
                            </div>
                        )}

                        {/* Mobile Step indicator (horizontal) */}
                        <div className="lg:hidden">
                            <StepIndicator steps={stepLabels} currentStep={currentStep} />
                        </div>

                        {/* Wrapper: fixed min-height so nav buttons stay at a consistent position */}
                        <div className="flex flex-col min-h-[calc(100vh-14rem)]">
                            {/* Step card */}
                            <div className="bg-white/90 backdrop-blur-xl rounded-2xl shadow-lg shadow-gray-200/40 border border-white/60 overflow-hidden relative">
                                {/* Top gradient accent line */}
                                <div className="absolute top-0 left-0 right-0 h-[3px] bg-gradient-to-r from-blue-500 via-indigo-500 to-purple-500" />

                                {/* ── STEP 0: Project Name ── */}
                                {currentStep === 0 && (
                                    <div className="p-6 sm:p-8">
                                        <div className="mb-6">
                                            <h2 className="text-xl font-bold text-gray-900 mb-1.5 tracking-tight">Project Details</h2>
                                            <p className="text-gray-400 text-sm leading-relaxed">Give your project a descriptive name to get started.</p>
                                        </div>
                                        <label className="block text-[11px] font-bold text-gray-500 mb-2 uppercase tracking-widest">
                                            Project Name <span className="text-red-400">*</span>
                                        </label>
                                        <div className="relative group">
                                            <input
                                                type="text"
                                                value={projectName}
                                                onChange={(e) => setProjectName(e.target.value)}
                                                onKeyDown={(e) => e.key === 'Enter' && goNext()}
                                                placeholder="e.g. Customer Analytics Platform"
                                                className="w-full px-4 py-3 border-2 border-gray-200 rounded-xl focus:ring-4 focus:ring-blue-100 focus:border-blue-400 text-sm bg-gray-50/50 text-gray-900 transition-all duration-200 placeholder:text-gray-300 hover:border-gray-300 font-medium"
                                            />
                                            <div className="absolute inset-y-0 right-3 flex items-center pointer-events-none opacity-0 group-focus-within:opacity-100 transition-opacity">
                                                <div className="w-2 h-2 rounded-full bg-blue-400 animate-pulse" />
                                            </div>
                                        </div>
                                        <p className="text-[11px] text-gray-400 mt-2 ml-1">This name will be used to identify your governance assessment.</p>
                                    </div>
                                )}

                                {/* ── STEP 1…N: Dimension questions ── */}
                                {isDimensionStep && (
                                    <div className="p-6 sm:p-8">
                                        {/* Dimension header */}
                                        <div className="mb-6">
                                            <div className="flex items-center gap-3 mb-1.5">
                                                <h2 className="text-xl font-bold text-gray-900 tracking-tight">{activeDimension}</h2>
                                                <span className="text-[11px] text-blue-600 bg-blue-50 px-2.5 py-1 rounded-full font-bold border border-blue-100">
                                                    {activeQuestions.filter((q) => answers[q.id] !== undefined).length}/{activeQuestions.length}
                                                </span>
                                            </div>
                                            {/* mini progress bar */}
                                            <div className="w-full bg-gray-100 rounded-full h-1.5 mt-2 overflow-hidden">
                                                <div
                                                    className="bg-gradient-to-r from-blue-500 to-indigo-500 h-1.5 rounded-full transition-all duration-500 ease-out"
                                                    style={{ width: `${(activeQuestions.filter((q) => answers[q.id] !== undefined).length / activeQuestions.length) * 100}%` }}
                                                />
                                            </div>
                                        </div>

                                        {/* Questions */}
                                        <div className="space-y-4">
                                            {activeQuestions.map((question, qIdx) => {
                                                const answered = answers[question.id] !== undefined;
                                                return (
                                                    <div
                                                        key={question.id}
                                                        className={`rounded-xl border-2 p-5 transition-all duration-300 hover:shadow-md ${answered
                                                            ? 'border-blue-200/80 bg-gradient-to-br from-blue-50/40 to-indigo-50/30 shadow-sm'
                                                            : 'border-gray-200/80 bg-white hover:border-gray-300'}`}
                                                    >
                                                        <div className="flex items-start gap-3 mb-4">
                                                            <span className={`flex-shrink-0 w-7 h-7 rounded-lg flex items-center justify-center text-[11px] font-bold transition-all duration-300 ${answered
                                                                ? 'bg-gradient-to-br from-blue-500 to-indigo-600 text-white shadow-md shadow-blue-200'
                                                                : 'bg-gray-100 text-gray-500 border border-gray-200'}`}
                                                            >
                                                                {answered ? <Check className="w-3.5 h-3.5" /> : qIdx + 1}
                                                            </span>
                                                            <h3 className="text-gray-800 font-semibold text-sm leading-relaxed pt-0.5">{question.question}</h3>
                                                        </div>

                                                        {/* Options — 2 cols on wider screens */}
                                                        <div className="ml-10 grid grid-cols-1 sm:grid-cols-2 gap-2">
                                                            {question.options.map((option) => {
                                                                const selected = answers[question.id] === option.score;
                                                                return (
                                                                    <label
                                                                        key={option.label}
                                                                        className={`flex items-center gap-2.5 cursor-pointer rounded-xl px-3.5 py-2.5 border-2 text-sm transition-all duration-200 group ${selected
                                                                            ? 'border-blue-400 bg-blue-50/70 text-blue-900 font-semibold shadow-sm shadow-blue-100'
                                                                            : 'border-gray-150 bg-gray-50/50 text-gray-600 hover:border-blue-200 hover:bg-blue-50/30 hover:text-gray-800'}`}
                                                                    >
                                                                        <input
                                                                            type="radio"
                                                                            name={`question-${question.id}`}
                                                                            value={option.score}
                                                                            checked={selected}
                                                                            onChange={() => handleAnswer(question.id, option.score)}
                                                                            className="sr-only"
                                                                        />
                                                                        {/* Custom radio indicator */}
                                                                        <span className={`flex-shrink-0 w-4 h-4 rounded-full border-2 flex items-center justify-center transition-all duration-200 ${selected
                                                                            ? 'border-blue-500 bg-blue-500' : 'border-gray-300 bg-white group-hover:border-blue-300'}`}
                                                                        >
                                                                            {selected && <span className="w-1.5 h-1.5 rounded-full bg-white" />}
                                                                        </span>
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
                                    <div className="p-6 sm:p-8">
                                        <div className="mb-6">
                                            <h2 className="text-xl font-bold text-gray-900 mb-1.5 tracking-tight">Review & Submit</h2>
                                            <p className="text-gray-400 text-sm leading-relaxed">Verify your answers, then submit for scoring.</p>
                                        </div>

                                        {/* Summary grid */}
                                        <div className="space-y-2 mb-6">
                                            <div className="rounded-xl border-2 border-gray-200/60 bg-gradient-to-r from-gray-50 to-slate-50 px-5 py-3.5">
                                                <p className="text-[10px] font-bold uppercase tracking-widest text-gray-400 mb-0.5">Project</p>
                                                <p className="text-gray-900 font-bold text-sm">{projectName}</p>
                                            </div>

                                            {dimensions.map((dim, idx) => {
                                                const qs = questionsByDimension[dim];
                                                const allDone = qs.every((q) => answers[q.id] !== undefined);
                                                const answered = qs.filter((q) => answers[q.id] !== undefined).length;
                                                return (
                                                    <div
                                                        key={dim}
                                                        className={`rounded-xl border-2 px-5 py-3.5 flex items-center gap-3 transition-all duration-200 ${allDone
                                                            ? 'border-emerald-200/60 bg-gradient-to-r from-emerald-50/40 to-green-50/30'
                                                            : 'border-red-200/60 bg-gradient-to-r from-red-50/40 to-rose-50/30'}`}
                                                    >
                                                        <div className={`w-6 h-6 rounded-lg flex items-center justify-center flex-shrink-0 ${allDone
                                                            ? 'bg-gradient-to-br from-emerald-400 to-green-500 text-white shadow-sm shadow-emerald-200'
                                                            : 'bg-gradient-to-br from-red-400 to-rose-500 text-white shadow-sm shadow-red-200'}`}
                                                        >
                                                            {allDone ? <Check className="w-3 h-3" /> : <AlertCircle className="w-3 h-3" />}
                                                        </div>
                                                        <div className="flex-1 min-w-0">
                                                            <p className="text-sm font-semibold text-gray-800 truncate">{dim}</p>
                                                            <p className="text-[11px] text-gray-500 font-medium">{answered}/{qs.length} answered</p>
                                                        </div>
                                                        {!allDone && (
                                                            <button type="button" onClick={() => { setError(''); setCurrentStep(idx + 1); }}
                                                                className="text-[11px] text-blue-600 font-bold hover:text-blue-700 flex-shrink-0 bg-blue-50 px-3 py-1 rounded-lg border border-blue-100 hover:border-blue-200 transition-all"
                                                            >Fix →</button>
                                                        )}
                                                    </div>
                                                );
                                            })}
                                        </div>

                                        <button
                                            type="button"
                                            onClick={handleSubmit}
                                            disabled={submitting || Object.keys(answers).length !== questions.length}
                                            className="w-full inline-flex items-center justify-center py-3.5 px-6 text-sm font-bold rounded-xl text-white bg-gradient-to-r from-blue-600 via-indigo-600 to-blue-700 hover:from-blue-700 hover:via-indigo-700 hover:to-blue-800 disabled:from-gray-300 disabled:to-gray-400 disabled:cursor-not-allowed transition-all active:scale-[0.98] shadow-lg shadow-blue-200/50 gap-2"
                                        >
                                            <Send className="w-4 h-4" />
                                            {submitting ? 'Submitting…' : 'Submit & Score'}
                                        </button>
                                    </div>
                                )}
                            </div>
                            {/* end of step card */}

                            {/* ── NAV BUTTONS ── */}
                            <div className="flex items-center justify-end gap-3 mt-auto pt-5 px-1">
                                {currentStep === 0 ? (
                                    <button type="button" onClick={() => navigate('/dashboard')}
                                        className="inline-flex items-center gap-1.5 py-2.5 px-5 text-sm font-semibold rounded-xl text-gray-500 bg-white/80 backdrop-blur-sm border border-gray-200/60 hover:bg-white hover:border-gray-300 transition-all shadow-sm"
                                    >
                                        <ChevronLeft className="w-4 h-4" /> Dashboard
                                    </button>
                                ) : (
                                    <button type="button" onClick={goPrev}
                                        className="inline-flex items-center gap-1.5 py-2.5 px-5 text-sm font-semibold rounded-xl text-gray-500 bg-white/80 backdrop-blur-sm border border-gray-200/60 hover:bg-white hover:border-gray-300 transition-all shadow-sm"
                                    >
                                        <ChevronLeft className="w-4 h-4" /> Back
                                    </button>
                                )}

                                {!isReviewStep && (
                                    <button
                                        type="button"
                                        onClick={goNext}
                                        disabled={!canProceed()}
                                        className={`inline-flex items-center gap-1.5 py-2.5 px-6 text-sm font-bold rounded-xl text-white transition-all shadow-md ${canProceed()
                                            ? 'bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 active:scale-[0.97] shadow-blue-200/50'
                                            : 'bg-gray-300 cursor-not-allowed shadow-none'
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
        <div className="h-full overflow-y-auto min-h-screen bg-gray-50 p-3 sm:p-4 md:p-8 pb-24 md:pb-32">
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
                <div className="flex flex-col sm:flex-row gap-3 pb-12 md:pb-24">
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
                                window.location.href = `/a/${result.project_token}`;
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
