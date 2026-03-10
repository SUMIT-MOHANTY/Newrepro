const TASK_TOKEN_STORAGE_KEY = 'status_dashboard_task_token_cache';

function decodeJwtExpiry(token) {
  try {
    const parts = String(token || '').split('.');
    if (parts.length < 2) return null;
    const payloadB64 = parts[1].replace(/-/g, '+').replace(/_/g, '/');
    const padded = payloadB64 + '='.repeat((4 - (payloadB64.length % 4)) % 4);
    const payload = JSON.parse(atob(padded));
    return typeof payload.exp === 'number' ? payload.exp : null;
  } catch {
    return null;
  }
}

function readTaskTokenCache() {
  try {
    const raw = localStorage.getItem(TASK_TOKEN_STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
}

function writeTaskTokenCache(cache) {
  try {
    localStorage.setItem(TASK_TOKEN_STORAGE_KEY, JSON.stringify(cache));
  } catch {
    // Ignore storage errors.
  }
}

/**
 * Returns cached token string for a project key if present and not expired.
 * If minTtlSeconds > 0, a token expiring sooner than now+minTtlSeconds is treated as expired.
 */
export function getCachedTaskToken(projectKey, minTtlSeconds = 0) {
  if (!projectKey) return null;
  const cache = readTaskTokenCache();
  const entry = cache[projectKey];
  if (!entry || !entry.token) return null;

  const now = Math.floor(Date.now() / 1000);
  const expiresAt = typeof entry.expiresAt === 'number' ? entry.expiresAt : decodeJwtExpiry(entry.token);
  if (expiresAt && expiresAt <= now + Number(minTtlSeconds || 0)) {
    delete cache[projectKey];
    writeTaskTokenCache(cache);
    return null;
  }

  return entry.token;
}

/**
 * Cache token string for a project key (best effort).
 */
export function setCachedTaskToken(projectKey, token) {
  if (!projectKey || !token) return;
  const cache = readTaskTokenCache();
  cache[projectKey] = {
    token,
    expiresAt: decodeJwtExpiry(token),
  };
  writeTaskTokenCache(cache);
}

