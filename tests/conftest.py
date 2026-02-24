"""Shared pytest configuration for co-vibe tests."""


def pytest_configure(config):
    config.addinivalue_line("markers", "integration: marks tests that call real APIs (deselect with '-m \"not integration\"')")
    config.addinivalue_line("markers", "timeout: set per-test timeout in seconds")
