import { API_ENDPOINTS } from '../config';

export const fetchGovernanceQuestions = async () => {
    const res = await fetch(API_ENDPOINTS.GOVERNANCE_QUESTIONS);
    if (!res.ok) {
        throw new Error('Failed to load governance questions');
    }
    const data = await res.json();
    return data;
};

export const submitGovernanceResponse = async (submissionData) => {
    const token = localStorage.getItem('token');
    const res = await fetch(API_ENDPOINTS.GOVERNANCE_SUBMIT, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${token}`
        },
        body: JSON.stringify(submissionData),
    });

    if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Submission failed');
    }

    return await res.json();
};
