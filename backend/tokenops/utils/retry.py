import time
import functools
import logging
from sqlalchemy.exc import OperationalError

logger = logging.getLogger(__name__)

def retry_on_lock(max_retries: int = 3):
    """
    Decorator to retry a function if SQLite raises a 'database is locked' OperationalError.
    Uses exponential backoff: 50ms, 100ms, 200ms.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            delays = [0.05, 0.1, 0.2]  # 50ms, 100ms, 200ms
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except OperationalError as e:
                    if "database is locked" in str(e).lower() and attempt < max_retries:
                        delay = delays[attempt] if attempt < len(delays) else delays[-1]
                        logger.warning(f"Database locked. Retrying in {delay}s (Attempt {attempt + 1}/{max_retries})")
                        time.sleep(delay)
                    else:
                        raise
        return wrapper
    return decorator
