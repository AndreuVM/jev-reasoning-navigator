"""Pruebas de seguridad contra fuga de secretos en variables de entorno y outputs (tests/security/test_secret_leakage.py)."""

import os
from praxeon.policy.sanitizer import DataSanitizer
from praxeon.runtime.sandbox import LocalProcessSandbox


def test_environment_secrets_scrubbed_by_sandbox():
    """Verifica que claves de API y credenciales críticas sean removidas del entorno del proceso hijo."""
    # Inyectar temporalmente en os.environ variables sensibles
    sensitive_keys = {
        "TYPESAFE_API_KEY": "ts-live-99999",
        "GEMINI_API_KEY": "AIzaSyFakeGeminiKey",
        "OPENAI_API_KEY": "sk-proj-supersecretkey",
        "AWS_SECRET_ACCESS_KEY": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        "SSH_AUTH_SOCK": "/tmp/ssh-agent.sock",
    }
    for k, v in sensitive_keys.items():
        os.environ[k] = v

    try:
        sandbox = LocalProcessSandbox()
        clean_env = sandbox._sanitize_environment()

        for k in sensitive_keys:
            assert k not in clean_env, f"La variable sensible '{k}' no fue depurada del proceso hijo."
        
        # Verificar que el marcador de sandbox sí esté presente
        assert clean_env.get("JEV_SANDBOX_ACTIVE") == "1"
    finally:
        for k in sensitive_keys:
            os.environ.pop(k, None)


def test_custom_blocked_vars_scrubbed():
    """Verifica que variables bloqueadas adicionales sean purgadas correctamente."""
    os.environ["INTERNAL_COMPANY_TOKEN"] = "corp-token-12345"
    try:
        sandbox = LocalProcessSandbox(extra_blocked_vars={"INTERNAL_COMPANY_TOKEN"})
        clean_env = sandbox._sanitize_environment()
        assert "INTERNAL_COMPANY_TOKEN" not in clean_env
    finally:
        os.environ.pop("INTERNAL_COMPANY_TOKEN", None)


def test_output_sanitization_masks_credentials():
    """Verifica que DataSanitizer enmascare tokens y credenciales en texto de salida."""
    sanitizer = DataSanitizer()
    raw_output = (
        "Execution output: authenticated using Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9... "
        "and API Key sk-1234567890abcdef1234567890abcdef for user admin@example.com"
    )
    masked = sanitizer.mask_secrets(raw_output)
    assert "sk-1234567890abcdef1234567890abcdef" not in masked
    assert "[MASKED" in masked or "[REDACTED" in masked
