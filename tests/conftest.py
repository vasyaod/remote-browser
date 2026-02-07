"""
Pytest configuration and fixtures.
"""
import pytest
import subprocess
import os


def pytest_configure(config):
    """Configure pytest markers."""
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )

