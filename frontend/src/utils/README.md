# Error Handling Utilities

This directory contains utilities for consistent error handling across the application.

## Usage

### Basic Error Sanitization

```javascript
import { sanitizeErrorMessage } from './errorHandling';

try {
    // Some API call or operation
    const result = await fetch('/api/endpoint');
    if (!result.ok) {
        throw new Error('API call failed');
    }
} catch (error) {
    // Instead of showing technical error to user
    setError(sanitizeErrorMessage(error));
}
```

### Error Handling with Context

```javascript
import { handleError } from './errorHandling';

try {
    // Some operation
    await saveData();
} catch (error) {
    // Logs the full error for debugging, returns sanitized message
    const userMessage = handleError(error, 'saveData');
    setError(userMessage);
}
```

### Using Predefined Messages

```javascript
import { ERROR_MESSAGES } from './errorHandling';

// For common scenarios
if (!navigator.onLine) {
    setError(ERROR_MESSAGES.NETWORK);
}

if (response.status === 401) {
    setError(ERROR_MESSAGES.AUTH);
}
```

## Error Types Handled

- **Database Errors**: UNIQUE constraint violations, integrity errors
- **Network Errors**: Connection issues, offline status
- **Authentication Errors**: 401, unauthorized access
- **Server Errors**: 500, internal server errors
- **Permission Errors**: 403, access denied
- **Git/Repository Errors**: Clone failures, repository access issues
- **Timeout Errors**: Request timeouts
- **Generic API Errors**: Long technical error messages

## Benefits

1. **Consistent UX**: All error messages follow the same user-friendly format
2. **Security**: Technical details and stack traces are hidden from users
3. **Debugging**: Original errors are still logged to console for developers
4. **Maintainability**: Centralized error handling logic