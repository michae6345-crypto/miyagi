"""Setup health rows (server.orchestrator.health), pure: an old companion reads not ok with the install fix."""

from __future__ import annotations

import pytest

from server.orchestrator import health


def _companion(**probes) -> dict:
    base = {"screen": True, "accessibility": True, "vscode": True, "keys": True}
    rows = health.from_probes({**base, **probes})
    return next(r for r in rows if r["id"] == "companion")


@pytest.mark.parametrize("version", ["0.0.6", "0.0.1", "0.0", "0.0.6-beta"])
def test_old_companion_is_missing_with_install_fix(version):
    row = _companion(companion=True, companionVersion=version)
    assert row["state"] == health.MISSING
    assert row["fix"] == "install_companion" and row["outdated"] is True
    assert row["version"] == version and "running" not in row


def test_old_companion_stays_missing_when_a_window_answers():
    row = _companion(companion=True, companionRunning=True, companionVersion="0.0.5")
    assert row["state"] == health.MISSING and row["fix"] == "install_companion"


@pytest.mark.parametrize("version", ["0.0.7", "0.0.8", "0.1", "0.10.0", "1.0.0"])
def test_current_companion_is_ok(version):
    row = _companion(companion=True, companionRunning=True, companionVersion=version)
    assert row["state"] == health.OK and "fix" not in row and "outdated" not in row
    assert row["running"] is True


def test_unknown_version_is_not_called_outdated():
    row = _companion(companion=True, companionVersion=None)
    assert row["state"] == health.OK and "fix" not in row
    assert not health.companion_outdated("") and not health.companion_outdated("beta")


def test_not_installed_keeps_its_fixes():
    assert _companion(companion=False)["fix"] == "install_companion"
    assert _companion(companion=False, vscode=False)["fix"] == "get_vscode"


def test_outdated_counts_against_ready():
    snap = health.summarize(health.from_probes({"screen": True, "accessibility": True, "vscode": True,
                                                "companion": True, "companionVersion": "0.0.6", "keys": True}))
    assert snap["ready"] == snap["total"] - 1


def test_payload_fits_the_health_contract():
    from server.orchestrator.main import contract_health
    from shared.contracts.events import engine_message

    snap = health.summarize(health.from_probes({"companion": True, "companionVersion": "0.0.6"}))
    row = next(r for r in engine_message("health", contract_health(snap))["payload"]["items"] if r["id"] == "companion")
    assert row["state"] == "missing" and row["fix"] == "install_companion" and row["outdated"] is True
