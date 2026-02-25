import { useQuery, useMutation } from '@tanstack/react-query';
import { fetchGovernanceQuestions, submitGovernanceResponse } from '../api/governance';

export const useGovernanceQuestions = () => {
    return useQuery({
        queryKey: ['governance-questions'],
        queryFn: fetchGovernanceQuestions,
        staleTime: 1000 * 60 * 5, // Cache for 5 mins
    });
};

export const useSubmitGovernance = (options) => {
    return useMutation({
        mutationFn: submitGovernanceResponse,
        onSuccess: options?.onSuccess,
        onError: options?.onError
    });
};
