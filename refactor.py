import re

with open('frontend/src/pages/Dashboard.jsx', 'r') as f:
    content = f.read()

# Replace useStates
state_decls = """    const [files, setFiles] = useState([]);
    const [textInput, setTextInput] = useState('');
    const [activeTab, setActiveTab] = useState('upload'); // 'upload' or 'text'
    const [processing, setProcessing] = useState(false);
    const [result, setResult] = useState(null);
    const [error, setError] = useState('');
    const [aiConfig, setAiConfig] = useState({
        apiUrl: '',
        apiKey: '',
        model: ''
    });
    const [analyzeWithAi] = useState(true);
    const navigate = useNavigate();

    const [streamResponse] = useState(true);
    const [userFeedback, setUserFeedback] = useState(''); // Raw feedback string
    const [aiQuestions, setAiQuestions] = useState([]);   // Structured questions
    const [userAnswers, setUserAnswers] = useState({});   // Map: index -> answer

    const [history, setHistory] = useState([]);
    const [governanceHistory, setGovernanceHistory] = useState([]);
    const [projects, setProjects] = useState([]);
    const [selectedProjectKey, setSelectedProjectKey] = useState('');
    const [revisionUnlocked, setRevisionUnlocked] = useState(false);
    const [revisionReason, setRevisionReason] = useState('');
    const [showSettings, setShowSettings] = useState(false);
    const [progress, setProgress] = useState(0);
    const [progressMessage, setProgressMessage] = useState('');"""

new_state_decls = """    const [aiConfig, setAiConfig] = useState({
        apiUrl: '',
        apiKey: '',
        model: ''
    });
    const [analyzeWithAi] = useState(true);
    const navigate = useNavigate();

    const [streamResponse] = useState(true);

    const [history, setHistory] = useState([]);
    const [governanceHistory, setGovernanceHistory] = useState([]);
    const [projects, setProjects] = useState([]);
    const [selectedProjectKey, setSelectedProjectKey] = useState('');
    const [showSettings, setShowSettings] = useState(false);

    // -- Per-Project State Management --
    const [projectStates, setProjectStates] = useState({});

    const getProjectState = (key) => projectStates[key] || {
        files: [], textInput: '', activeTab: 'upload', processing: false,
        result: null, error: '', userFeedback: '', aiQuestions: [],
        userAnswers: {}, revisionUnlocked: false, revisionReason: '',
        progress: 0, progressMessage: ''
    };

    const setProjectState = (key, updater) => {
        setProjectStates(prev => {
            const current = prev[key] || getProjectState(key);
            const next = typeof updater === 'function' ? updater(current) : { ...current, ...updater };
            return { ...prev, [key]: next };
        });
    };

    const activeState = getProjectState(selectedProjectKey);
    const {
        files, textInput, activeTab, processing, result, error,
        userFeedback, aiQuestions, userAnswers, revisionUnlocked,
        revisionReason, progress, progressMessage
    } = activeState;

    // Helpers to update active project state from UI components natively 
    const setFiles = (v) => setProjectState(selectedProjectKey, { files: typeof v === 'function' ? v(activeState.files) : v });
    const setTextInput = (v) => setProjectState(selectedProjectKey, { textInput: typeof v === 'function' ? v(activeState.textInput) : v });
    const setActiveTab = (v) => setProjectState(selectedProjectKey, { activeTab: typeof v === 'function' ? v(activeState.activeTab) : v });
    const setProcessing = (v) => setProjectState(selectedProjectKey, { processing: typeof v === 'function' ? v(activeState.processing) : v });
    const setResult = (v) => setProjectState(selectedProjectKey, { result: typeof v === 'function' ? v(activeState.result) : v });
    const setError = (v) => setProjectState(selectedProjectKey, { error: typeof v === 'function' ? v(activeState.error) : v });
    const setUserFeedback = (v) => setProjectState(selectedProjectKey, { userFeedback: typeof v === 'function' ? v(activeState.userFeedback) : v });
    const setAiQuestions = (v) => setProjectState(selectedProjectKey, { aiQuestions: typeof v === 'function' ? v(activeState.aiQuestions) : v });
    const setUserAnswers = (v) => setProjectState(selectedProjectKey, { userAnswers: typeof v === 'function' ? v(activeState.userAnswers) : v });
    const setRevisionUnlocked = (v) => setProjectState(selectedProjectKey, { revisionUnlocked: typeof v === 'function' ? v(activeState.revisionUnlocked) : v });
    const setRevisionReason = (v) => setProjectState(selectedProjectKey, { revisionReason: typeof v === 'function' ? v(activeState.revisionReason) : v });
    const setProgress = (v) => setProjectState(selectedProjectKey, { progress: typeof v === 'function' ? v(activeState.progress) : v });
    const setProgressMessage = (v) => setProjectState(selectedProjectKey, { progressMessage: typeof v === 'function' ? v(activeState.progressMessage) : v });
"""

content = content.replace(state_decls, new_state_decls)

# Now we must update the async functions to use `taskKey` and `setProjectState`
# saveToHistory
content = content.replace("const saveToHistory = async (newResult) => {", "const saveToHistory = async (newResult, taskKey = selectedProjectKey) => {")
content = content.replace("setResult(prev => ({ ...prev, id: savedDoc.id }));", "setProjectState(taskKey, prev => ({ result: { ...prev.result, id: savedDoc.id }, revisionUnlocked: false, revisionReason: '' }));")
content = content.replace("setRevisionUnlocked(false);", "")
content = content.replace("setRevisionReason('');", "")
content = content.replace("selectedProject?.name", "(projects.find(p => p.key === taskKey)?.name)")
content = content.replace("selectedProject?.governanceResultId", "(projects.find(p => p.key === taskKey)?.governanceResultId)")
content = content.replace("selectedProject?.documents?.length", "(projects.find(p => p.key === taskKey)?.documents?.length)")

# loadHistoryItem
content = content.replace("const loadHistoryItem = (doc) => {", "const loadHistoryItem = (doc, taskKey = selectedProjectKey) => {")
content = content.replace("setAiQuestions(loadedQuestions);", "setProjectState(taskKey, { aiQuestions: loadedQuestions, userAnswers: savedAnswers, userFeedback: savedFeedback, error: '' });")
content = content.replace("setUserAnswers(savedAnswers);", "")
content = content.replace("setUserFeedback(savedFeedback);", "")
content = content.replace("setError('');", "")

content = content.replace("""setResult({
                id: doc.id,
                filename: doc.filename,
                extraction: {
                    markdown: doc.full_content || doc.content_preview || '(Content not available)',
                    num_pages: null
                },
                analysis: {
                    ...parsedAnalysis,
                    analysis: normalizedReport,
                    metrics: metrics || parsedAnalysis.metrics
                }
            });""", """setProjectState(taskKey, { result: {
                id: doc.id,
                filename: doc.filename,
                extraction: {
                    markdown: doc.full_content || doc.content_preview || '(Content not available)',
                    num_pages: null
                },
                analysis: {
                    ...parsedAnalysis,
                    analysis: normalizedReport,
                    metrics: metrics || parsedAnalysis.metrics
                }
            }});""")

# handleUpload
content = content.replace("const handleUpload = async (e) => {", "const handleUpload = async (e) => { const taskKey = selectedProjectKey; const taskFiles = files; const taskTab = activeTab; const taskTextInput = textInput; const taskGov = governanceContext;")
content = content.replace("setProcessing(true);", "setProjectState(taskKey, { processing: true, error: '', result: null, aiQuestions: [], userAnswers: {}, userFeedback: '' });")
content = content.replace("setError('');", "")
content = content.replace("setResult(null);", "")
content = content.replace("setAiQuestions([]);", "")
content = content.replace("setUserAnswers({});", "")
content = content.replace("setUserFeedback('');", "")

content = content.replace("setProgress(10);", "setProjectState(taskKey, { progress: 10, progressMessage: `Uploading ${taskFiles.length > 0 ? taskFiles.length : ''} documents for ${selectedProject.name}...` });")
content = content.replace("setProgressMessage(`Uploading ${files.length > 0 ? files.length : ''} documents for ${selectedProject.name}...`);", "")

content = content.replace("for (let i = 0; i < files.length; i++) {", "for (let i = 0; i < taskFiles.length; i++) {")
content = content.replace("formData.append('files', files[i]);", "formData.append('files', taskFiles[i]);")

content = content.replace("setProgress(40);", "setProjectState(taskKey, { progress: 40, progressMessage: 'Processing documents...' });")
content = content.replace("setProgressMessage('Processing documents...');", "")

content = content.replace("setResult(initialResult);", "setProjectState(taskKey, { result: initialResult });")
content = content.replace("""setResult(prev => ({
                    ...prev,
                    analysis: null
                }));""", "setProjectState(taskKey, prev => ({ result: { ...prev.result, analysis: null } }));")

# fetchAnalysis and streamAnalysis and handleRefineAnalysis
content = content.replace("const fetchAnalysis = async (payload, token, initialContext = null) => {", "const fetchAnalysis = async (payload, token, initialContext = null, taskKey = selectedProjectKey) => {")
content = content.replace("const streamAnalysis = async (payload, token, initialContext = null) => {", "const streamAnalysis = async (payload, token, initialContext = null, taskKey = selectedProjectKey) => {")
content = content.replace("const handleRefineAnalysis = async () => {", "const handleRefineAnalysis = async () => { const taskKey = selectedProjectKey; const taskGov = governanceContext; const taskResult = result;")

content = content.replace("setProgress(70);", "setProjectState(taskKey, { progress: 70, progressMessage: 'Initializing AI task...' });")
content = content.replace("setProgressMessage('Initializing AI stream...');", "")
content = content.replace("setProgressMessage('Requesting AI Analysis...');", "")
content = content.replace("await streamAnalysis(aiPayload, token, initialResult);", "await streamAnalysis(aiPayload, token, initialResult, taskKey);")
content = content.replace("await fetchAnalysis(aiPayload, token, initialResult);", "await fetchAnalysis(aiPayload, token, initialResult, taskKey);")
content = content.replace("await streamAnalysis(aiPayload, token, result);", "await streamAnalysis(aiPayload, token, taskResult, taskKey);")
content = content.replace("await fetchAnalysis(aiPayload, token, result);", "await fetchAnalysis(aiPayload, token, taskResult, taskKey);")

content = content.replace("setProcessing(false);", "setProjectState(taskKey, { processing: false });")
content = content.replace("setError(err.message);", "setProjectState(taskKey, { error: err.message });")
content = content.replace("setError(`Start Error: ${err.message}`);", "setProjectState(taskKey, { error: `Start Error: ${err.message}` });")
content = content.replace("setError(`Stream Error: ${err.message}`);", "setProjectState(taskKey, { error: `Stream Error: ${err.message}` });")

content = re.sub(r'if \(questions\.length > 0\) setAiQuestions\(questions\);', r'if (questions.length > 0) setProjectState(taskKey, { aiQuestions: questions });', content)

content = content.replace("""setResult(finalResult);
            setProgress(100);
            setProgressMessage('Analysis complete!');
            saveToHistory(finalResult);""", """setProjectState(taskKey, { result: finalResult, progress: 100, progressMessage: 'Analysis complete!' });
            saveToHistory(finalResult, taskKey);""")

content = content.replace("""setResult(finalResult);
            saveToHistory(finalResult);
            setProgress(100);
            setProgressMessage('Analysis complete!');""", """setProjectState(taskKey, { result: finalResult, progress: 100, progressMessage: 'Analysis complete!' });
            saveToHistory(finalResult, taskKey);""")

content = content.replace("setProgress(85);", "setProjectState(taskKey, { progress: 85, progressMessage: 'Generating professional analysis report...' });")
content = content.replace("setProgressMessage('Generating professional analysis report...');", "")

content = content.replace("""setResult(prev => ({
                                ...prev,
                                analysis: {
                                    analysis: report, // Use cleaned report
                                    reasoning: aiReasoning,
                                    model: payload.model || 'Streaming...',
                                    metrics: metrics // Update metrics from stream
                                }
                            }));""", """setProjectState(taskKey, prev => ({ result: {
                                ...prev.result,
                                analysis: {
                                    ...(prev.result?.analysis || {}),
                                    analysis: report,
                                    reasoning: aiReasoning,
                                    model: payload.model || 'Streaming...',
                                    metrics: metrics
                                }
                            }}));""")

content = content.replace("saveToHistory(finalResult);", "saveToHistory(finalResult, taskKey);")

content = content.replace("setProgress(20);", "setProjectState(taskKey, { progress: 20, progressMessage: 'Submitting feedback and refinements...' });")
content = content.replace("setProgressMessage('Submitting feedback and refinements...');", "")


with open('frontend/src/pages/Dashboard.jsx', 'w') as f:
    f.write(content)

