import time
from datetime import datetime
from typing import Any

from src.models.config import config
from src.services.aws_client import AWSClientManager
from src.services.rate_limiter import rate_limiter
from src.utils.exceptions import handle_gracefully
from src.utils.logger import app_logger


class HealthCheck:
    """Health check and monitoring for the Canvas Demo application"""

    def __init__(self) -> None:
        self.client_manager = AWSClientManager()
        self.start_time = time.time()
        self.request_count = 0
        self.error_count = 0

    def increment_request(self):
        """Increment request counter"""
        self.request_count += 1

    def increment_error(self):
        """Increment error counter"""
        self.error_count += 1

    @handle_gracefully(default_return={"status": "error", "message": "Health check failed"})
    def get_health_status(self) -> dict[str, Any]:
        """Get comprehensive health status"""
        current_time = time.time()
        uptime_seconds = current_time - self.start_time

        # Basic health info
        health_info = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "uptime_seconds": round(uptime_seconds, 2),
            "uptime_human": self._format_uptime(uptime_seconds),
            "environment": "lambda" if config.is_lambda else "local",
            "version": "2.0.0-optimized",
        }

        # Service checks
        services = self._check_services()
        health_info["services"] = services

        # Performance metrics
        metrics = self._get_metrics()
        health_info["metrics"] = metrics

        # Rate limiting status
        rate_status = rate_limiter.get_current_usage()
        health_info["rate_limiting"] = rate_status

        # Overall health determination
        if any(service["status"] != "healthy" for service in services.values()):
            health_info["status"] = "degraded"

        if self.error_count / max(self.request_count, 1) > 0.1:  # 10% error rate
            health_info["status"] = "unhealthy"

        return health_info

    def _check_services(self) -> dict[str, dict[str, Any]]:
        """Check status of dependent services"""
        services = {}

        # Check Bedrock connectivity
        services["bedrock"] = self._check_bedrock()

        # Check S3 connectivity
        services["s3"] = self._check_s3()

        # Check configuration
        services["configuration"] = self._check_configuration()

        return services

    @handle_gracefully(default_return={"status": "error", "message": "Connection check failed"})
    def _check_bedrock(self) -> dict[str, Any]:
        """Check Bedrock service connectivity"""
        try:
            # Simple connectivity test - just check if client can be created
            _ = self.client_manager.bedrock_client
            return {
                "status": "healthy",
                "message": "Bedrock client initialized successfully",
                "region": config.aws_region,
            }
        except Exception as e:
            app_logger.error(f"Bedrock health check failed: {e!s}")
            return {"status": "unhealthy", "message": f"Bedrock connection failed: {e!s}"}

    @handle_gracefully(default_return={"status": "error", "message": "Connection check failed"})
    def _check_s3(self) -> dict[str, Any]:
        """Check S3 service connectivity"""
        try:
            # Test S3 connectivity by checking bucket access
            client = self.client_manager.s3_client
            client.head_bucket(Bucket=config.nova_image_bucket)
            return {
                "status": "healthy",
                "message": "S3 bucket accessible",
                "bucket": config.nova_image_bucket,
                "region": config.bucket_region,
            }
        except Exception as e:
            app_logger.error(f"S3 health check failed: {e!s}")
            return {"status": "unhealthy", "message": f"S3 connection failed: {e!s}"}

    def _check_configuration(self) -> dict[str, Any]:
        """Check application configuration"""
        issues = []

        # Check required environment variables
        if not config.aws_access_key_id:
            issues.append("Missing AWS_ACCESS_KEY_ID")

        if not config.aws_secret_access_key:
            issues.append("Missing AWS_SECRET_ACCESS_KEY")

        if not config.nova_image_bucket:
            issues.append("Missing NOVA_IMAGE_BUCKET")

        if config.enable_nsfw_check and not config.hf_token:
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
            "total_errors": self.error_count,
            "error_rate": round(self.error_count / max(self.request_count, 1), 4),
            "requests_per_second": round(self.request_count / max(uptime_seconds, 1), 4),
            "memory_info": self._get_memory_info(),
        }

    @handle_gracefully(default_return={"status": "unavailable"})
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


# Global health checker instance
health_checker = HealthCheck()
