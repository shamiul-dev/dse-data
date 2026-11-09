"""
Token-bucket rate limiter with randomized jitter to prevent rate-limiting/429s.
Thread-safe and async-friendly.
"""

import random
import time


class RateLimiter:
    """
    Limits requests to a maximum frequency (calls per second)
    with randomized jitter to simulate human/organic traffic patterns.
    """

    def __init__(self, requests_per_second: float = 2.0, jitter_range: tuple[float, float] = (0.1, 0.4)):
        self.min_interval = 1.0 / max(0.1, requests_per_second)
        self.jitter_min, self.jitter_max = jitter_range
        self.last_call_time = 0.0

    def wait(self) -> None:
        """Blocks until it is safe to make the next request."""
        now = time.monotonic()
        elapsed = now - self.last_call_time
        target_wait = self.min_interval + random.uniform(self.jitter_min, self.jitter_max)

        if elapsed < target_wait:
            time.sleep(target_wait - elapsed)

        self.last_call_time = time.monotonic()

