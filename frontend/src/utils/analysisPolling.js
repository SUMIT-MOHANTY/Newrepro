/**
 * Utility functions for polling AI analysis jobs
 */

import { API_ENDPOINTS } from '../config';

/**
 * Start an analysis job and return the job ID
 */
export async function startAnalysisJob(payload, token) {
    const response = await fetch(API_ENDPOINTS.AI_ANALYZE, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify(payload)
    });

    if (response.status === 401) {
        throw new Error('Unauthorized - please log in again');
    }

    if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || 'Failed to start analysis');
    }

    const data = await response.json();
    
    // Check if this is a job response or direct result (for streaming mode)
    if (data.job_id) {
        return { jobId: data.job_id, isJob: true };
    }
    
    // Direct result (streaming mode or old behavior)
    return { result: data, isJob: false };
}

/**
 * Poll for analysis job status
 */
export async function pollAnalysisStatus(jobId, token) {
    const response = await fetch(`${API_ENDPOINTS.AI_ANALYZE}/status/${jobId}`, {
        method: 'GET',
        headers: {
            'Authorization': `Bearer ${token}`
        }
    });

    if (response.status === 401) {
        throw new Error('Unauthorized - please log in again');
    }

    if (response.status === 404) {
        throw new Error('Analysis job not found');
    }

    if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || 'Failed to get analysis status');
    }

    return await response.json();
}

/**
 * Poll for analysis completion with progress updates
 * 
 * @param {string} jobId - The job ID to poll
 * @param {string} token - Auth token
 * @param {function} onProgress - Callback for progress updates (progress, message)
 * @param {number} pollInterval - Polling interval in milliseconds (default: 2000)
 * @param {number} maxAttempts - Maximum polling attempts (default: 300 = 10 minutes at 2s intervals)
 * @returns {Promise<object>} - The completed analysis result
 */
export async function pollUntilComplete(
    jobId,
    token,
    onProgress = null,
    pollInterval = 30000,
    maxAttempts = 300
) {
    let attempts = 0;

    while (attempts < maxAttempts) {
        attempts++;

        try {
            const status = await pollAnalysisStatus(jobId, token);

            // Update progress if callback provided
            if (onProgress && typeof onProgress === 'function') {
                onProgress(status.progress || 0, status.progress_message || 'Processing...');
            }

            // Check if completed
            if (status.status === 'completed') {
                if (!status.result) {
                    throw new Error('Analysis completed but no result returned');
                }
                return status.result;
            }

            // Check if failed
            if (status.status === 'failed') {
                throw new Error(status.error || 'Analysis failed');
            }

            // Wait before next poll
            await new Promise(resolve => setTimeout(resolve, pollInterval));

        } catch (error) {
            // If it's a network error or temporary issue, retry
            if (attempts < maxAttempts) {
                console.warn(`Polling attempt ${attempts} failed, retrying...`, error);
                await new Promise(resolve => setTimeout(resolve, pollInterval));
                continue;
            }
            throw error;
        }
    }

    throw new Error('Analysis timed out - maximum polling attempts reached');
}

/**
 * Start analysis and poll until complete (convenience function)
 */
export async function startAndPollAnalysis(
    payload,
    token,
    onProgress = null,
    pollInterval = 30000,
    maxAttempts = 300
) {
    // Start the job
    const { jobId, isJob, result } = await startAnalysisJob(payload, token);

    // If not a job (streaming mode), return result directly
    if (!isJob) {
        return result;
    }

    // Poll until complete
    return await pollUntilComplete(jobId, token, onProgress, pollInterval, maxAttempts);
}
