import json
import time
from typing import Dict, List
from datetime import datetime
from src.models.config import config
from src.services.aws_client import AWSClientManager
from src.utils.logger import app_logger, log_performance
from src.utils.exceptions import RateLimitError, handle_gracefully

class OptimizedRateLimiter:
    """Optimized rate limiter with in-memory caching and S3 fallback"""
    
    def __init__(self):
        self.client_manager = AWSClientManager()
        self.rate_data_cache: Dict[str, List[float]] = {'premium': [], 'standard': []}
        self.cache_expiry = 0
        self.cache_duration = 60  # Cache for 1 minute
        self.s3_key = 'rate-limit/jsonData.json'
        
        # Optimized rate limit message
        self.rate_limit_message = (
            "<div style='text-align: center;'>Rate limit exceeded. "
            "Try again later or use the "
            "<a href='https://docs.aws.amazon.com/bedrock/latest/userguide/playgrounds.html'>Bedrock Playground</a>."
            "</div>"
        )
    
    @log_performance
    def check_rate_limit(self, request_body: str) -> None:
        """Check if request should be rate limited"""
        try:
            # Parse quality from request
            body_dict = json.loads(request_body)
            quality = body_dict.get('imageGenerationConfig', {}).get('quality', 'standard')
            
            # Get current rate data
            rate_data = self._get_rate_data()
            
            # Clean old entries and check limits
            current_time = time.time()
            self._clean_old_entries(rate_data, current_time)
            
            # Calculate current usage
            total_requests = len(rate_data['premium']) * 2 + len(rate_data['standard'])
            
            # Check if adding this request would exceed limits
            request_cost = 2 if quality == 'premium' else 1
            
            if total_requests + request_cost > config.rate_limit:
                app_logger.warning(f"Rate limit exceeded: {total_requests + request_cost} > {config.rate_limit}")
                raise RateLimitError(self.rate_limit_message)
            
            # Add current request to tracking
            rate_data[quality].append(current_time)
            
            # Update cache and S3 asynchronously
            self._update_rate_data(rate_data)
            
            app_logger.debug(f"Rate check passed: {total_requests + request_cost}/{config.rate_limit}")
            
        except json.JSONDecodeError:
            app_logger.error("Invalid JSON in request body for rate limiting")
            raise RateLimitError("Invalid request format")
        except RateLimitError:
            raise
        except Exception as e:
            app_logger.error(f"Rate limiting error: {str(e)}")
            # Don't block requests if rate limiting fails
            pass
    
    def _get_rate_data(self) -> Dict[str, List[float]]:
        """Get rate data with caching"""
        current_time = time.time()
        
        # Check if cache is still valid
        if current_time < self.cache_expiry and self.rate_data_cache:
            app_logger.debug("Using cached rate data")
            return self.rate_data_cache.copy()
        
        # Try to load from S3
        try:
            app_logger.debug("Loading rate data from S3")
            response = self.client_manager.s3_client.get_object(
                Bucket=config.nova_image_bucket,
                Key=self.s3_key
            )
            rate_data = json.loads(response['Body'].read().decode('utf-8'))
            
            # Update cache
            self.rate_data_cache = rate_data
            self.cache_expiry = current_time + self.cache_duration
            
            return rate_data.copy()
            
        except self.client_manager.s3_client.exceptions.NoSuchKey:
            app_logger.info("Rate limit file not found, initializing")
            rate_data = {'premium': [], 'standard': []}
            self.rate_data_cache = rate_data
            self.cache_expiry = current_time + self.cache_duration
            return rate_data.copy()
            
        except Exception as e:
            app_logger.warning(f"Failed to load rate data from S3: {str(e)}")
            # Return cached data even if expired, or empty data
            return self.rate_data_cache.copy() if self.rate_data_cache else {'premium': [], 'standard': []}
    
    def _clean_old_entries(self, rate_data: Dict[str, List[float]], current_time: float) -> None:
        """Remove entries older than 20 minutes"""
        twenty_minutes_ago = current_time - 1200  # 20 minutes in seconds
        
        rate_data['premium'] = [t for t in rate_data.get('premium', []) if t > twenty_minutes_ago]
        rate_data['standard'] = [t for t in rate_data.get('standard', []) if t > twenty_minutes_ago]
    
    @handle_gracefully(log_error=True)
    def _update_rate_data(self, rate_data: Dict[str, List[float]]) -> None:
        """Update rate data in cache and S3"""
        current_time = time.time()
        
        # Update cache
        self.rate_data_cache = rate_data.copy()
        self.cache_expiry = current_time + self.cache_duration
        
        # Update S3 asynchronously (don't block on S3 failures)
        try:
            self.client_manager.s3_client.put_object(
                Bucket=config.nova_image_bucket,
                Key=self.s3_key,
                Body=json.dumps(rate_data),
                ContentType='application/json'
            )
            app_logger.debug("Rate data updated in S3")
        except Exception as e:
            app_logger.warning(f"Failed to update rate data in S3: {str(e)}")
            # Don't fail the operation if S3 update fails
    
    def get_current_usage(self) -> Dict[str, int]:
        """Get current rate limit usage for monitoring"""
        try:
            rate_data = self._get_rate_data()
            current_time = time.time()
            self._clean_old_entries(rate_data, current_time)
            
            premium_count = len(rate_data.get('premium', []))
            standard_count = len(rate_data.get('standard', []))
            total_requests = premium_count * 2 + standard_count
            
            return {
                'premium_requests': premium_count,
                'standard_requests': standard_count,
                'total_usage': total_requests,
                'limit': config.rate_limit,
                'remaining': max(0, config.rate_limit - total_requests)
            }
        except Exception as e:
            app_logger.error(f"Failed to get current usage: {str(e)}")
            return {'error': str(e)}

# Global rate limiter instance
rate_limiter = OptimizedRateLimiter()