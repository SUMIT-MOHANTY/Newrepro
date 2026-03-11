import { useState, useMemo } from 'react';
import {
    Plus, Edit2, Trash2, ChevronDown, ChevronUp, Save, X, GripVertical,
    AlertCircle, CheckCircle2, Layout, Settings, List, BarChart2, ChevronRight, ChevronLeft
} from 'lucide-react';
import {
    useAllGovernanceQuestions,
    useCreateGovernanceQuestion,
    useUpdateGovernanceQuestion,
    useDeleteGovernanceQuestion
} from '../hooks/useGovernance';

const DEFAULT_DIMENSIONS = [
    "Business Value & Urgency",
    "Data Sensitivity",
    "Integration & Architecture Complexity",
    "Operational Impact",
    "AI Risk",
    "Ownership & Support"
];

const GovernanceManagement = () => {
    const { data: questions, isLoading } = useAllGovernanceQuestions();
    const createMutation = useCreateGovernanceQuestion();
    const updateMutation = useUpdateGovernanceQuestion();
    const deleteMutation = useDeleteGovernanceQuestion();

    const [editingId, setEditingId] = useState(null);
    const [isCreating, setIsCreating] = useState(false);
    const [isCustomDimension, setIsCustomDimension] = useState(false);
    const [formData, setFormData] = useState({
        dimension: DEFAULT_DIMENSIONS[0],
        question_text: '',
        order: 0,
        is_active: true,
        options: [
            { label: '', score: 0 },
            { label: '', score: 1 },
            { label: '', score: 2 },
            { label: '', score: 3 }
        ]
    });

    const handleEdit = (q) => {
        setEditingId(q.id);
        const isDefault = DEFAULT_DIMENSIONS.includes(q.dimension);
        setIsCustomDimension(!isDefault);
        setFormData({
            dimension: q.dimension,
            question_text: q.question_text,
            order: q.order,
            is_active: q.is_active,
            options: q.options.map(o => ({ label: o.label, score: o.score }))
        });
        setIsCreating(false);
    };

    const handleCancel = () => {
        setEditingId(null);
        setIsCreating(false);
        setIsCustomDimension(false);
        setFormData({
            dimension: DEFAULT_DIMENSIONS[0],
            question_text: '',
            order: 0,
            is_active: true,
            options: [
                { label: '', score: 0 },
                { label: '', score: 1 },
                { label: '', score: 2 },
                { label: '', score: 3 }
            ]
        });
    };

    const handleSave = async () => {
        try {
            if (editingId) {
                await updateMutation.mutateAsync({ id: editingId, ...formData });
            } else {
                await createMutation.mutateAsync(formData);
                handleCancel();
            }
        } catch (err) {
            console.error(err);
        }
    };

    const handleNavigate = (direction) => {
        if (!editingId) return;
        const currentIndex = sortedQuestions.findIndex(q => q.id === editingId);
        const targetQuestion = sortedQuestions[currentIndex + direction];
        if (targetQuestion) {
            handleEdit(targetQuestion);
        }
    };

    const handleDelete = async (id) => {
        if (window.confirm('Are you sure you want to delete this question?')) {
            try {
                await deleteMutation.mutateAsync(id);
            } catch (err) {
                console.error(err);
            }
        }
    };

    const handleOptionChange = (idx, field, value) => {
        const newOptions = [...formData.options];
        newOptions[idx] = { ...newOptions[idx], [field]: field === 'score' ? parseInt(value) : value };
        setFormData({ ...formData, options: newOptions });
    };

    const addOption = () => {
        setFormData({
            ...formData,
            options: [...formData.options, { label: '', score: 0 }]
        });
    };

    const removeOption = (idx) => {
        setFormData({
            ...formData,
            options: formData.options.filter((_, i) => i !== idx)
        });
    };

    const allDimensions = useMemo(() => {
        const questionDims = questions?.map(q => q.dimension) || [];
        return Array.from(new Set([...DEFAULT_DIMENSIONS, ...questionDims]));
    }, [questions]);

    const sortedQuestions = useMemo(() => {
        if (!questions) return [];
        return [...questions].sort((a, b) => a.order - b.order);
    }, [questions]);

    if (isLoading) {
        return (
            <div className="flex items-center justify-center h-full">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-app-primary"></div>
            </div>
        );
    }

    return (
        <div className="flex-1 overflow-auto bg-app-bg-page p-8 min-h-full">
            <div className="max-w-6xl mx-auto pb-24">
                <div className="flex justify-between items-center mb-10">
                    <div>
                        <h1 className="text-3xl font-bold text-app-text-main flex items-center gap-3">
                            <Layout className="w-8 h-8 text-app-primary" />
                            Governance Management
                        </h1>
                        <p className="text-app-text-light mt-2">
                            Configure project classification questions, dimensions, and scoring logic.
                        </p>
                    </div>
                    {!isCreating && !editingId && (
                        <button
                            onClick={() => setIsCreating(true)}
                            className="flex items-center gap-2 bg-app-primary hover:bg-app-primary-hover text-white px-5 py-2.5 rounded-xl font-semibold transition-all shadow-lg active:scale-95"
                        >
                            <Plus className="w-5 h-5" />
                            Add Question
                        </button>
                    )}
                </div>

                {(isCreating || editingId) ? (
                    <div className="bg-app-bg-card border border-app-border rounded-2xl shadow-xl overflow-hidden animate-in fade-in slide-in-from-bottom-4 duration-500">
                        <div className="p-6 border-b border-app-border bg-app-bg-muted/30 flex justify-between items-center">
                            <h2 className="text-xl font-bold text-app-text-main flex items-center gap-2">
                                {editingId ? 'Edit Question' : 'Create New Question'}
                            </h2>
                            <div className="flex gap-2">
                                <button
                                    onClick={handleCancel}
                                    className="p-2 text-app-text-light hover:bg-app-bg-muted rounded-lg transition-colors"
                                >
                                    <X className="w-6 h-6" />
                                </button>
                            </div>
                        </div>

                        <div className="p-8 space-y-8">
                            <div className="grid grid-cols-2 gap-8">
                                <div className="space-y-2">
                                    <div className="flex justify-between items-center">
                                        <label className="text-sm font-bold text-app-text-label uppercase tracking-wider">Dimension</label>
                                        <button
                                            onClick={() => {
                                                setIsCustomDimension(!isCustomDimension);
                                                if (!isCustomDimension) setFormData({ ...formData, dimension: '' });
                                                else setFormData({ ...formData, dimension: DEFAULT_DIMENSIONS[0] });
                                            }}
                                            className="text-[10px] font-bold text-app-primary uppercase hover:underline"
                                        >
                                            {isCustomDimension ? 'Select Existing' : 'Add Custom'}
                                        </button>
                                    </div>
                                    {isCustomDimension ? (
                                        <input
                                            type="text"
                                            value={formData.dimension}
                                            onChange={(e) => setFormData({ ...formData, dimension: e.target.value })}
                                            className="w-full bg-app-bg-page border border-app-border rounded-xl px-4 py-3 text-app-text-main focus:ring-2 focus:ring-app-primary outline-none transition-all"
                                            placeholder="Enter custom dimension name..."
                                        />
                                    ) : (
                                        <select
                                            value={formData.dimension}
                                            onChange={(e) => setFormData({ ...formData, dimension: e.target.value })}
                                            className="w-full bg-app-bg-page border border-app-border rounded-xl px-4 py-3 text-app-text-main focus:ring-2 focus:ring-app-primary outline-none transition-all"
                                        >
                                            {allDimensions.map(d => <option key={d} value={d}>{d}</option>)}
                                        </select>
                                    )}
                                </div>
                                <div className="space-y-2">
                                    <label className="text-sm font-bold text-app-text-label uppercase tracking-wider">Sort Order</label>
                                    <input
                                        type="number"
                                        value={formData.order}
                                        onChange={(e) => setFormData({ ...formData, order: parseInt(e.target.value) })}
                                        className="w-full bg-app-bg-page border border-app-border rounded-xl px-4 py-3 text-app-text-main focus:ring-2 focus:ring-app-primary outline-none transition-all"
                                        placeholder="0"
                                    />
                                </div>
                            </div>

                            <div className="space-y-2">
                                <label className="text-sm font-bold text-app-text-label uppercase tracking-wider">Question Text</label>
                                <textarea
                                    value={formData.question_text}
                                    onChange={(e) => setFormData({ ...formData, question_text: e.target.value })}
                                    className="w-full bg-app-bg-page border border-app-border rounded-xl px-4 py-3 text-app-text-main focus:ring-2 focus:ring-app-primary outline-none transition-all min-h-[100px]"
                                    placeholder="Enter question text..."
                                />
                            </div>

                            <div className="space-y-4">
                                <div className="flex justify-between items-center">
                                    <label className="text-sm font-bold text-app-text-label uppercase tracking-wider">Answer Options & Scores</label>
                                    <button
                                        onClick={addOption}
                                        className="text-xs flex items-center gap-1 text-app-primary hover:underline font-bold"
                                    >
                                        <Plus className="w-3 h-3" /> Add Option
                                    </button>
                                </div>
                                <div className="space-y-3">
                                    {formData.options.map((opt, idx) => (
                                        <div key={idx} className="flex gap-4 items-center animate-in fade-in slide-in-from-left-2 duration-300">
                                            <div className="flex-1">
                                                <input
                                                    type="text"
                                                    value={opt.label}
                                                    onChange={(e) => handleOptionChange(idx, 'label', e.target.value)}
                                                    className="w-full bg-app-bg-page border border-app-border rounded-xl px-4 py-2.5 text-app-text-main focus:ring-2 focus:ring-app-primary outline-none transition-all"
                                                    placeholder="Option label..."
                                                />
                                            </div>
                                            <div className="w-24">
                                                <input
                                                    type="number"
                                                    value={opt.score}
                                                    onChange={(e) => handleOptionChange(idx, 'score', e.target.value)}
                                                    className="w-full bg-app-bg-page border border-app-border rounded-xl px-4 py-2.5 text-app-text-main focus:ring-2 focus:ring-app-primary outline-none transition-all text-center"
                                                    placeholder="Score"
                                                />
                                            </div>
                                            <button
                                                onClick={() => removeOption(idx)}
                                                className="p-2 text-app-text-light hover:text-app-status-error hover:bg-app-status-errorBg rounded-lg transition-all"
                                            >
                                                <Trash2 className="w-4 h-4" />
                                            </button>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </div>

                        <div className="p-6 bg-app-bg-muted/30 border-t border-app-border flex justify-between items-center">
                            <div className="flex gap-3">
                                {editingId && (
                                    <>
                                        <button
                                            onClick={() => handleNavigate(-1)}
                                            disabled={sortedQuestions.findIndex(q => q.id === editingId) === 0}
                                            className="flex items-center gap-2 bg-app-bg-muted hover:bg-app-bg-muted/80 text-app-text-main px-4 py-2.5 rounded-xl font-bold transition-all active:scale-95 disabled:opacity-30"
                                        >
                                            <ChevronLeft className="w-5 h-5" />
                                            Back
                                        </button>
                                        <button
                                            onClick={() => handleNavigate(1)}
                                            disabled={sortedQuestions.findIndex(q => q.id === editingId) === sortedQuestions.length - 1}
                                            className="flex items-center gap-2 bg-app-bg-muted hover:bg-app-bg-muted/80 text-app-text-main px-4 py-2.5 rounded-xl font-bold transition-all active:scale-95 disabled:opacity-30"
                                        >
                                            Next
                                            <ChevronRight className="w-5 h-5" />
                                        </button>
                                    </>
                                )}
                            </div>
                            <div className="flex gap-3">
                                <button
                                    onClick={handleCancel}
                                    className="px-6 py-2.5 rounded-xl font-bold text-app-text-label hover:bg-app-bg-muted transition-all"
                                >
                                    Cancel
                                </button>
                                <button
                                    onClick={handleSave}
                                    disabled={createMutation.isPending || updateMutation.isPending}
                                    className="flex items-center gap-2 bg-app-primary hover:bg-app-primary-hover text-white px-8 py-2.5 rounded-xl font-bold transition-all shadow-lg active:scale-95 disabled:opacity-50"
                                >
                                    {(createMutation.isPending || updateMutation.isPending) ? (
                                        <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                                    ) : <Save className="w-5 h-5" />}
                                    {editingId ? 'Update Question' : 'Save Question'}
                                </button>
                            </div>
                        </div>
                    </div>
                ) : (
                    <div className="space-y-6">
                        {sortedQuestions.length === 0 ? (
                            <div className="text-center py-20 bg-app-bg-card border border-dashed border-app-border rounded-3xl">
                                <List className="w-16 h-16 text-app-text-light/20 mx-auto mb-4" />
                                <h3 className="text-xl font-bold text-app-text-label">No questions found</h3>
                                <p className="text-app-text-light mt-2">Get started by creating your first governance question.</p>
                                <button
                                    onClick={() => setIsCreating(true)}
                                    className="mt-6 inline-flex items-center gap-2 text-app-primary font-bold hover:underline"
                                >
                                    <Plus className="w-4 h-4" /> Add your first question
                                </button>
                            </div>
                        ) : (
                            <div className="grid gap-6">
                                {[...allDimensions].sort().map(dim => {
                                    const dimQuestions = sortedQuestions.filter(q => q.dimension === dim);
                                    if (dimQuestions.length === 0) return null;

                                    return (
                                        <div key={dim} className="space-y-4">
                                            <h3 className="text-sm font-black text-app-text-label uppercase tracking-[0.2em] flex items-center gap-2 pl-2">
                                                <BarChart2 className="w-4 h-4 text-app-primary" />
                                                {dim}
                                            </h3>
                                            <div className="grid gap-4">
                                                {dimQuestions.map(q => (
                                                    <div
                                                        key={q.id}
                                                        className="bg-app-bg-card border border-app-border rounded-2xl p-5 hover:border-app-primary/30 hover:shadow-xl transition-all group relative"
                                                    >
                                                        <div className="flex justify-between items-start">
                                                            <div className="flex-1 pr-10">
                                                                <div className="flex items-center gap-3 mb-2">
                                                                    <span className="bg-app-bg-muted text-app-text-label text-[10px] font-bold px-2 py-0.5 rounded uppercase tracking-wider">
                                                                        ID: {q.id}
                                                                    </span>
                                                                    <span className="bg-app-bg-muted text-app-text-label text-[10px] font-bold px-2 py-0.5 rounded uppercase tracking-wider">
                                                                        Order: {q.order}
                                                                    </span>
                                                                    {!q.is_active && (
                                                                        <span className="bg-app-status-errorBg text-app-status-error text-[10px] font-bold px-2 py-0.5 rounded uppercase tracking-wider">
                                                                            Inactive
                                                                        </span>
                                                                    )}
                                                                </div>
                                                                <h4 className="text-lg font-bold text-app-text-main leading-tight mb-4">
                                                                    {q.question_text}
                                                                </h4>
                                                                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                                                                    {q.options.map((opt, i) => (
                                                                        <div key={i} className="bg-app-bg-muted/40 rounded-xl p-3 border border-app-border/50">
                                                                            <p className="text-[10px] font-semibold text-app-text-muted uppercase tracking-tighter mb-1">Score: {opt.score}</p>
                                                                            <p className="text-xs font-bold text-app-text-label line-clamp-2">{opt.label}</p>
                                                                        </div>
                                                                    ))}
                                                                </div>
                                                            </div>
                                                            <div className="flex flex-col gap-2 opacity-0 group-hover:opacity-100 transition-opacity absolute top-5 right-5">
                                                                <button
                                                                    onClick={() => handleEdit(q)}
                                                                    className="p-2.5 bg-app-bg-page hover:bg-app-primary hover:text-white border border-app-border rounded-xl shadow-sm transition-all"
                                                                    title="Edit Question"
                                                                >
                                                                    <Edit2 className="w-4 h-4" />
                                                                </button>
                                                                <button
                                                                    onClick={() => handleDelete(q.id)}
                                                                    className="p-2.5 bg-app-bg-page hover:bg-app-status-error hover:text-white border border-app-border rounded-xl shadow-sm transition-all text-app-status-error"
                                                                    title="Delete Question"
                                                                >
                                                                    <Trash2 className="w-4 h-4" />
                                                                </button>
                                                            </div>
                                                        </div>
                                                    </div>
                                                ))}
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
};

export default GovernanceManagement;
