import { useState, useEffect, useMemo } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { API_ENDPOINTS } from '../config';
import { customConfirm } from '../utils/modalHelpers';
import { Send, AlertCircle, CheckCircle2, AlertTriangle, ChevronRight, ChevronLeft, ArrowRight, Check, Loader2 } from 'lucide-react';
import { useGovernanceQuestions, useSubmitGovernance } from '../hooks/useGovernance';
import colors from '../styles/colors';
import { createDraftProject, getDraftProject, upsertDraftProject } from '../utils/draftProjects';
/* ─────────────────────────────────────────────────────────
   STEP INDICATOR  (compact, responsive)
───────────────────────────────────────────────────────── */
/* ─────────────────────────────────────────────────────────
   STEP INDICATOR  (responsive: vertical on desktop, horizontal on mobile)
   Now accepts a `vertical` prop to switch layout modes.
───────────────────────────────────────────────────────── */
const StepIndicator = ({ steps, currentStep, vertical = false, startStepNumber = 1, totalSteps = null }) => {
    // ── VERTICAL LAYOUT (Desktop Sidebar) ──
    if (vertical) {
        return (
            <div className="flex flex-col w-full relative">
                {/* Vertical connecting line */}
                <div className="absolute left-[15px] top-4 bottom-4 w-[2px] bg-gradient-to-b from-app-primary-ring via-app-bg-hover to-app-bg-muted rounded-full" />
                <div className="space-y-0.5">
                    {steps.map((step, idx) => {
                        const done = idx < currentStep;
                        const active = idx === currentStep;
                        return (
                            <div key={step} className={`flex items-center gap-3.5 py-2.5 px-2 rounded-xl cursor-default transition-all duration-300 group
                                ${active ? 'bg-gradient-to-r from-app-primary-light to-app-primary-light/60' : 'hover:bg-app-bg-page/60'}`}
                            >
                                {/* Indicator Circle */}
                                <div className={`relative z-10 flex items-center justify-center w-8 h-8 rounded-full text-xs font-bold transition-all duration-300 flex-shrink-0
                                    ${done ? 'bg-gradient-to-br from-app-primary to-app-primary text-white shadow-md shadow-app-primary-ring'
                                        : active ? 'bg-app-bg-card border-2 border-app-primary text-app-primary shadow-lg shadow-app-primary-light ring-4 ring-app-primary-light'
                                            : 'bg-app-bg-muted border border-app-border text-app-text-light group-hover:border-app-border group-hover:text-app-text-muted'}`}
                                >
                                    {done ? <Check className="w-3.5 h-3.5" /> : startStepNumber + idx}
                                    {active && <span className="absolute inset-0 rounded-full animate-ping bg-blue-400/20" />}
                                </div>
                                {/* Label */}
                                <div className="flex flex-col min-w-0">
                                    <span className={`text-[10px] font-bold uppercase tracking-widest transition-colors duration-200
                                        ${active ? 'text-app-primary' : done ? 'text-app-primary/70' : 'text-app-text-light'}`}
                                    >
                                        Step {startStepNumber + idx}
                                    </span>
                                    <span className={`text-[13px] font-semibold transition-colors duration-200 truncate
                                        ${active ? 'text-app-text-main' : done ? 'text-app-text-label' : 'text-app-text-light'}`}
                                    >
                                        {step}
                                    </span>
                                </div>
                                {done && <Check className="w-3.5 h-3.5 text-app-primary/60 ml-auto flex-shrink-0" />}
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
                <span className="font-bold text-transparent bg-clip-text bg-gradient-to-r from-app-primary to-app-primary">
                    Step {startStepNumber + currentStep} of {totalSteps || steps.length}
                </span>
                <span className="text-app-text-label font-semibold truncate ml-2">{steps[currentStep]}</span>
            </div>
            <div className="w-full bg-app-bg-muted rounded-full h-2.5 overflow-hidden shadow-inner">
                <div
                    className="bg-gradient-to-r from-app-primary via-app-primary to-app-primary h-full rounded-full transition-all duration-500 ease-out relative overflow-hidden"
                    style={{ width: `${((currentStep + 1) / steps.length) * 100}%` }}
                >
                    <div className="absolute inset-0 bg-gradient-to-r from-transparent via-app-bg-card/30 to-transparent animate-pulse" />
                </div>
            </div>
        </div>
    );
};

/* ─────────────────────────────────────────────────────────
   MAIN FORM COMPONENT
───────────────────────────────────────────────────────── */
const GovernanceForm = ({
    fetchRoadmapData,
    selectedProjectKey,
    setSelectedProjectKey,
    setIsNewProjectMode,
    fetchHistory,
    projects = [],
}) => {
    const navigate = useNavigate();
    const location = useLocation();
    const queryClient = useQueryClient();
    const { data: questionsData, isLoading: loading, error: queryError } = useGovernanceQuestions();
    const { mutate: submitGovernance, isPending: submitting } = useSubmitGovernance();
    const isGovernanceQuestionsPage = location.pathname.endsWith('/governance');
    const initiationPath = '/new-project';
    const projectStorageKey = 'status_dashboard_selected_project_key';
    // CRITICAL: Always get fresh draft project on every render to ensure we have latest credentials
    const persistedDraftProject = getDraftProject(selectedProjectKey);
    const selectedProject = useMemo(() => {
        const projectFromList = projects.find((project) => project.key === selectedProjectKey) || null;
        if (!projectFromList) return persistedDraftProject || null;
        if (!persistedDraftProject) return projectFromList;

        // CRITICAL: Always check draft project FIRST for credentials (most reliable source before governance submission)
        const draftClientId = persistedDraftProject?.client_id || null;
        const draftClientSecret = persistedDraftProject?.client_secret || null;
        const backendClientId = projectFromList.client_id || null;
        const backendClientSecret = projectFromList.client_secret || null;

        // Prioritize backend credentials if they exist, otherwise use draft credentials
        const finalClientId = (backendClientId && backendClientId.trim()) ? backendClientId : draftClientId;
        const finalClientSecret = (backendClientSecret && backendClientSecret.trim()) ? backendClientSecret : draftClientSecret;

        return {
            ...persistedDraftProject,
            ...projectFromList,
            // CRITICAL: Explicitly preserve credentials - NEVER allow null to overwrite existing credentials
            client_id: finalClientId,
            client_secret: finalClientSecret,
            documents: projectFromList.documents?.length ? projectFromList.documents : persistedDraftProject.documents,
            latestRevision: projectFromList.latestRevision || persistedDraftProject.latestRevision,
            status: projectFromList.status === 'analysis_complete' || persistedDraftProject.status === 'analysis_complete'
                ? 'analysis_complete'
                : projectFromList.status,
        };
    }, [selectedProjectKey, projects, persistedDraftProject]);
    const hasExistingAnalysis = Boolean(
        selectedProject?.status === 'analysis_complete'
    );

    const questions = questionsData?.questions || [];

    const [answers, setAnswers] = useState({});
    const [projectName, setProjectName] = useState('');
    const [error, setError] = useState('');
    const [result, setResult] = useState(null);
    const [isHydrated, setIsHydrated] = useState(false);
    const [isCreatingProject, setIsCreatingProject] = useState(false);
    const skipOption = { label: 'Skip', score: 0 };

    // Step state: 0 = Project Name page, 1…N = dimension steps, N+1 = review
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
        const params = new URLSearchParams(location.search);
        const nameFromUrl = params.get('projectName');
        const isNew = params.get('new');
        const draftProject = getDraftProject(selectedProjectKey) || selectedProject || null;
        const currentProjectName = String(draftProject?.name || '').trim();
        const matchesCurrentProject = (payload) => {
            if (!payload || typeof payload !== 'object') return false;

            const payloadToken = String(payload.project_token || '').trim();
            if (selectedProjectKey && payloadToken) {
                return payloadToken === String(selectedProjectKey);
            }

            const payloadName = String(payload.project_name || '').trim().toLowerCase();
            return Boolean(payloadName && currentProjectName && payloadName === currentProjectName.toLowerCase());
        };

        setTimeout(() => {
            if (isNew) {
                setProjectName('');
                setAnswers({});
                setCurrentStep(0);
                setResult(null);
                sessionStorage.removeItem('governance_wizard_step_new');
                navigate(initiationPath, { replace: true });
                setIsHydrated(true);
                return;
            }

            if (nameFromUrl) {
                setProjectName(decodeURIComponent(nameFromUrl));
                setCurrentStep(0);
                // Also store it so it persists on reload
                sessionStorage.setItem('governanceContext', JSON.stringify({ project_name: decodeURIComponent(nameFromUrl) }));
                // Clean up the URL
                navigate(location.pathname, { replace: true });
            }

            const savedContext = getStoredJson('governanceContext');
            if (savedContext && !nameFromUrl && matchesCurrentProject(savedContext)) {
                if (savedContext.project_name) setProjectName(savedContext.project_name);
                if (Array.isArray(savedContext.answers)) {
                    const r = {};
                    savedContext.answers.forEach((a) => {
                        if (a?.question_id !== undefined && a?.score !== undefined)
                            r[a.question_id] = { score: a.score, label: a.selected_option };
                    });
                    setAnswers(r);
                }
            }
            if (!nameFromUrl && currentProjectName) {
                setProjectName(currentProjectName);
            }

            // Check if user is in edit mode (went back from result page to edit)
            const isEditMode = sessionStorage.getItem('governanceEditMode') === 'true';

            const savedResult = getStoredJson('governanceResult');
            // Don't restore result if user is in edit mode (they want to edit the form)
            if (savedResult && matchesCurrentProject(savedResult) && !isEditMode) {
                setResult(savedResult);
            } else {
                setResult(null);
                // Clear edit mode flag after checking
                if (isEditMode) {
                    sessionStorage.removeItem('governanceEditMode');
                }
            }

            const storageKey = selectedProjectKey ? `governance_wizard_step_${selectedProjectKey}` : 'governance_wizard_step_new';
            let persistedStep = 0;
            try {
                const rawStep = sessionStorage.getItem(storageKey);
                if (rawStep) {
                    const parsedStep = JSON.parse(rawStep);
                    if (parsedStep && typeof parsedStep.step === 'number') {
                        persistedStep = parsedStep.step;
                    }
                }
            } catch {
                persistedStep = 0;
            }

            if (isGovernanceQuestionsPage) {
                setCurrentStep(Math.max(1, persistedStep || 1));
            } else {
                setCurrentStep(0);
            }
            setIsHydrated(true);
        }, 0);
    }, [location.search, location.pathname, navigate, isGovernanceQuestionsPage, selectedProjectKey, selectedProject]);

    // Persist current wizard step so the global tracker can highlight
    // Project Initiation vs Governance appropriately while filling the form.
    useEffect(() => {
        try {
            const storageKey = selectedProjectKey ? `governance_wizard_step_${selectedProjectKey}` : 'governance_wizard_step_new';
            const payload = { projectKey: selectedProjectKey || 'new', step: currentStep };
            sessionStorage.setItem(storageKey, JSON.stringify(payload));
        } catch {
            // ignore storage errors
        }
    }, [currentStep, selectedProjectKey]);

    useEffect(() => {
        if (queryError) {
            setTimeout(() => {
                setError(prev => prev || `Failed to load screening questions: ${queryError.message}`);
            }, 0);
        }
    }, [queryError]);

    useEffect(() => {
        if (!isHydrated) return;
        if (!isGovernanceQuestionsPage) return;
        if (projectName.trim()) return;
        navigate(initiationPath, { replace: true });
    }, [isHydrated, isGovernanceQuestionsPage, projectName, navigate]);

    const handleAnswer = (questionId, option) =>
        setAnswers((prev) => ({ ...prev, [questionId]: option }));

    const getQuestionOptions = (question) => {
        if (question.options.some((option) => option.label === skipOption.label)) {
            return question.options;
        }
        return [...question.options, skipOption];
    };

    /* ── submit ── */
    const handleSubmit = (e) => {
        e?.preventDefault();

        if (!projectName.trim()) { setError('Please enter a project name'); return; }
        if (Object.keys(answers).length !== questions.length) {
            setError('Please answer all questions before submitting');
            return;
        }

        setError('');

        const formattedAnswers = questions.map((q) => ({
            question_id: q.id,
            question: q.question,
            dimension: q.dimension,
            score: answers[q.id]?.score ?? 0,
            selected_option: answers[q.id]?.label || '',
        }));
        const allSkipped = formattedAnswers.every(
            (a) => (a.selected_option || '').toLowerCase() === skipOption.label.toLowerCase()
        );

        const submission = {
            project_name: projectName,
            answers: formattedAnswers.map((a) => ({
                question_id: a.question_id,
                score: a.score,
                selected_option: a.selected_option,
            })),
            project_token: selectedProject?.projectToken || selectedProjectKey || undefined,
            client_id: selectedProject?.client_id || undefined,
            client_secret: selectedProject?.client_secret || undefined,
        };

        submitGovernance(submission, {
            onSuccess: (resultData) => {
                try {
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
                    // Clear edit mode flag when submitting (new submission)
                    sessionStorage.removeItem('governanceEditMode');
                    setResult(normalizedResultData);

                    // Preserve existing credentials from draft project - don't overwrite with null
                    const existingDraft = getDraftProject(resultData.project_token || selectedProjectKey);
                    const existingClientId = existingDraft?.client_id || selectedProject?.client_id;
                    const existingClientSecret = existingDraft?.client_secret || selectedProject?.client_secret;

                    upsertDraftProject({
                        key: resultData.project_token || selectedProjectKey,
                        name: projectName,
                        // Preserve existing credentials, only use new ones if they exist from backend
                        client_id: resultData.client_id || existingClientId || null,
                        client_secret: resultData.client_secret || existingClientSecret || null,
                    });
                    if (resultData.project_token) {
                        setSelectedProjectKey?.(String(resultData.project_token));
                    }
                    setIsNewProjectMode?.(false);
                    fetchHistory?.();

                    // DO NOT auto-refresh roadmap here - it causes AppLayout to navigate away before user sees result
                    // Roadmap will be refreshed when user clicks "Proceed to Agent Analysis" button
                    // This ensures the GovernanceResult component renders and user can review their score

                    // If all questions were skipped (score 5), do NOT navigate - user should see the sandbox score
                    // Navigation is blocked in AppLayout.jsx for this case
                } catch (err) {
                    setError('Submission data processing error: ' + err.message);
                }
            },
            onError: (err) => {
                setError('Submission error: ' + err.message);
            }
        });
    };

    /* ── loading / result screens ── */
    if (loading) {
        return (
            <div className="flex items-center justify-center min-h-screen bg-gradient-to-br from-app-bg-page via-app-bg-page to-app-primary-light/30">
                <div className="flex flex-col items-center gap-5">
                    <div className="relative">
                        <div className="w-14 h-14 border-4 border-app-primary-light border-t-blue-600 rounded-full animate-spin" />
                        <div className="absolute inset-0 w-14 h-14 border-4 border-transparent border-b-indigo-400 rounded-full animate-spin" style={{ animationDirection: 'reverse', animationDuration: '1.5s' }} />
                    </div>
                    <p className="text-app-text-muted font-semibold text-sm tracking-wide">Loading screening questionnaire…</p>
                </div>
            </div>
        );
    }

    if (result) {
        return <GovernanceResult 
            result={result} 
            fetchRoadmapData={fetchRoadmapData}
            navigate={navigate}
            onBack={() => {
                setResult(null);
                // Clear stored result so it doesn't get restored by useEffect
                sessionStorage.removeItem('governanceResult');
                localStorage.removeItem('governanceResult');
                // Set flag to indicate user wants to edit (prevents result restoration)
                sessionStorage.setItem('governanceEditMode', 'true');
                // Also clear governanceContext result_id to allow re-editing
                const savedContext = getStoredJson('governanceContext');
                if (savedContext && savedContext.result_id) {
                    const updatedContext = { ...savedContext };
                    delete updatedContext.result_id;
                    sessionStorage.setItem('governanceContext', JSON.stringify(updatedContext));
                    localStorage.setItem('governanceContext', JSON.stringify(updatedContext));
                }
            }} 
        />;
    }

    /* ── build dimension list ── */
    const questionsByDimension = {};
    questions.forEach((q) => {
        if (!questionsByDimension[q.dimension]) questionsByDimension[q.dimension] = [];
        questionsByDimension[q.dimension].push(q);
    });
    const dimensions = Object.keys(questionsByDimension);

    // Cross-page flow:
    // /new-project -> Project Initiation only
    // /new-project/governance -> Governance questionnaire after Requirement Screening
    const TOTAL_STEPS = dimensions.length + 2;
    const governanceStepLabels = [...dimensions.map((d) => d.split(' ')[0]), 'Review'];
    const sidebarStepLabels = isGovernanceQuestionsPage ? governanceStepLabels : ['Project Initiation'];
    const sidebarCurrentStep = isGovernanceQuestionsPage ? Math.max(currentStep - 1, 0) : 0;
    // Start numbering from 1 on the Governance wizard sidebar.
    // (User-facing "Step 1" should be Business when on /new-project/governance)
    const sidebarStepOffset = 1;
    const isDimensionStep = isGovernanceQuestionsPage && currentStep >= 1 && currentStep <= dimensions.length;
    const isReviewStep = isGovernanceQuestionsPage && currentStep === dimensions.length + 1;
    const activeDimension = isDimensionStep ? dimensions[currentStep - 1] : null;
    const activeQuestions = activeDimension ? questionsByDimension[activeDimension] : [];



    const canProceed = () => {
        if (!isGovernanceQuestionsPage) return projectName.trim().length > 0;
        if (isDimensionStep) return activeQuestions.every((q) => answers[q.id] !== undefined);
        return true;
    };

    const continueToScreening = async () => {
        setIsCreatingProject(true);
        setError('');

        try {
            // Validate project name
            const trimmedName = projectName.trim();
            if (!trimmedName) {
                setError('Please enter a project name');
                setIsCreatingProject(false);
                return;
            }

            // CRITICAL FIX: Synchronize project with backend BEFORE navigation
            // This prevents duplicate project creation by ensuring backend knows about the project
            
            const projectKeyToUse = selectedProject?.projectToken || selectedProjectKey || undefined;
            const existingDraft = getDraftProject(projectKeyToUse);

            // Preserve existing credentials from draft project (most reliable source)
            const existingClientId = existingDraft?.client_id || selectedProject?.client_id;
            const existingClientSecret = existingDraft?.client_secret || selectedProject?.client_secret;

            // Call backend to ensure project exists (creates if needed, returns existing if found)
            const response = await fetch(API_ENDPOINTS.PROJECT_ENSURE, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    Authorization: `Bearer ${localStorage.getItem('token')}`
                },
                body: JSON.stringify({
                    project_token: projectKeyToUse,
                    project_name: trimmedName,
                    client_id: existingClientId || null,
                    client_secret: existingClientSecret || null,
                })
            });

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                
                // Handle duplicate name error specifically
                if (response.status === 409) {
                    setError(errorData.detail || 'A project with this name already exists. Please choose a different name.');
                    setIsCreatingProject(false);
                    return;
                }
                
                throw new Error(errorData.detail || 'Failed to create project in backend');
            }

            const backendProject = await response.json();
            
            // Update draft project with backend-confirmed token and credentials
            const draftProject = upsertDraftProject(createDraftProject(trimmedName, {
                key: backendProject.project_token,
                client_id: backendProject.client_id || null,
                client_secret: backendProject.client_secret || null,
            }));

            if (!draftProject?.projectToken) {
                setError('Unable to create the project. Please try again.');
                setIsCreatingProject(false);
                return;
            }

            // Wait a bit to ensure credentials are saved before navigation
            await new Promise(resolve => setTimeout(resolve, 100));

            try {
                localStorage.setItem(projectStorageKey, draftProject.key);
            } catch {
                // Ignore storage access errors in restricted browser contexts.
            }

            setSelectedProjectKey?.(draftProject.key);
            setIsNewProjectMode?.(false);

            // Set a flag to tell AppLayout to skip its automatic redirect during this navigation.
            try {
                sessionStorage.setItem('skipAppLayoutRedirect', 'true');
            } catch (e) {
                // ignore storage errors (e.g., in private mode)
            }

            const nextStepPath = '/dashboard';
            navigate(nextStepPath, { replace: true });

            // Fallback navigation in case the SPA router does not update the URL promptly.
            window.setTimeout(() => {
                if (window.location.pathname !== nextStepPath) {
                    window.location.assign(nextStepPath);
                }
            }, 0);
        } catch (err) {
            console.error('Project creation error:', err);
            setError(err.message || 'Failed to create project. Please try again.');
            setIsCreatingProject(false);
        }
    };

    const goNext = () => {
        if (!canProceed()) {
            if (!isGovernanceQuestionsPage || currentStep === 0) setError('Please enter a project name before continuing.');
            else setError('Please answer all questions in this section before continuing.');
            return;
        }
        setError('');
        if (!isGovernanceQuestionsPage) {
            continueToScreening();
            return;
        }
        setCurrentStep((s) => Math.min(s + 1, TOTAL_STEPS - 1));
    };

    const goPrev = () => {
        setError('');
        if (!isGovernanceQuestionsPage) {
            setCurrentStep(0);
            return;
        }
        if (currentStep <= 1) {
            navigate(initiationPath);
            return;
        }
        setCurrentStep((s) => Math.max(s - 1, 1));
    };

    // Skip all unanswered questions in the current dimension step
    const handleSkipAll = () => {
        if (!isDimensionStep) return;
        const newAnswers = { ...answers };
        activeQuestions.forEach((q) => {
            newAnswers[q.id] = skipOption;
        });
        setAnswers(newAnswers);
    };

    /* ── render ── */
    const mainContentClass = isGovernanceQuestionsPage
        ? 'flex-1 min-w-0 max-w-4xl'
        : 'flex-1 min-w-0 w-full';

    return (
        <div className="h-full overflow-y-auto bg-gradient-to-br from-app-bg-page via-app-bg-page to-app-primary-light/30">

            {/* ── MAIN AREA ── */}
            <div className="px-3 sm:px-4 lg:px-6 py-4 lg:py-6 max-w-[1440px] mx-auto">

                {/* Page header — premium */}
                {/* <div className="flex items-start justify-between gap-3 mb-5"> */}
                <div>
                    {/* <div className="flex items-center gap-3 mb-1">
                            <div className="w-1 h-8 rounded-full bg-gradient-to-b from-app-primary to-app-primary" />
                            <h1 className="text-xl sm:text-2xl lg:text-3xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-app-text-main via-app-text-main to-app-text-label tracking-tight">
                                Governance Questionnaire
                            </h1>
                        </div> */}
                    {/* <p className="text-app-text-light text-sm mt-0.5 ml-4">
                            <span className="inline-flex items-center gap-1.5">
                                <span className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse" />
                                {questions.length} questions · {dimensions.length} dimensions
                            </span>
                        </p> */}
                </div>
                {/* </div> */}



                <div className="flex gap-5 items-start">

                    {/* ── DESKTOP SIDEBAR (≥1024px) ── */}
                    {isGovernanceQuestionsPage && (
                        <aside className="hidden lg:block w-64 xl:w-72 flex-shrink-0 sticky top-6 self-start">
                            <div className="bg-app-bg-card/80 backdrop-blur-xl rounded-2xl shadow-lg shadow-app-bg-hover/50 border border-app-bg-card/60 p-5 relative overflow-hidden">
                                {/* Decorative gradient accent */}
                                <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-app-primary via-app-primary to-purple-500 rounded-t-2xl" />
                                <h2 className="text-[10px] font-bold uppercase tracking-[0.15em] text-app-text-light mb-5 mt-1 flex items-center gap-2">
                                    <span className="w-4 h-[2px] bg-gradient-to-r from-blue-400 to-indigo-400 rounded-full" />
                                    Progress
                                </h2>
                                <StepIndicator
                                    steps={sidebarStepLabels}
                                    currentStep={sidebarCurrentStep}
                                    vertical={true}
                                    startStepNumber={sidebarStepOffset}
                                    totalSteps={TOTAL_STEPS}
                                />
                            </div>
                        </aside>
                    )}

                    {/* ── MAIN CONTENT: Step Wizard ── */}
                    <div className={mainContentClass}>
                        {/* Error banner */}
                        {error && (
                            <div className="rounded-xl bg-app-status-errorBg/80 backdrop-blur-sm p-4 border border-red-200/60 text-app-status-error mb-5 flex items-start gap-3 shadow-sm">
                                <div className="w-8 h-8 rounded-lg bg-app-status-errorBg flex items-center justify-center flex-shrink-0">
                                    <AlertCircle className="w-4 h-4 text-app-status-error" />
                                </div>
                                <div className="text-sm font-medium pt-1">{error}</div>
                            </div>
                        )}

                        {/* Mobile Step indicator (horizontal) */}
                        {isGovernanceQuestionsPage && (
                            <div className="lg:hidden">
                                <StepIndicator
                                    steps={sidebarStepLabels}
                                    currentStep={sidebarCurrentStep}
                                    startStepNumber={sidebarStepOffset}
                                    totalSteps={TOTAL_STEPS}
                                />
                            </div>
                        )}

                        {/* Wrapper: fixed min-height so nav buttons stay at a consistent position */}
                        <div className="flex flex-col min-h-[calc(100vh-14rem)]">
                            {/* Step card */}
                            <div className="bg-app-bg-card/90 backdrop-blur-xl rounded-2xl shadow-lg shadow-app-bg-hover/40 border border-app-bg-card/60 overflow-hidden relative">
                                {/* Top gradient accent line */}
                                <div className="absolute top-0 left-0 right-0 h-[3px] bg-gradient-to-r from-app-primary via-app-primary to-purple-500" />

                                {/* ── STEP 0: Project Name ── */}
                                {!isGovernanceQuestionsPage && (
                                    <div className="p-6 sm:p-8">
                                        <div className="mb-6">
                                            <h2 className="text-xl font-bold text-app-text-main mb-1.5 tracking-tight">Project Details</h2>
                                            <p className="text-app-text-light text-sm leading-relaxed">Give your project a descriptive name to get started.</p>
                                        </div>
                                        <label className="block text-[11px] font-bold text-app-text-muted mb-2 uppercase tracking-widest">
                                            Project Name <span className="text-red-400">*</span>
                                        </label>
                                        <div className="relative group">
                                            <input
                                                type="text"
                                                value={projectName}
                                                onChange={(e) => {
                                                    setProjectName(e.target.value);
                                                    // Clear error when user starts typing
                                                    if (error && error.includes('already exists')) {
                                                        setError('');
                                                    }
                                                }}
                                                onKeyDown={(e) => e.key === 'Enter' && goNext()}
                                                placeholder="e.g. Customer Analytics Platform"
                                                className="w-full px-4 py-3 border-2 border-app-border rounded-xl focus:ring-4 focus:ring-app-primary-light focus:border-blue-400 text-sm bg-app-bg-page/50 text-app-text-main transition-all duration-200 placeholder:text-app-border hover:border-app-border font-medium"
                                            />
                                            <div className="absolute inset-y-0 right-3 flex items-center pointer-events-none opacity-0 group-focus-within:opacity-100 transition-opacity">
                                                <div className="w-2 h-2 rounded-full bg-blue-400 animate-pulse" />
                                            </div>
                                        </div>
                                        <p className="text-[11px] text-app-text-light mt-2 ml-1">This name will be used to identify your screening assessment.</p>
                                    </div>
                                )}

                                {/* ── STEP 1…N: Dimension questions ── */}
                                {isDimensionStep && (
                                    <div className="p-6 sm:p-8">
                                        {/* Dimension header */}
                                        <div className="mb-6">
                                            <div className="flex items-center gap-3 mb-1.5">
                                                <h2 className="text-xl font-bold text-app-text-main tracking-tight">{activeDimension}</h2>
                                                <span className="text-[11px] text-app-primary bg-app-primary-light px-2.5 py-1 rounded-full font-bold border border-app-primary-light">
                                                    {activeQuestions.filter((q) => answers[q.id] !== undefined).length}/{activeQuestions.length}
                                                </span>
                                            </div>
                                            {/* mini progress bar */}
                                            <div className="w-full bg-app-bg-muted rounded-full h-1.5 mt-2 overflow-hidden">
                                                <div
                                                    className="bg-gradient-to-r from-app-primary to-app-primary h-1.5 rounded-full transition-all duration-500 ease-out"
                                                    style={{ width: `${(activeQuestions.filter((q) => answers[q.id] !== undefined).length / activeQuestions.length) * 100}%` }}
                                                />
                                            </div>
                                        </div>

                                        {/* Questions */}
                                        <div className="space-y-4">
                                            {activeQuestions.map((question, qIdx) => {
                                                const answered = answers[question.id] !== undefined;
                                                const allOptions = getQuestionOptions(question);
                                                const mainOptions = allOptions.filter((opt) => opt.label !== skipOption.label);
                                                const skip = allOptions.find((opt) => opt.label === skipOption.label);
                                                const isSkipped = answers[question.id]?.label === skipOption.label;

                                                return (
                                                    <div
                                                        key={question.id}
                                                        className={`rounded-xl border-2 p-5 transition-all duration-300 hover:shadow-md ${answered
                                                            ? 'border-app-primary-ring/80 bg-gradient-to-br from-app-primary-light/40 to-app-primary-light/30 shadow-sm'
                                                            : 'border-app-border/80 bg-app-bg-card hover:border-app-border'}`}
                                                    >
                                                        <div className="flex items-start justify-between gap-3 mb-4">
                                                            <div className="flex items-start gap-3">
                                                                <span className={`flex-shrink-0 w-7 h-7 rounded-lg flex items-center justify-center text-[11px] font-bold transition-all duration-300 ${answered
                                                                    ? 'bg-gradient-to-br from-app-primary to-app-primary text-app-bg-card shadow-md shadow-app-primary-ring'
                                                                    : 'bg-app-bg-muted text-app-text-muted border border-app-border'}`}
                                                                >
                                                                    {answered ? <Check className="w-3.5 h-3.5" /> : qIdx + 1}
                                                                </span>
                                                                <h3 className="text-app-text-main font-semibold text-sm leading-relaxed pt-0.5 max-w-xl">
                                                                    {question.question}
                                                                </h3>
                                                            </div>
                                                            {skip && (
                                                                <button
                                                                    type="button"
                                                                    onClick={() => handleAnswer(question.id, skip)}
                                                                    className={`text-[11px] font-semibold rounded-full px-3 py-1 border transition-colors duration-200 whitespace-nowrap ${isSkipped
                                                                        ? 'border-blue-400 bg-app-primary-light text-app-primary-dark'
                                                                        : 'border-transparent text-app-text-light hover:text-app-primary hover:border-app-primary-light hover:bg-app-primary-light/20'
                                                                        }`}
                                                                >
                                                                    Skip
                                                                </button>
                                                            )}
                                                        </div>

                                                        {/* Options — 2 cols on wider screens (excluding Skip) */}
                                                        <div className="ml-10 grid grid-cols-1 sm:grid-cols-2 gap-2">
                                                            {mainOptions.map((option) => {
                                                                const selected = answers[question.id]?.label === option.label;
                                                                return (
                                                                    <label
                                                                        key={option.label}
                                                                        className={`flex items-center gap-2.5 cursor-pointer rounded-xl px-3.5 py-2.5 border-2 text-sm transition-all duration-200 group ${selected
                                                                            ? 'border-blue-400 bg-app-primary-light/70 text-app-primary-dark font-semibold shadow-sm shadow-app-primary-light'
                                                                            : 'border-gray-150 bg-app-bg-page/50 text-app-text-label hover:border-app-primary-ring hover:bg-app-primary-light/30 hover:text-app-text-main'}`}
                                                                    >
                                                                        <input
                                                                            type="radio"
                                                                            name={`question-${question.id}`}
                                                                            value={option.score}
                                                                            checked={selected}
                                                                            onChange={() => handleAnswer(question.id, option)}
                                                                            className="sr-only"
                                                                        />
                                                                        {/* Custom radio indicator */}
                                                                        <span className={`flex-shrink-0 w-4 h-4 rounded-full border-2 flex items-center justify-center transition-all duration-200 ${selected
                                                                            ? 'border-app-primary bg-app-primary' : 'border-app-border bg-app-bg-card group-hover:border-blue-300'}`}
                                                                        >
                                                                            {selected && <span className="w-1.5 h-1.5 rounded-full bg-app-bg-card" />}
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
                                            <h2 className="text-xl font-bold text-app-text-main mb-1.5 tracking-tight">Review & Submit</h2>
                                            <p className="text-app-text-light text-sm leading-relaxed">Verify your answers, then submit for scoring.</p>
                                        </div>

                                        {/* Summary grid */}
                                        <div className="space-y-2 mb-6">
                                            <div className="rounded-xl border-2 border-app-border/60 bg-gradient-to-r from-app-bg-page to-app-bg-page px-5 py-3.5">
                                                <p className="text-[10px] font-bold uppercase tracking-widest text-app-text-light mb-0.5">Project</p>
                                                <p className="text-app-text-main font-bold text-sm">{projectName}</p>
                                            </div>

                                            {dimensions.map((dim, idx) => {
                                                const qs = questionsByDimension[dim];
                                                const allDone = qs.every((q) => answers[q.id] !== undefined);
                                                const answered = qs.filter((q) => answers[q.id] !== undefined).length;
                                                return (
                                                    <div
                                                        key={dim}
                                                        className={`rounded-xl border-2 px-5 py-3.5 flex items-center gap-3 transition-all duration-200 ${allDone
                                                            ? 'border-emerald-200/60 bg-gradient-to-r from-app-status-successBg/40 to-app-status-successBg/30'
                                                            : 'border-red-200/60 bg-gradient-to-r from-app-status-errorBg/40 to-app-status-errorBg/30'}`}
                                                    >
                                                        <div className={`w-6 h-6 rounded-lg flex items-center justify-center flex-shrink-0 ${allDone
                                                            ? 'bg-gradient-to-br from-emerald-400 to-app-status-success text-app-bg-card shadow-sm shadow-emerald-200'
                                                            : 'bg-gradient-to-br from-red-400 to-app-status-error text-app-bg-card shadow-sm shadow-red-200'}`}
                                                        >
                                                            {allDone ? <Check className="w-3 h-3" /> : <AlertCircle className="w-3 h-3" />}
                                                        </div>
                                                        <div className="flex-1 min-w-0">
                                                            <p className="text-sm font-semibold text-app-text-main truncate">{dim}</p>
                                                            <p className="text-[11px] text-app-text-muted font-medium">{answered}/{qs.length} answered</p>
                                                        </div>
                                                        {!allDone && (
                                                            <button type="button" onClick={() => { setError(''); setCurrentStep(idx + 1); }}
                                                                className="text-[11px] text-app-primary font-bold hover:text-app-primary-hover flex-shrink-0 bg-app-primary-light px-3 py-1 rounded-lg border border-app-primary-light hover:border-app-primary-ring transition-all"
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
                                            className="w-full inline-flex items-center justify-center py-3.5 px-6 text-sm font-bold rounded-xl text-app-bg-card bg-gradient-to-r from-app-primary via-app-primary to-app-primary-hover hover:from-app-primary-hover hover:via-app-primary-hover hover:to-app-primary-dark disabled:from-app-border disabled:to-app-text-light disabled:cursor-not-allowed transition-all active:scale-[0.98] shadow-lg shadow-app-primary-ring/50 gap-2"
                                        >
                                            <Send className="w-4 h-4" />
                                            {submitting ? 'Submitting…' : 'Submit & Score'}
                                        </button>
                                    </div>
                                )}
                            </div>
                            {/* end of step card */}

                            {/* ── NAV BUTTONS ── */}
                            <div className="flex items-center justify-between gap-3 mt-auto pt-5 px-1">
                                {!isGovernanceQuestionsPage ? (
                                    <button type="button" onClick={() => navigate('/dashboard')}
                                        className="inline-flex items-center gap-1.5 py-2.5 px-5 text-sm font-semibold rounded-xl text-app-text-muted bg-app-bg-card/80 backdrop-blur-sm border border-app-border/60 hover:bg-app-bg-card hover:border-app-border transition-all shadow-sm"
                                    >
                                        <ChevronLeft className="w-4 h-4" /> Dashboard
                                    </button>
                                ) : (
                                    <button type="button" onClick={goPrev}
                                        className="inline-flex items-center gap-1.5 py-2.5 px-5 text-sm font-semibold rounded-xl text-app-text-muted bg-app-bg-card/80 backdrop-blur-sm border border-app-border/60 hover:bg-app-bg-card hover:border-app-border transition-all shadow-sm"
                                    >
                                        <ChevronLeft className="w-4 h-4" /> Back
                                    </button>
                                )}

    <div className="flex items-center gap-3">
        {isDimensionStep && (
            <button type="button" onClick={handleSkipAll}
                className="inline-flex items-center gap-1.5 py-2.5 px-5 text-sm font-semibold rounded-xl text-app-primary bg-app-primary-light border border-app-primary-light hover:bg-app-primary-light/80 transition-all shadow-sm"
            >
                Skip All
            </button>
        )}
        {!isReviewStep && (
            <button
                type="button"
                onClick={goNext}
                disabled={!canProceed() || isCreatingProject}
                className={`inline-flex items-center gap-1.5 py-2.5 px-6 text-sm font-bold rounded-xl text-white transition-all shadow-md ${canProceed() && !isCreatingProject
                    ? 'bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 active:scale-[0.97] shadow-blue-200/50'
                    : 'bg-gray-300 cursor-not-allowed shadow-none'
                    }`}
            >
                {isCreatingProject ? (
                    <>
                        <Loader2 className="w-4 h-4 animate-spin" />
                        <span>Creating Project...</span>
                    </>
                ) : (
                    <>
                        {!isGovernanceQuestionsPage ? 'Continue to Screening' : currentStep === dimensions.length ? 'Review' : 'Next'}
                        <ChevronRight className="w-4 h-4" />
                    </>
                )}
            </button>
        )}
    </div>
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
        gradient: 'from-app-text-muted to-app-primary',
        bg: 'bg-app-bg-page', border: 'border-app-border', text: 'text-app-text-label',
        badge: 'bg-app-bg-muted text-app-text-main',
        label: 'Controlled Sandbox', emoji: '⚠️',
    },
    ENTERPRISE: {
        gradient: 'from-app-status-error to-rose-800',
        bg: 'bg-app-status-errorBg', border: 'border-rose-200', text: 'text-app-status-error',
        badge: 'bg-app-status-errorBg text-rose-800',
        label: 'Enterprise Build', emoji: '🔴',
    },
};

const ScoreRing = ({ score, max = 10, size = 120, stroke = 10 }) => {
    const radius = (size - stroke) / 2;
    const circumference = 2 * Math.PI * radius;
    const pct = Math.min(score / max, 1);
    const offset = circumference * (1 - pct);
    const color = score <= 3.5 ? colors.status.lowRisk : score <= 6.5 ? colors.status.mediumRisk : colors.status.highRisk;
    return (
        <div className="relative flex items-center justify-center" style={{ width: size, height: size }}>
            <svg width={size} height={size} className="-rotate-90">
                <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke={colors.border.DEFAULT} strokeWidth={stroke} />
                <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke={color} strokeWidth={stroke}
                    strokeLinecap="round" strokeDasharray={circumference} strokeDashoffset={offset}
                    style={{ transition: 'stroke-dashoffset 1s ease-out' }} />
            </svg>
            <div className="absolute flex flex-col items-center">
                <span className="text-2xl font-extrabold text-app-text-main">{score}</span>
                <span className="text-[10px] font-semibold text-app-text-light uppercase tracking-wide">/ {max}</span>
            </div>
        </div>
    );
};

const GovernanceResult = ({ result, onBack, fetchRoadmapData, navigate }) => {
    const [isNavigating, setIsNavigating] = useState(false);

    if (!result) {
        return <div className="text-app-status-error p-6">Error: No result data available.</div>;
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
        gradient: 'from-app-text-light to-app-text-muted', bg: 'bg-app-bg-page', border: 'border-app-border',
        text: 'text-app-text-label', badge: 'bg-app-bg-muted text-app-text-main', label: classification, emoji: '📋',
    };
    const isSkipFollowUpCase =
        classification === 'ENTERPRISE' &&
        String(classification_description || '').toLowerCase().includes('our it team will reach out to you');


    return (
        <div className="h-full overflow-y-auto min-h-screen bg-app-bg-page p-3 sm:p-4 md:p-8 pb-24 md:pb-32">
            <div className="max-w-5xl mx-auto">

                {/* ── Back link ── */}
                <button onClick={onBack} className="inline-flex items-center gap-1.5 text-sm font-semibold text-app-text-muted hover:text-app-text-main mb-6 transition-colors group">
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
                            <div className="bg-app-bg-card/20 backdrop-blur-sm rounded-2xl p-3 flex-shrink-0">
                                <ScoreRing score={weighted_score} />
                            </div>

                            <div className="flex-1 min-w-0">
                                <p className="text-white/70 text-xs font-semibold uppercase tracking-widest mb-1">Governance Result</p>
                                <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight mb-1 truncate">
                                    {theme.emoji} {theme.label}
                                </h1>
                                <p className="text-white/80 text-sm mb-3 line-clamp-2">{classification_description}</p>
                                <div className="flex flex-wrap items-center gap-2">
                                    <span className="bg-app-bg-card/20 backdrop-blur-sm text-white text-xs font-bold px-3 py-1 rounded-full">
                                        {project_name}
                                    </span>
                                    <span className="bg-app-bg-card/20 backdrop-blur-sm text-white text-xs font-semibold px-3 py-1 rounded-full">
                                        Score: {weighted_score}/10
                                    </span>
                                    <span className="bg-app-bg-card/20 backdrop-blur-sm text-white text-xs font-semibold px-3 py-1 rounded-full">
                                        {weighted_score <= 3.5 ? 'Low Governance' : weighted_score <= 6.5 ? 'Moderate Governance' : 'High Governance'}
                                    </span>
                                </div>
                            </div>
                        </div>
                        {/* decorative circles */}
                        <div className="absolute -top-10 -right-10 w-40 h-40 bg-app-bg-card/5 rounded-full" />
                        <div className="absolute -bottom-8 -left-8 w-32 h-32 bg-app-bg-card/5 rounded-full" />
                    </div>

                    {/* RIGHT: Dimension Pie Charts — vertical 2×3 */}
                    <div className="bg-app-bg-card rounded-2xl shadow-sm border border-app-border-light p-4 sm:p-5 lg:w-[340px] xl:w-[380px] flex-shrink-0">
                        <h3 className="text-app-text-main font-bold text-sm mb-3 flex items-center gap-2">
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
                                                <span className="text-sm font-extrabold text-app-text-main">{score}</span>
                                                <span className="text-[8px] font-semibold text-app-text-light">/10</span>
                                            </div>
                                        </div>
                                        <span className="text-[10px] font-semibold text-app-text-muted text-center capitalize leading-tight group-hover:text-app-primary transition-colors max-w-[90px]">
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
                    <div className="bg-app-status-errorBg border border-red-200 rounded-xl p-4 mb-6">
                        <h3 className="text-red-800 font-bold text-sm mb-2 flex items-center gap-2">
                            <AlertCircle className="w-4 h-4" /> Hard Stops Triggered
                        </h3>
                        <ul className="space-y-1 text-app-status-error text-sm">
                            {hard_stops.map((stop, idx) => <li key={idx} className="flex gap-2"><span className="text-red-400">•</span>{stop}</li>)}
                        </ul>
                    </div>
                )}


                {/* ══════════════════════════════════════════════
                   ACTION BUTTONS
                ══════════════════════════════════════════════ */}
                <div className="flex flex-col sm:flex-row gap-3 pb-12 md:pb-24">
                    <button
                        onClick={onBack}
                        className="inline-flex items-center justify-center gap-2 py-3 px-6 text-sm font-semibold rounded-xl text-app-text-label bg-app-bg-card border border-app-border hover:bg-app-bg-page transition-all active:scale-[0.97] shadow-sm"
                    >
                        <ChevronLeft className="w-4 h-4" /> Back to Form
                    </button>
                    {(classification !== 'ENTERPRISE' || !isSkipFollowUpCase) && (
                        <button
                            onClick={async () => {
                                if (isNavigating) return; // Prevent double-clicks
                                
                                setIsNavigating(true);
                                
                                try {
                                    // CRITICAL FIX: Ensure project token is properly set before navigation
                                    // This prevents duplicate project creation
                                    
                                    // 1. Store result in session storage
                                    sessionStorage.setItem('governanceResult', JSON.stringify(result));
                                    sessionStorage.setItem('shouldStartAnalysis', 'true');
                                    
                                    // 2. Ensure project token is set in localStorage
                                    if (result.project_token) {
                                        localStorage.setItem('status_dashboard_selected_project_key', result.project_token);
                                    }
                                    
                                    // 3. Try to refresh roadmap data with timeout
                                    if (fetchRoadmapData && result.project_token) {
                                        try {
                                            // Race between fetch and timeout (max 3 seconds)
                                            await Promise.race([
                                                fetchRoadmapData(result.project_token),
                                                new Promise((_, reject) => 
                                                    setTimeout(() => reject(new Error('Roadmap fetch timeout')), 3000)
                                                )
                                            ]);
                                        } catch (fetchError) {
                                            console.warn('Roadmap fetch failed or timed out, continuing anyway:', fetchError);
                                            // Continue to navigation even if fetch fails
                                        }
                                    }
                                    
                                    // 4. Use React Router navigation with project token in URL
                                    // This ensures the token is available even after page reload
                                    const targetUrl = result.project_token 
                                        ? `/agent-analysis?project=${result.project_token}`
                                        : '/agent-analysis';
                                    
                                    navigate(targetUrl, {
                                        replace: false,
                                        state: {
                                            projectToken: result.project_token,
                                            shouldStartAnalysis: true
                                        }
                                    });
                                    
                                } catch (error) {
                                    console.error('Error during navigation:', error);
                                    setIsNavigating(false);
                                    // Show error to user instead of forcing navigation
                                    alert('Failed to navigate to Agent Analysis. Please try again.');
                                }
                            }}
                            disabled={isNavigating}
                            className={`inline-flex items-center justify-center gap-2 flex-1 py-3 px-6 text-sm font-bold rounded-xl text-white transition-all shadow-md ${
                                isNavigating 
                                    ? 'bg-app-primary/70 cursor-not-allowed' 
                                    : 'bg-app-primary hover:bg-app-primary-hover active:scale-[0.97]'
                            }`}
                        >
                            {isNavigating ? (
                                <>
                                    <Loader2 className="w-4 h-4 animate-spin" /> Loading...
                                </>
                            ) : (
                                <>
                                    <ArrowRight className="w-4 h-4" /> Proceed to Agent Analysis
                                </>
                            )}
                        </button>
                    )}
                    {isSkipFollowUpCase && (
                        <div className="inline-flex items-center justify-center gap-2 flex-1 py-3 px-6 text-sm font-semibold rounded-xl text-amber-800 bg-app-status-warningBg border border-amber-200">
                            <AlertCircle className="w-4 h-4" /> Sandbox score: {weighted_score}/10 - IT team will reach out
                        </div>
                    )}
                    {!isSkipFollowUpCase && (
                        <button
                            onClick={async () => {
                                const confirmed = await customConfirm('Are you sure you want to reset your screening assessment? All answers will be cleared.');
                                if (confirmed) {
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
                    )}
                </div>
            </div>
        </div>
    );
};

export default GovernanceForm;
