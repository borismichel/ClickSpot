"""Deployment guarantees asserted against the Compose manifest.

These are the four-container invariants that were each broken by a manifest
written for a single-process mental model — one host, one home directory, one
loopback interface. They are asserted here, not in a Docker test, because the
manifest alone decides them: PyYAML resolves the merge keys the file uses to
share its environment block, so the effective per-service environment is
available without a daemon.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

MANIFEST = Path(__file__).resolve().parents[1] / "docker-compose.yml"

CONFIG_VOLUME = "clickspot_config"
CONFIG_MOUNT_PATH = "/home/app/.clickspot"


@pytest.fixture(scope="module")
def manifest() -> dict:
    return yaml.safe_load(MANIFEST.read_text())


@pytest.fixture(scope="module")
def services(manifest) -> dict:
    return manifest["services"]


def _mount_path(service: dict, volume: str) -> str | None:
    """Container-side path a named volume is mounted at, or None if unmounted."""
    for entry in service.get("volumes") or []:
        source, _, rest = str(entry).partition(":")
        if source == volume:
            return rest.split(":")[0]
    return None


def _override_default(value: str) -> str | None:
    """The default of a `${VAR:-default}` interpolation, or None if not one."""
    m = re.fullmatch(r"\$\{(\w+):-(.*)\}", value)
    return m.group(2) if m else None


# ---------------------------------------------------------------------------
# Demo seeding is opt-in
# ---------------------------------------------------------------------------


def test_seed_service_is_gated_behind_the_demo_profile(services):
    """A bare `docker compose up` must schedule no seed container — unconditional
    seeding mixed synthetic records into real portals on every restart."""
    assert services["seed"].get("profiles") == ["demo"]


def test_no_other_service_is_profile_gated(services):
    """Profiled services are omitted from the default service set, so anything
    else carrying a profile would silently drop out of a bare startup."""
    profiled = {name for name, svc in services.items() if svc.get("profiles")}
    assert profiled == {"seed"}


# ---------------------------------------------------------------------------
# One customer config, shared by the backend and the orchestrator
# ---------------------------------------------------------------------------


def test_backend_and_dagster_share_the_customer_config_volume(services):
    """The Settings API writes the extraction block; Dagster composes the silver
    column lists from it. Unshared, each container kept a private copy and
    neither side's writes were ever visible to the other."""
    backend = _mount_path(services["backend"], CONFIG_VOLUME)
    dagster = _mount_path(services["dagster"], CONFIG_VOLUME)
    assert backend == CONFIG_MOUNT_PATH
    assert dagster == CONFIG_MOUNT_PATH


def test_customer_config_lives_on_a_named_volume(manifest):
    """Named, so settings survive container recreation rather than being lost
    with the writable layer on a routine restart or image pull."""
    assert CONFIG_VOLUME in manifest["volumes"]


# ---------------------------------------------------------------------------
# The backend can reach the orchestrator
# ---------------------------------------------------------------------------


def test_dagster_graphql_url_addresses_the_orchestrator_by_service_name(services):
    """The app default targets loopback, which is correct from source and dead
    inside the backend container — Dagster is a separate service here."""
    for name in ("backend", "dagster"):
        value = services[name]["environment"]["DAGSTER_GRAPHQL_URL"]
        default = _override_default(value)
        assert default == "http://dagster:8194/graphql", name
        assert "localhost" not in default and "127.0.0.1" not in default


@pytest.mark.parametrize("var", ["DAGSTER_GRAPHQL_URL", "CLICKSPOT_TRUSTED_HOSTS"])
def test_deployment_overrides_stay_overridable_from_the_host(services, var):
    """Non-default network layouts (or an externally hosted orchestrator) must
    stay reachable without editing the manifest."""
    value = services["backend"]["environment"][var]
    assert _override_default(value) is not None, f"{var} is not a ${{VAR:-default}} interpolation"


# ---------------------------------------------------------------------------
# Health is a signal you can trust
# ---------------------------------------------------------------------------


def test_frontend_health_probe_addresses_the_ipv4_loopback(services):
    """nginx `listen 80;` binds IPv4 only while `localhost` resolves to ::1
    first in that image, so a hostname-based probe never passed. The probe lives
    in the frontend image, not the manifest — assert it where it is written."""
    dockerfile = MANIFEST.parent / "frontend" / "Dockerfile"
    healthcheck = [
        line for line in dockerfile.read_text().splitlines()
        if "HEALTHCHECK" in line or line.strip().startswith("CMD")
    ]
    probe = "\n".join(healthcheck)
    assert "127.0.0.1" in probe
    assert "localhost" not in probe
