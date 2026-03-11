import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { API_ENDPOINTS } from '../config';
import { fetchGovernanceQuestions, submitGovernanceResponse } from '../api/governance';

export const useGovernanceQuestions = () => {
    return useQuery({
        queryKey: ['governance-questions'],
        queryFn: fetchGovernanceQuestions,
        staleTime: 1000 * 60 * 5, // Cache for 5 mins
    });
};

export const useAllGovernanceQuestions = () => {
    return useQuery({
        queryKey: ['governance-questions-all'],
        queryFn: async () => {
            const token = localStorage.getItem('token');
            const res = await fetch(API_ENDPOINTS.GOVERNANCE_QUESTION_ALL, {
                headers: { Authorization: `Bearer ${token}` }
            });
            if (!res.ok) throw new Error('Failed to fetch questions');
            return res.json();
        }
    });
};

export const useCreateGovernanceQuestion = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (question) => {
            const token = localStorage.getItem('token');
            const res = await fetch(API_ENDPOINTS.GOVERNANCE_QUESTION_CREATE, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    Authorization: `Bearer ${token}`
                },
                body: JSON.stringify(question)
            });
            if (!res.ok) throw new Error('Failed to create question');
            return res.json();
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['governance-questions'] });
            queryClient.invalidateQueries({ queryKey: ['governance-questions-all'] });
        }
    });
};

export const useUpdateGovernanceQuestion = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, ...update }) => {
            const token = localStorage.getItem('token');
            const res = await fetch(API_ENDPOINTS.GOVERNANCE_QUESTION_UPDATE(id), {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    Authorization: `Bearer ${token}`
                },
                body: JSON.stringify(update)
            });
            if (!res.ok) throw new Error('Failed to update question');
            return res.json();
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['governance-questions'] });
            queryClient.invalidateQueries({ queryKey: ['governance-questions-all'] });
        }
    });
};

export const useDeleteGovernanceQuestion = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id) => {
            const token = localStorage.getItem('token');
            const res = await fetch(API_ENDPOINTS.GOVERNANCE_QUESTION_DELETE(id), {
                method: 'DELETE',
                headers: { Authorization: `Bearer ${token}` }
            });
            if (!res.ok) throw new Error('Failed to delete question');
            return res.json();
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['governance-questions'] });
            queryClient.invalidateQueries({ queryKey: ['governance-questions-all'] });
        }
    });
};

export const useSubmitGovernance = (options) => {
    return useMutation({
        mutationFn: submitGovernanceResponse,
        onSuccess: options?.onSuccess,
        onError: options?.onError
    });
};
