from __future__ import annotations
import time


def retry_with_backoff(fn, max_retries: int = 3, base_delay: float = 2.0, label: str = ""):
    """
    Call fn(). On rate-limit / quota errors, retry with exponential backoff.
    Other exceptions propagate immediately.
    """
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except Exception as exc:
            msg = str(exc).lower()
            is_rate_limit = any(s in msg for s in ["429", "rate", "quota", "resource_exhausted"])
            if not is_rate_limit or attempt == max_retries:
                raise
            delay = base_delay * (2 ** attempt)
            tag = f"[{label}] " if label else ""
            print(f"    ~ {tag}Rate limited, retrying in {delay:.0f}s (attempt {attempt + 1}/{max_retries})...")
            time.sleep(delay)
