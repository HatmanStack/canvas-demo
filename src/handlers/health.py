import threading
import time
from datetime import datetime
from typing import Any

from src.models.config import get_config
from src.services.aws_client import AWSClientManager
from src.services.rate_limiter import get_rate_limiter
from src.utils.logger import app_logger


class HealthCheck:
    """Health check and monitoring for the Canvas Demo application"""

    def __init__(self) -> None:
        self.client_manager = AWSClientManager()
        self.start_time = time.time()
        self._counter_lock = threading.Lock()
        self.request_count = 0

    def increment_request(self) -> None:
        """Increment request counter (thread-safe)."""
        with self._counter_lock:
            self.request_count += 1

    def get_health_status(self) -> dict[str, Any]:
        """Get comprehensive health status"""
        try:
            current_time = time.time()
            uptime_seconds = current_time - self.start_time

            # Basic health info
            health_info = {
                "status": "healthy",
                "timestamp": datetime.now().isoformat(),
                "uptime_seconds": round(uptime_seconds, 2),
                "uptime_human": self._format_uptime(uptime_seconds),
                "environment": "lambda" if get_config().is_lambda else "local",
                "version": "2.0.0-optimized",
            }

            # Service checks
            services = self._check_services()
            health_info["services"] = services

            # Performance metrics
            metrics = self._get_metrics()
            health_info["metrics"] = metrics

            # Rate limiting status
            rate_status = get_rate_limiter().get_current_usage()
            health_info["rate_limiting"] = rate_status

            # Overall health determination
            if any(service["status"] != "healthy" for service in services.values()):
                health_info["status"] = "degraded"

            return health_info
        except Exception:
            app_logger.logger.exception("Health check failed")
            return {"status": "error", "message": "Health check failed"}

    def _check_services(self) -> dict[str, dict[str, Any]]:
        """Check status of dependent services, using parallel I/O when possible."""
        executor = self.client_manager.executor
        if executor:
            bedrock_future = executor.submit(self._check_bedrock)
            s3_future = executor.submit(self._check_s3)
            return {
                "bedrock": bedrock_future.result(timeout=10),
                "s3": s3_future.result(timeout=10),
                "configuration": self._check_configuration(),
            }
        return {
            "bedrock": self._check_bedrock(),
            "s3": self._check_s3(),
            "configuration": self._check_configuration(),
        }

    def _check_bedrock(self) -> dict[str, Any]:
        """Check Bedrock service connectivity"""
        try:
            # Simple connectivity test - just check if client can be created
            _ = self.client_manager.bedrock_client
            return {
                "status": "healthy",
                "message": "Bedrock client initialized successfully",
                "region": get_config().aws_region,
            }
        except Exception as e:
            app_logger.error(f"Bedrock health check failed: {e!s}")
            return {"status": "unhealthy", "message": f"Bedrock connection failed: {e!s}"}

    def _check_s3(self) -> dict[str, Any]:
        """Check S3 service connectivity"""
        try:
            # Test S3 connectivity by checking bucket access
            client = self.client_manager.s3_client
            client.head_bucket(Bucket=get_config().nova_image_bucket)
            return {
                "status": "healthy",
                "message": "S3 bucket accessible",
                "bucket": get_config().nova_image_bucket,
                "region": get_config().bucket_region,
            }
        except Exception as e:
            app_logger.error(f"S3 health check failed: {e!s}")
            return {"status": "unhealthy", "message": f"S3 connection failed: {e!s}"}

    def _check_configuration(self) -> dict[str, Any]:
        """Check application configuration"""
        issues = []

        # Check required environment variables
        if not get_config().aws_access_key_id:
            issues.append("Missing AWS_ACCESS_KEY_ID")

        if not get_config().aws_secret_access_key:
            issues.append("Missing AWS_SECRET_ACCESS_KEY")

        if not get_config().nova_image_bucket:
            issues.append("Missing NOVA_IMAGE_BUCKET")

        if get_config().enable_nsfw_check and not get_config().hf_token:
            issues.append("NSFW check enabled but HF_TOKEN missing")

        if issues:
            return {
                "status": "unhealthy",
                "message": "Configuration issues detected",
                "issues": issues,
            }
        else:
            return {"status": "healthy", "message": "Configuration valid"}

    def _get_metrics(self) -> dict[str, Any]:
        """Get performance metrics"""
        current_time = time.time()
        uptime_seconds = current_time - self.start_time

        return {
            "total_requests": self.request_count,
            "requests_per_second": round(self.request_count / max(uptime_seconds, 1), 4),
            "memory_info": self._get_memory_info(),
        }

    def _get_memory_info(self) -> dict[str, Any]:
        """Get memory usage information"""
        try:
            import psutil

            process = psutil.Process()
            memory_info = process.memory_info()

            return {
                "rss_mb": round(memory_info.rss / 1024 / 1024, 2),
                "vms_mb": round(memory_info.vms / 1024 / 1024, 2),
                "percent": round(process.memory_percent(), 2),
            }
        except ImportError:
            return {"status": "psutil not available"}
        except Exception as e:
            return {"status": f"error: {e!s}"}

    def _format_uptime(self, seconds: float) -> str:
        """Format uptime in human readable format"""
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            return f"{int(seconds // 60)}m {int(seconds % 60)}s"
        else:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            return f"{hours}h {minutes}m"

    def get_simple_status(self) -> dict[str, str]:
        """Get simple health status for quick checks"""
        try:
            full_status = self.get_health_status()
            return {"status": full_status["status"], "timestamp": full_status["timestamp"]}
        except Exception as e:
            return {"status": "error", "message": str(e), "timestamp": datetime.now().isoformat()}


_health_checker: HealthCheck | None = None


def get_health_checker() -> HealthCheck:
    """Get or create the health checker singleton."""
    global _health_checker
    if _health_checker is None:
        _health_checker = HealthCheck()
    return _health_checker


def reset_health_checker() -> None:
    """Reset health checker for testing. Not for production use."""
    global _health_checker
    _health_checker = None
