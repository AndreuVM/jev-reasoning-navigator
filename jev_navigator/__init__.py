"""Backward-compatibility shim for jev_navigator.

PRAXEON is the new package name: Runtime supervision for autonomous AI agents.
"""

import importlib
import sys
import warnings

import praxeon
from praxeon import __version__  # noqa: F401

warnings.warn(
    "The 'jev_navigator' package has been renamed to 'praxeon'. Please update your imports.",
    DeprecationWarning,
    stacklevel=2,
)


class _CompatibilityFinder:
    """Redirects all jev_navigator.* imports to praxeon.* seamlessly."""

    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith("jev_navigator."):
            praxeon_name = "praxeon." + fullname[len("jev_navigator.") :]
            try:
                mod = importlib.import_module(praxeon_name)
                sys.modules[fullname] = mod
                return getattr(mod, "__spec__", None)
            except Exception:
                return None
        return None


if not any(isinstance(finder, _CompatibilityFinder) for finder in sys.meta_path):
    sys.meta_path.insert(0, _CompatibilityFinder())
