"""Optimized logging with CloudWatch integration and thread safety."""

import contextlib
import logging
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from functools import wraps
from typing import Any, ParamSpec, TypeVar

from src.models.config import get_config

P = ParamSpec("P")
R = TypeVar("R")


class OptimizedLogger:
    """Thread-safe optimized logger that reduces CloudWatch overhead."""

    _stream_lock: threading.Lock = threading.Lock()
    _batch_lock: threading.Lock = threading.Lock()

    def __init__(self, log_group: str = "/aws/lambda/canvas-demo") -> None:
        self.logger = logging.getLogger(__name__)
        self.log_group = log_group
        self.log_stream = "Canvas-Stream"
        self._cloudwatch_client: Any | None = None
        self._sequence_token: str | None = None
        self.batch_logs: list[dict[str, Any]] = []
        self.batch_size = 10
        self.last_flush = time.time()
        self.flush_interval = 30  # seconds
        self._stream_created = False

    @property
    def cloudwatch_client(self) -> Any | None:
        """Lazy initialization of CloudWatch client via AWSClientManager."""
        if self._cloudwatch_client is None and get_config().is_lambda:
            from src.services.aws_client import AWSClientManager

            self._cloudwatch_client = AWSClientManager().logs_client
            if self._cloudwatch_client:
                self._ensure_log_stream()
        return self._cloudwatch_client

    def _ensure_log_stream(self) -> None:
        """Thread-safe creation of CloudWatch log stream."""
        if self._stream_created or not self._cloudwatch_client:
            return

        with self._stream_lock:
            # Double-check after acquiring lock
            if self._stream_created:
                return

            try:
                self._cloudwatch_client.create_log_stream(
                    logGroupName=self.log_group, logStreamName=self.log_stream
                )
                self._stream_created = True
                self.logger.info(f"Created CloudWatch log stream: {self.log_stream}")
            except self._cloudwatch_client.exceptions.ResourceAlreadyExistsException:
                self._stream_created = True
                self.logger.debug(f"CloudWatch log stream already exists: {self.log_stream}")
            except self._cloudwatch_client.exceptions.ResourceNotFoundException:
                self.logger.error(f"CloudWatch log group not found: {self.log_group}")
            except Exception as e:
                self.logger.error(f"Failed to create log stream {self.log_stream}: {e}")

    _VALID_LEVELS: frozenset[str] = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})

    def log(self, message: str, level: str = "INFO", request_id: str = "") -> None:
        """Log message with optional CloudWatch batching."""
        if level.upper() not in self._VALID_LEVELS:
            level = "INFO"
        prefix = f"[{request_id}] " if request_id else ""
        timestamp = datetime.now(tz=UTC)

        # Always log to standard logger
        getattr(self.logger, level.lower())(f"{prefix}{message}")

        # Batch CloudWatch logs in Lambda environment
        if get_config().is_lambda and self.cloudwatch_client:
            with self._batch_lock:
                self.batch_logs.append(
                    {
                        "timestamp": int(timestamp.timestamp() * 1000),
                        "message": f"[{timestamp}] {prefix}{message}",
                    }
                )

                # Flush if batch is full or time interval exceeded
                if (
                    len(self.batch_logs) >= self.batch_size
                    or time.time() - self.last_flush > self.flush_interval
                ):
                    self._flush_logs_unlocked()

    def _flush_logs(self) -> None:
        """Thread-safe flush of batched logs to CloudWatch."""
        with self._batch_lock:
            self._flush_logs_unlocked()

    def _flush_logs_unlocked(self) -> None:
        """Flush batched logs to CloudWatch (must be called with lock held)."""
        if self.batch_logs and self.cloudwatch_client:
            try:
                kwargs: dict[str, Any] = {
                    "logGroupName": self.log_group,
                    "logStreamName": self.log_stream,
                    "logEvents": sorted(self.batch_logs, key=lambda e: e["timestamp"]),
                }
                if self._sequence_token:
                    kwargs["sequenceToken"] = self._sequence_token
                response = self.cloudwatch_client.put_log_events(**kwargs)
                self._sequence_token = response.get("nextSequenceToken")
                self.batch_logs.clear()
                self.last_flush = time.time()
            except Exception as e:
                self.logger.error(f"Failed to flush logs to CloudWatch: {e}")

    def debug(self, message: str, request_id: str = "") -> None:
        """Log at DEBUG level."""
        self.log(message, "DEBUG", request_id=request_id)

    def info(self, message: str, request_id: str = "") -> None:
        """Log at INFO level."""
        self.log(message, "INFO", request_id=request_id)

    def warning(self, message: str, request_id: str = "") -> None:
        """Log at WARNING level."""
        self.log(message, "WARNING", request_id=request_id)

    def error(self, message: str, request_id: str = "") -> None:
        """Log at ERROR level."""
        self.log(message, "ERROR", request_id=request_id)

    def __del__(self) -> None:
        """Ensure logs are flushed on cleanup."""
        with contextlib.suppress(Exception):
            self._flush_logs()


# Global logger instance
app_logger = OptimizedLogger()


def log_performance(func: Callable[P, R]) -> Callable[P, R]:
    """Decorator to log function performance."""

    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
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
            app_logger.error(f"Failed {func_name} after {duration:.2f}s: {e!s}")
            raise

    return wrapper
