# utils/rate_limiter.py
import time
import asyncio
from typing import Optional
from collections import deque

class TokenBucketRateLimiter:
    """
    Token Bucket Algorithm for Rate Limiting.
    Implements a sliding window to handle bursts while maintaining overall limit.
    
    Example:
        limiter = TokenBucketRateLimiter(rate=20, per=60)  # 20 requests per 60 seconds
        await limiter.acquire()  # Wait if needed, then proceed
    """
    
    def __init__(self, rate: int, per: int = 60):
        """
        Initialize rate limiter.
        
        Args:
            rate: Number of requests allowed
            per: Time window in seconds (default 60)
        """
        self.rate = rate
        self.per = per
        self.allowance = rate
        self.last_check = time.time()
        self.lock = asyncio.Lock()
    
    async def acquire(self):
        """
        Acquire permission to proceed. Will wait if rate limit exceeded.
        """
        async with self.lock:
            now = time.time()
            time_passed = now - self.last_check
            self.last_check = now
            
            # Refill tokens based on time passed
            self.allowance += time_passed * (self.rate / self.per)
            
            # Cap at max rate
            if self.allowance > self.rate:
                self.allowance = self.rate
            
            # Wait if no tokens available
            if self.allowance < 1.0:
                sleep_time = (1.0 - self.allowance) * (self.per / self.rate)
                await asyncio.sleep(sleep_time)
                self.allowance = 0.0
            else:
                self.allowance -= 1.0

class SlidingWindowRateLimiter:
    """
    Sliding Window Rate Limiter for more accurate limiting.
    Tracks exact timestamps of requests.
    
    Example:
        limiter = SlidingWindowRateLimiter(rate=20, window=60)
        await limiter.acquire()
    """
    
    def __init__(self, rate: int, window: int = 60):
        """
        Initialize sliding window limiter.
        
        Args:
            rate: Number of requests allowed
            window: Time window in seconds
        """
        self.rate = rate
        self.window = window
        self.requests = deque()
        self.lock = asyncio.Lock()
    
    async def acquire(self):
        """
        Acquire permission to proceed. Will wait if rate limit exceeded.
        """
        async with self.lock:
            now = time.time()
            
            # Remove old requests outside the window
            while self.requests and self.requests[0] < now - self.window:
                self.requests.popleft()
            
            # If we've hit the limit, wait for the oldest request to expire
            if len(self.requests) >= self.rate:
                sleep_time = self.requests[0] + self.window - now
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
                    # Recursively try again after sleeping
                    return await self.acquire()
            
            # Record this request
            self.requests.append(now)
    
    def get_remaining_requests(self) -> int:
        """Get number of remaining requests in current window."""
        now = time.time()
        # Remove old requests
        while self.requests and self.requests[0] < now - self.window:
            self.requests.popleft()
        return max(0, self.rate - len(self.requests))
    
    def get_time_to_reset(self) -> float:
        """Get seconds until the rate limit resets."""
        if not self.requests:
            return 0.0
        now = time.time()
        reset_time = self.requests[0] + self.window
        return max(0.0, reset_time - now)


class AdaptiveRateLimiter:
    """
    Adaptive Rate Limiter that adjusts based on error feedback.
    Useful for APIs that give 429 (Too Many Requests) responses.
    """
    
    def __init__(self, initial_rate: int = 20, min_rate: int = 1, max_rate: int = 100):
        """
        Initialize adaptive limiter.
        
        Args:
            initial_rate: Starting requests per minute
            min_rate: Minimum rate to avoid going too low
            max_rate: Maximum rate cap
        """
        self.current_rate = initial_rate
        self.min_rate = min_rate
        self.max_rate = max_rate
        self.limiter = TokenBucketRateLimiter(rate=initial_rate, per=60)
        self.lock = asyncio.Lock()
    
    async def acquire(self):
        """Acquire permission to proceed."""
        await self.limiter.acquire()
    
    async def on_rate_limit_hit(self):
        """Call this when you get a 429 error. Reduces the rate."""
        async with self.lock:
            self.current_rate = max(self.min_rate, int(self.current_rate * 0.8))
            self.limiter = TokenBucketRateLimiter(rate=self.current_rate, per=60)
            print(f"Rate limit hit. Reducing to {self.current_rate} req/min")
    
    async def on_success(self):
        """Call this on successful requests. Slowly increases rate."""
        async with self.lock:
            if self.current_rate < self.max_rate:
                self.current_rate = min(self.max_rate, self.current_rate + 1)
                self.limiter = TokenBucketRateLimiter(rate=self.current_rate, per=60)
