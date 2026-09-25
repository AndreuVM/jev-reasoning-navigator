"""Pruebas de seguridad contra path traversal, symlink escapes y violaciones de filesystem (tests/security/test_path_traversal_and_symlinks.py)."""

import os
import tempfile
import pytest
from jev_navigator.runtime.sandbox import LocalProcessSandbox, SandboxViolation


@pytest.fixture
def workspace_env():
    with tempfile.TemporaryDirectory() as ws_dir:
        # Archivo legítimo dentro del workspace
        legit_file = os.path.join(ws_dir, "legit.txt")
        with open(legit_file, "w", encoding="utf-8") as f:
            f.write("contenido seguro")
        sandbox = LocalProcessSandbox(workspace_root=ws_dir)
        yield ws_dir, sandbox


def test_relative_path_traversal_blocked(workspace_env):
    """Verifica que rutas con ../../ intentando salir del workspace sean interceptadas."""
    ws_dir, sandbox = workspace_env
    traversal_paths = [
        "../../etc/passwd",
        "subdir/../../../secret.env",
        "subdir/../../outside.txt",
    ]
    for path in traversal_paths:
        with pytest.raises(SandboxViolation) as exc_info:
            sandbox._validate_path_containment(path)
        assert "Evasión de ruta" in str(exc_info.value) or "fuera del workspace" in str(exc_info.value)

        # También verificar que el método de alto nivel read_file lo capture y reporte
        res = sandbox.read_file(path)
        assert res.is_error is True
        assert "Evasión de ruta" in res.output or "fuera del workspace" in res.output


def test_absolute_path_escape_blocked(workspace_env):
    """Verifica que rutas absolutas fuera del workspace sean rechazadas."""
    ws_dir, sandbox = workspace_env
    # Crear un archivo externo fuera de ws_dir
    with tempfile.NamedTemporaryFile(delete=False) as external_file:
        ext_path = external_file.name

    try:
        with pytest.raises(SandboxViolation) as exc_info:
            sandbox._validate_path_containment(ext_path)
        assert "fuera del workspace" in str(exc_info.value)

        res = sandbox.read_file(ext_path)
        assert res.is_error is True
        assert "fuera del workspace" in res.output
    finally:
        if os.path.exists(ext_path):
            os.remove(ext_path)


def test_symlink_traversal_escape_blocked(workspace_env):
    """Verifica que symlinks creados dentro del workspace apuntando al exterior sean interceptados."""
    ws_dir, sandbox = workspace_env
    # Crear archivo externo sensible
    with tempfile.NamedTemporaryFile(delete=False) as ext_target:
        ext_target.write(b"EXTERIOR_SECRET")
        ext_target_path = ext_target.name

    symlink_path = os.path.join(ws_dir, "link_to_external")
    try:
        try:
            os.symlink(ext_target_path, symlink_path)
        except (OSError, NotImplementedError):
            pytest.skip("Symlink creation not permitted in this OS environment without admin rights")

        with pytest.raises(SandboxViolation) as exc_info:
            sandbox._validate_path_containment("link_to_external")
        assert "Evasión de ruta" in str(exc_info.value) or "fuera del workspace" in str(exc_info.value)

        res = sandbox.read_file("link_to_external")
        assert res.is_error is True
        assert "Evasión de ruta" in res.output or "fuera del workspace" in res.output
    finally:
        if os.path.exists(ext_target_path):
            os.remove(ext_target_path)


def test_edit_file_traversal_blocked(workspace_env):
    """Verifica que edit_file no permita escribir fuera de los límites del workspace."""
    ws_dir, sandbox = workspace_env
    with pytest.raises(SandboxViolation) as exc_info:
        sandbox._validate_path_containment("../../malicious.py")
    assert "fuera del workspace" in str(exc_info.value)

    res = sandbox.edit_file("../../malicious.py", "print('hacked')")
    assert res.is_error is True
    assert "fuera del workspace" in res.output
