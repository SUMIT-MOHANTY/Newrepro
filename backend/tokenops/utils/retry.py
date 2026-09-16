import time
import functools
import logging
from sqlalchemy.exc import OperationalError

logger = logging.getLogger(__name__)

def retry_on_lock(max_retries: int = 5):
    """
    Decorator to retry a function if SQLite raises a 'database is locked' OperationalError.
    Uses exponential backoff: 100ms, 250ms, 500ms, 1s, 2s.
    Ensures active SQLAlchemy sessions are rolled back between attempts to clear invalid transaction state.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            delays = [0.1, 0.25, 0.5, 1.0, 2.0]
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except (OperationalError, Exception) as e:
                    err_str = str(e).lower()
                    is_lock = "database is locked" in err_str or "database table is locked" in err_str or "busy" in err_str
                    if is_lock and attempt < max_retries:
                        delay = delays[attempt] if attempt < len(delays) else delays[-1]
                        logger.warning(f"Database locked in {func.__name__}. Rolling back and retrying in {delay}s (Attempt {attempt + 1}/{max_retries})")
                        
                        # Roll back session if available on instance
                        if args and hasattr(args[0], "session"):
                            try:
                                args[0].session.rollback()
                            except Exception:
                                pass
                        time.sleep(delay)
                    else:
                        raise
        return wrapper
    return decorator
