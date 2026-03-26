"""Unit test configuration — auto-marks all tests in this directory."""

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def reset_aws_clients():
    """Reset AWS singleton before and after tests to prevent state leakage."""
    from src.services.aws_client import AWSClientManager

    AWSClientManager._reset()
    yield
    AWSClientManager._reset()
