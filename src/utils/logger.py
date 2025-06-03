import logging
import time
import boto3
from functools import wraps
from datetime import datetime
from typing import Optional
from src.models.config import config

class OptimizedLogger:
    """Optimized logger that reduces CloudWatch overhead"""
    
    def __init__(self, log_group: str = '/aws/lambda/canvas-demo'):
        self.logger = logging.getLogger(__name__)
        self.log_group = log_group
        self.log_stream = 'Canvas-Stream'
        self._cloudwatch_client: Optional[boto3.client] = None
        self.batch_logs = []
        self.batch_size = 10
        self.last_flush = time.time()
        self.flush_interval = 30  # seconds
        self._stream_created = False
        
    @property
    def cloudwatch_client(self):
        """Lazy initialization of CloudWatch client"""
        if self._cloudwatch_client is None and config.is_lambda:
            self._cloudwatch_client = boto3.client('logs', region_name=config.aws_region)
            self._ensure_log_stream()
        return self._cloudwatch_client
    
    def _ensure_log_stream(self):
        """Ensure the Canvas-Stream log stream exists"""
        if self._stream_created or not self._cloudwatch_client:
            return
            
        try:
            # Try to describe the log stream
            self._cloudwatch_client.describe_log_streams(
                logGroupName=self.log_group,
                logStreamNamePrefix=self.log_stream
            )
            self._stream_created = True
        except self._cloudwatch_client.exceptions.ResourceNotFoundException:
            try:
                # Create the log stream if it doesn't exist
                self._cloudwatch_client.create_log_stream(
                    logGroupName=self.log_group,
                    logStreamName=self.log_stream
                )
                self._stream_created = True
                self.logger.info(f"Created CloudWatch log stream: {self.log_stream}")
            except Exception as e:
                self.logger.error(f"Failed to create log stream {self.log_stream}: {e}")
        except Exception as e:
            self.logger.error(f"Error checking log stream {self.log_stream}: {e}")
    
    def log(self, message: str, level: str = 'INFO'):
        """Optimized logging with batching for CloudWatch"""
        timestamp = datetime.now()
        
        # Always log to standard logger
        getattr(self.logger, level.lower())(message)
        
        # Batch CloudWatch logs in Lambda environment
        if config.is_lambda and self.cloudwatch_client:
            self.batch_logs.append({
                'timestamp': int(timestamp.timestamp() * 1000),
                'message': f"[{timestamp}] {message}"
            })
            
            # Flush if batch is full or time interval exceeded
            if (len(self.batch_logs) >= self.batch_size or 
                time.time() - self.last_flush > self.flush_interval):
                self._flush_logs()
    
    def _flush_logs(self):
        """Flush batched logs to CloudWatch"""
        if self.batch_logs and self.cloudwatch_client:
            try:
                self.cloudwatch_client.put_log_events(
                    logGroupName=self.log_group,
                    logStreamName=self.log_stream,
                    logEvents=self.batch_logs
                )
                self.batch_logs.clear()
                self.last_flush = time.time()
            except Exception as e:
                self.logger.error(f"Failed to flush logs to CloudWatch: {e}")
    
    def debug(self, message: str):
        """Debug level logging"""
        self.log(message, 'DEBUG')
    
    def info(self, message: str):
        """Info level logging"""
        self.log(message, 'INFO')
    
    def warning(self, message: str):
        """Warning level logging"""
        self.log(message, 'WARNING')
    
    def error(self, message: str):
        """Error level logging"""
        self.log(message, 'ERROR')
    
    def __del__(self):
        """Ensure logs are flushed on cleanup"""
        self._flush_logs()

# Global logger instance
app_logger = OptimizedLogger()

def log_performance(func):
    """Decorator to log function performance"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        func_name = f"{func.__module__}.{func.__name__}"
        
        app_logger.debug(f"Starting {func_name}")
        try:
            result = func(*args, **kwargs)
            duration = time.time() - start_time
            app_logger.info(f"Completed {func_name} in {duration:.2f}s")
            return result
        except Exception as e:
            duration = time.time() - start_time
            app_logger.error(f"Failed {func_name} after {duration:.2f}s: {str(e)}")
            raise
    
    return wrapper