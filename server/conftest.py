"""Every server test: the Tiger spool is a temp folder, never ~/.miyagi/tiger-spool. The engine uploads that spool to
Tiger Data on its next connection, so a test's sessions and runs would show up on /stats as real learning events and
real learner runs."""

import os

import pytest


@pytest.fixture(autouse=True, scope="session")
def _private_tiger_spool(tmp_path_factory):
    old = os.environ.get("TUT_SPOOL_DIR")
    os.environ["TUT_SPOOL_DIR"] = str(tmp_path_factory.mktemp("tiger-spool"))
    from server.checks import tiger

    tiger._writer = None  # the writer reads TUT_SPOOL_DIR when it is made
    yield
    tiger._writer = None
    if old is None:
        os.environ.pop("TUT_SPOOL_DIR", None)
    else:
        os.environ["TUT_SPOOL_DIR"] = old
