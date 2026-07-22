const DRAFT_PROJECTS_STORAGE_KEY = 'draft_projects';

const readDraftProjects = () => {
    if (typeof window === 'undefined') return [];

    try {
        const raw = localStorage.getItem(DRAFT_PROJECTS_STORAGE_KEY);
        if (!raw) return [];

        const parsed = JSON.parse(raw);
        return Array.isArray(parsed) ? parsed : [];
    } catch {
        return [];
    }
};

const writeDraftProjects = (projects) => {
    if (typeof window === 'undefined') return;

    try {
        localStorage.setItem(DRAFT_PROJECTS_STORAGE_KEY, JSON.stringify(projects));
    } catch {
        // Ignore storage quota / privacy mode errors.
    }
};

const buildDraftProject = (project = {}) => {
    if (!project || typeof project !== 'object') return null;

    const key = String(project.key || project.projectToken || '').trim();
    if (!key) return null;

    const createdAt = project.createdAt || new Date().toISOString();
    const name = String(project.name || project.project_name || 'Untitled Project').trim() || 'Untitled Project';

    return {
        key,
        projectToken: key,
        governanceResultId: project.governanceResultId ?? null,
        name,
        classification: project.classification || 'N/A',
        weightedScore: project.weightedScore ?? null,
        submissionDate: project.submissionDate || createdAt,
        createdAt,
        documents: Array.isArray(project.documents) ? project.documents : [],
        latestDocument: project.latestDocument || null,
        latestRevision: project.latestRevision ?? 0,
        status: project.status || 'ready_for_upload',
        pendingRevisionReason: project.pendingRevisionReason || null,
        client_id: project.client_id || null,
        client_secret: project.client_secret || null,
        owner_id: project.owner_id || null,
        isDraft: true,
    };
};

const generateDraftKey = () => {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
        return crypto.randomUUID();
    }
    return `draft-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
};

export const createDraftProject = (name, overrides = {}) => {
    const resolvedKey = overrides?.key || overrides?.projectToken || generateDraftKey();
    return buildDraftProject({
        ...overrides,
        key: resolvedKey,
        name,
    });
};

export const getDraftProjects = () => {
    return readDraftProjects()
        .map((project) => buildDraftProject(project))
        .filter(Boolean)
        .sort((a, b) => new Date(b.createdAt || b.submissionDate || 0).getTime() - new Date(a.createdAt || a.submissionDate || 0).getTime());
};

export const getDraftProject = (projectKey) => {
    const normalizedKey = String(projectKey || '').trim();
    if (!normalizedKey) return null;
    return getDraftProjects().find((project) => project.key === normalizedKey || project.projectToken === normalizedKey) || null;
};

export const upsertDraftProject = (project) => {
    const nextProject = buildDraftProject(project);
    if (!nextProject) return null;

    const existing = readDraftProjects().map((entry) => buildDraftProject(entry)).filter(Boolean);
    const nextProjects = existing.filter((entry) => entry.key !== nextProject.key);
    nextProjects.push(nextProject);
    writeDraftProjects(nextProjects);
    return nextProject;
};

export const removeDraftProject = (projectKey) => {
    const normalizedKey = String(projectKey || '').trim();
    if (!normalizedKey) return;

    const nextProjects = readDraftProjects().filter((entry) => {
        const entryKey = String(entry?.key || entry?.projectToken || '').trim();
        return entryKey && entryKey !== normalizedKey;
    });
    writeDraftProjects(nextProjects);
};

export const clearDraftProjects = () => {
    if (typeof window === 'undefined') return;
    try {
        localStorage.removeItem(DRAFT_PROJECTS_STORAGE_KEY);
    } catch {
        // Ignore storage quota / privacy mode errors.
    }
};

export { DRAFT_PROJECTS_STORAGE_KEY };
