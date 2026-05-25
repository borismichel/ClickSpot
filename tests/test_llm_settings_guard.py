"""Tests for the loopback / CLICKSPOT_TRUSTED_HOSTS guard on settings writes.

The Settings drawer endpoints (LLM key + Claude OAuth token writes) must only
be reachable from the local host. Behind Docker's port-forwarding the backend
sees the request from the bridge gateway rather than 127.0.0.1, so the guard
also honours CLICKSPOT_TRUSTED_HOSTS — the env var the bundled demo sets so the
in-app key form works out of the box. These tests pin both halves: loopback is
always allowed, and the override accepts explicit IPs, hostnames, and CIDRs.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api import llm_routes


def _request(host: str | None):
    """Minimal stand-in for a Starlette Request with a .client.host."""
    client = SimpleNamespace(host=host) if host is not None else None
    return SimpleNamespace(client=client)


# --- loopback is always trusted, no configuration --------------------------


@pytest.mark.parametrize("host", ["127.0.0.1", "127.0.0.5", "::1", "localhost"])
def test_loopback_always_allowed(host, monkeypatch):
    monkeypatch.delenv("CLICKSPOT_TRUSTED_HOSTS", raising=False)
    # Should not raise.
    llm_routes._require_localhost(_request(host))


def test_ipv4_mapped_loopback_allowed(monkeypatch):
    monkeypatch.delenv("CLICKSPOT_TRUSTED_HOSTS", raising=False)
    llm_routes._require_localhost(_request("::ffff:127.0.0.1"))


# --- non-loopback rejected unless explicitly trusted -----------------------


def test_bridge_gateway_rejected_by_default(monkeypatch):
    monkeypatch.delenv("CLICKSPOT_TRUSTED_HOSTS", raising=False)
    with pytest.raises(HTTPException) as exc:
        llm_routes._require_localhost(_request("172.18.0.1"))
    assert exc.value.status_code == 403
    # The message must name the override and the rejected host.
    assert "CLICKSPOT_TRUSTED_HOSTS" in exc.value.detail
    assert "172.18.0.1" in exc.value.detail


def test_missing_client_rejected(monkeypatch):
    monkeypatch.delenv("CLICKSPOT_TRUSTED_HOSTS", raising=False)
    with pytest.raises(HTTPException):
        llm_routes._require_localhost(_request(None))


# --- CLICKSPOT_TRUSTED_HOSTS override --------------------------------------


def test_cidr_override_allows_bridge_range(monkeypatch):
    monkeypatch.setenv("CLICKSPOT_TRUSTED_HOSTS", "172.16.0.0/12")
    # Demo default: any address in the Docker bridge range is accepted.
    llm_routes._require_localhost(_request("172.18.0.1"))
    llm_routes._require_localhost(_request("172.31.255.254"))


def test_cidr_override_does_not_leak_outside_range(monkeypatch):
    monkeypatch.setenv("CLICKSPOT_TRUSTED_HOSTS", "172.16.0.0/12")
    # A common LAN range stays blocked under the demo default.
    with pytest.raises(HTTPException):
        llm_routes._require_localhost(_request("192.168.1.10"))


def test_explicit_ip_override(monkeypatch):
    monkeypatch.setenv("CLICKSPOT_TRUSTED_HOSTS", "10.8.0.3")
    llm_routes._require_localhost(_request("10.8.0.3"))
    with pytest.raises(HTTPException):
        llm_routes._require_localhost(_request("10.8.0.4"))


def test_hostname_override(monkeypatch):
    monkeypatch.setenv("CLICKSPOT_TRUSTED_HOSTS", "proxy.internal, 172.16.0.0/12")
    llm_routes._require_localhost(_request("proxy.internal"))


def test_blank_and_whitespace_entries_ignored(monkeypatch):
    monkeypatch.setenv("CLICKSPOT_TRUSTED_HOSTS", " , ,10.0.0.1, ")
    llm_routes._require_localhost(_request("10.0.0.1"))
    with pytest.raises(HTTPException):
        llm_routes._require_localhost(_request("10.0.0.2"))


# --- end-to-end through the real PUT /settings route -----------------------


@pytest.fixture
def client(tmp_path, monkeypatch):
    import app.llm.config as config

    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")

    from fastapi.testclient import TestClient
    from app.main import app

    # No context manager: skip the lifespan startup (it reaches for ClickHouse).
    return TestClient(app)


def test_put_settings_rejected_from_untrusted_host(client, monkeypatch):
    # TestClient presents client host "testclient", which is not loopback.
    monkeypatch.delenv("CLICKSPOT_TRUSTED_HOSTS", raising=False)
    res = client.put("/api/v1/settings", json={"anthropic_api_key": "sk-ant-test"})
    assert res.status_code == 403


def test_put_settings_persists_key_when_host_trusted(client, monkeypatch, tmp_path):
    import app.llm.config as config

    monkeypatch.setenv("CLICKSPOT_TRUSTED_HOSTS", "testclient")
    res = client.put("/api/v1/settings", json={"anthropic_api_key": "sk-ant-xyz"})
    assert res.status_code == 200, res.text
    assert config.load_config()["anthropic_api_key"] == "sk-ant-xyz"
