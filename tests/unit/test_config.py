"""Tests for config factory function pattern."""

import os
from unittest.mock import patch

import pytest


class TestConfigFactory:
    """Tests for get_config() lazy factory and reset_config()."""

    def test_import_does_not_trigger_config_init(self):
        """Importing a src module without env vars does not raise."""
        # This should not raise even without valid AWS credentials
        # because config is no longer created at import time
        import src.models.config  # noqa: F401

    def test_get_config_returns_app_config(self):
        """get_config() returns an AppConfig instance."""
        from src.models.config import AppConfig, get_config, reset_config

        reset_config()
        config = get_config()
        assert isinstance(config, AppConfig)

    def test_get_config_is_singleton(self):
        """Calling get_config() twice returns the same object."""
        from src.models.config import get_config, reset_config

        reset_config()
        config1 = get_config()
        config2 = get_config()
        assert config1 is config2

    def test_reset_config_clears_singleton(self):
        """reset_config() causes get_config() to create a new instance."""
        from src.models.config import get_config, reset_config

        reset_config()
        config1 = get_config()
        reset_config()
        config2 = get_config()
        assert config1 is not config2

    def test_get_config_reads_env_vars_at_call_time(self):
        """Config reads env vars when get_config() is called, not at import time."""
        from src.models.config import get_config, reset_config

        reset_config()
        with patch.dict(os.environ, {"NOVA_IMAGE_BUCKET": "bucket-a"}):
            config_a = get_config()
            assert config_a.nova_image_bucket == "bucket-a"

        reset_config()
        with patch.dict(os.environ, {"NOVA_IMAGE_BUCKET": "bucket-b"}):
            config_b = get_config()
            assert config_b.nova_image_bucket == "bucket-b"

    def test_get_config_without_credentials_raises(self):
        """get_config() without required env vars raises ConfigurationError."""
        from src.models.config import reset_config

        reset_config()
        with patch.dict(
            os.environ,
            {
                "AWS_ACCESS_KEY_ID": "",
                "AWS_SECRET_ACCESS_KEY": "",
                "AMP_AWS_ID": "",
                "AMP_AWS_SECRET": "",
                "AWS_ID": "",
                "AWS_SECRET": "",
                "NOVA_IMAGE_BUCKET": "test-bucket",
            },
            clear=False,
        ):
            from src.models.config import get_config
            from src.models.config import reset_config as rc2

            rc2()
            from src.utils.exceptions import ConfigurationError

            with pytest.raises(ConfigurationError, match="AWS credentials"):
                get_config()

        # Restore valid state
        reset_config()
