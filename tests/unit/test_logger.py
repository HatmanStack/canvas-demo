"""Unit tests for OptimizedLogger."""

import logging

from src.utils.logger import OptimizedLogger


class TestLoggerRequestId:
    """Tests for request_id propagation in logger."""

    def test_log_with_request_id_prefixes_message(self, caplog):
        """Log messages include [request_id] prefix when provided."""
        logger = OptimizedLogger()
        with caplog.at_level(logging.INFO):
            logger.log("test message", level="INFO", request_id="abc123")

        assert "[abc123]" in caplog.text
        assert "test message" in caplog.text

    def test_log_without_request_id_no_prefix(self, caplog):
        """Log messages have no prefix when request_id is empty."""
        logger = OptimizedLogger()
        with caplog.at_level(logging.INFO):
            logger.log("test message", level="INFO")

        assert "[" not in caplog.text
        assert "test message" in caplog.text

    def test_convenience_methods_accept_request_id(self, caplog):
        """info/debug/warning/error accept and pass through request_id."""
        logger = OptimizedLogger()
        with caplog.at_level(logging.DEBUG):
            logger.info("info msg", request_id="req1")
            logger.debug("debug msg", request_id="req2")
            logger.warning("warn msg", request_id="req3")
            logger.error("err msg", request_id="req4")

        assert "[req1]" in caplog.text
        assert "[req2]" in caplog.text
        assert "[req3]" in caplog.text
        assert "[req4]" in caplog.text


class TestLoggerLevelValidation:
    """Tests for log level validation."""

    def test_invalid_level_falls_back_to_info(self, caplog):
        """Invalid log level falls back to INFO instead of raising."""
        logger = OptimizedLogger()
        with caplog.at_level(logging.INFO):
            logger.log("test message", level="INVALID")

        # Should not raise, message should be logged at INFO
        assert "test message" in caplog.text

    def test_valid_levels_work(self, caplog):
        """All valid log levels work without falling back."""
        logger = OptimizedLogger()
        with caplog.at_level(logging.DEBUG):
            for level in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
                logger.log(f"{level} message", level=level)

        for level in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            assert f"{level} message" in caplog.text
