"""
Rate limiting for authentication endpoints
Prevents brute force attacks and API abuse
"""

import time
from typing import Dict, Optional
from collections import defaultdict, deque
import structlog

logger = structlog.get_logger(__name__)

class RateLimiter:
    """Rate limiter for authentication attempts"""
    
    def __init__(self, max_attempts: int = 5, window_seconds: int = 300):
        """
        Initialize rate limiter
        
        Args:
            max_attempts: Maximum attempts allowed within the window
            window_seconds: Time window in seconds (default: 5 minutes)
        """
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.attempts: Dict[str, deque] = defaultdict(deque)
        
    def is_allowed(self, identifier: str) -> bool:
        """
        Check if request is allowed based on rate limiting
        
        Args:
            identifier: Unique identifier (IP address, user ID, etc.)
            
        Returns:
            True if request is allowed, False if rate limited
        """
        current_time = time.time()
        
        # Get attempts for this identifier
        attempts = self.attempts[identifier]
        
        # Remove old attempts outside the window
        while attempts and attempts[0] < current_time - self.window_seconds:
            attempts.popleft()
        
        # Check if under limit
        if len(attempts) >= self.max_attempts:
            logger.warning(
                "Rate limit exceeded",
                identifier=identifier,
                attempts=len(attempts),
                max_attempts=self.max_attempts
            )
            return False
        
        # Record this attempt
        attempts.append(current_time)
        return True
    
    def record_failed_attempt(self, identifier: str) -> None:
        """
        Record a failed authentication attempt
        
        Args:
            identifier: Unique identifier
        """
        current_time = time.time()
        self.attempts[identifier].append(current_time)
        
        logger.info(
            "Failed authentication attempt recorded",
            identifier=identifier,
            total_attempts=len(self.attempts[identifier])
        )
    
    def get_remaining_attempts(self, identifier: str) -> int:
        """
        Get remaining attempts for identifier
        
        Args:
            identifier: Unique identifier
            
        Returns:
            Number of remaining attempts
        """
        current_time = time.time()
        attempts = self.attempts[identifier]
        
        # Remove old attempts
        while attempts and attempts[0] < current_time - self.window_seconds:
            attempts.popleft()
        
        return max(0, self.max_attempts - len(attempts))
    
    def get_reset_time(self, identifier: str) -> Optional[float]:
        """
        Get timestamp when rate limit will reset
        
        Args:
            identifier: Unique identifier
            
        Returns:
            Timestamp when limit resets, or None if not rate limited
        """
        attempts = self.attempts[identifier]
        if not attempts or len(attempts) < self.max_attempts:
            return None
        
        # Reset time is when oldest attempt expires
        return attempts[0] + self.window_seconds

# Global rate limiters
_auth_rate_limiter = RateLimiter(max_attempts=5, window_seconds=300)  # 5 attempts per 5 minutes
_api_rate_limiter = RateLimiter(max_attempts=100, window_seconds=60)  # 100 requests per minute

def get_auth_rate_limiter() -> RateLimiter:
    """Get authentication rate limiter"""
    return _auth_rate_limiter

def get_api_rate_limiter() -> RateLimiter:
    """Get API rate limiter"""
    return _api_rate_limiter