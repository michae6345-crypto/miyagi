def pytest_configure(config):
    config.addinivalue_line("markers", "demo_rehearsal: the judged Demo end to end on a private engine (~1.5 min)")
