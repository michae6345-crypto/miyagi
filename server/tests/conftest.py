import pytest

TEST_CLOUD_HOST = "cloud.example.test"  # the offline cloud tests' proxy host (test_cloud_config, test_cloud_heal)


def pytest_configure(config):
    config.addinivalue_line("markers", "demo_rehearsal: the judged Demo end to end on a private engine (~1.5 min)")


@pytest.fixture(autouse=True)
def _test_cloud_host(monkeypatch):
    """The cloud pin (server/config.py cloud_host_allowed) has no wildcard, so the offline cloud tests add their own
    reserved host to CLOUD_HOSTS here, the way MIYAGI_CLOUD_HOSTS would at engine start. Nothing else is allowed."""
    from server import config

    monkeypatch.setattr(config, "CLOUD_HOSTS", config.CLOUD_HOSTS | {TEST_CLOUD_HOST})
