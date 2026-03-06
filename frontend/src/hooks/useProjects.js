import { useQuery, useQueryClient } from '@tanstack/react-query';
import { fetchProjectsData, fetchRoadmapStep } from '../api/projects';
import { getDraftProjects } from '../utils/draftProjects';

export const useProjects = () => {
    return useQuery({
        queryKey: ['projects'],
        queryFn: fetchProjectsData,
        staleTime: 60 * 1000,
        select: (data) => {
            const { govPayload, historyPayload } = data;
            const submissions = Array.isArray(govPayload?.submissions) ? govPayload.submissions : [];
            const history = Array.isArray(historyPayload) ? historyPayload : [];
            const draftProjects = getDraftProjects();

            // Build project map
            const normalizeProjectName = (name) => String(name || '').trim().toLowerCase().replace(/\s+/g, ' ');
            const projectMap = new Map();

            submissions.forEach((sub) => {
                const key = sub.project_token || String(sub.id);
                projectMap.set(key, {
                    key,
                    governanceResultId: sub.id,
                    projectToken: sub.project_token,
                    name: sub.project_name || `Project #${sub.id}`,
                    classification: sub.classification || 'N/A',
                    weightedScore: sub.weighted_score ?? null,
                    submissionDate: sub.submission_date || null,
                    documents: [],
                    latestDocument: null,
                    latestRevision: 0,
                    status: 'ready_for_upload',
                    pendingRevisionReason: sub.pending_revision_reason || null,
                    client_id: sub.client_id || null,
                    client_secret: sub.client_secret || null,
                });
            });

            history.forEach((doc) => {
                let parsedAnalysis = null;
                try { parsedAnalysis = doc?.analysis_result ? JSON.parse(doc.analysis_result) : null; } catch { /* ignore */ }

                const meta = parsedAnalysis?.projectMeta || {};
                const govMeta = parsedAnalysis?.governanceContext || {};
                const projectName = meta.project_name || govMeta.project_name || 'Unassigned Project';
                const governanceResultId = meta.governance_result_id || govMeta.result_id || null;
                const projectToken = meta.project_token || govMeta.project_token || null;

                const client_id = doc.project_application?.client_id || null;
                const client_secret = doc.project_application?.client_secret || null;

                let targetKey = projectToken || null;
                if (!targetKey || !projectMap.has(targetKey)) {
                    const byId = governanceResultId
                        ? Array.from(projectMap.values()).find(p => p.governanceResultId === governanceResultId)
                        : null;
                    if (byId) targetKey = byId.key;
                }
                if (!targetKey || !projectMap.has(targetKey)) {
                    const byName = Array.from(projectMap.values()).find(
                        p => normalizeProjectName(p.name) === normalizeProjectName(projectName)
                    );
                    if (byName) targetKey = byName.key;
                }
                if (!targetKey || !projectMap.has(targetKey)) {
                    targetKey = projectToken || (governanceResultId ? String(governanceResultId) : `doc-${doc.id}`);
                    if (!projectMap.has(targetKey)) {
                        projectMap.set(targetKey, {
                            key: targetKey, governanceResultId: governanceResultId, projectToken,
                            name: projectName, classification: 'N/A', weightedScore: null,
                            submissionDate: null, documents: [], latestDocument: null,
                            latestRevision: 0, status: 'ready_for_upload',
                            client_id, client_secret
                        });
                    }
                }
                const project = projectMap.get(targetKey);
                if (client_id && !project.client_id) {
                    project.client_id = client_id;
                    project.client_secret = client_secret;
                }

                project.documents.push(doc);
                if (!project.latestDocument) project.latestDocument = doc;
            });

            const builtProjects = Array.from(projectMap.values())
                .map(project => {
                    const draft = draftProjects.find((entry) => entry.key === project.key);
                    const docs = [...project.documents].sort(
                        (a, b) => new Date(b.upload_date || 0).getTime() - new Date(a.upload_date || 0).getTime()
                    );
                    return {
                        ...draft,
                        ...project,
                        projectToken: project.projectToken || draft?.projectToken || project.key,
                        client_id: project.client_id || draft?.client_id || null,
                        client_secret: project.client_secret || draft?.client_secret || null,
                        documents: docs,
                        latestDocument: docs[0] || null,
                        latestRevision: docs.length,
                        status: docs.length > 0 ? 'analysis_complete' : (draft?.status || 'ready_for_upload'),
                        isDraft: !project.governanceResultId && docs.length === 0,
                    };
                })
                .concat(
                    draftProjects
                        .filter((draft) => !projectMap.has(draft.key))
                        .map((draft) => ({ ...draft }))
                )
                .sort((a, b) => {
                    const aDate = new Date(a.submissionDate || a.createdAt || a.latestDocument?.upload_date || 0).getTime();
                    const bDate = new Date(b.submissionDate || b.createdAt || b.latestDocument?.upload_date || 0).getTime();
                    return bDate - aDate;
                });

            return builtProjects;
        }
    });
};

export const useRoadmapData = (projectKey) => {
    return useQuery({
        queryKey: ['roadmap', projectKey],
        queryFn: () => fetchRoadmapStep(projectKey),
        enabled: !!projectKey,
        staleTime: 0, // Always refetch to be accurate, or use queryClient.invalidateQueries()
    });
};

export const useInvalidateProjects = () => {
    const queryClient = useQueryClient();
    return () => {
        queryClient.invalidateQueries({ queryKey: ['projects'] });
        queryClient.invalidateQueries({ queryKey: ['roadmap'] });
    }
}
