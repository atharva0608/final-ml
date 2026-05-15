"""
Root conftest.py
================
Registers lightweight sys.modules stubs for backend.services and backend.api
BEFORE any test module is imported.

Purpose:
  backend/services/__init__.py eagerly imports the full service registry
  (auth_service → core.crypto → cryptography) and
  backend/api/__init__.py eagerly imports every FastAPI route (fastapi, etc.).
  Neither of these packages is installed in the minimal test venv.

  Stubbing the *package* (not the submodule files) means:
    - __init__.py is never executed for either package.
    - Individual submodule files (placement_controller_service.py, etc.)
      are still loaded from disk normally.

  This follows the standard sys.modules pre-population pattern for unit
  test isolation without requiring the full production dependency stack.
"""
import os
import sys
import types


_ROOT = os.path.dirname(__file__)


def _stub(name: str) -> types.ModuleType:
    """Create a package stub with __path__ pointing to the real directory.

    Setting __path__ is critical: without it Python treats the entry in
    sys.modules as a plain module (not a package) and refuses to import
    submodules from it.  With __path__ pointing to the actual directory,
    Python can find and load submodule .py files from disk while completely
    skipping the package's own __init__.py.
    """
    mod = types.ModuleType(name)
    mod.__package__ = name
    pkg_path = os.path.join(_ROOT, *name.split("."))
    mod.__path__ = [pkg_path]
    sys.modules[name] = mod
    return mod


# ── backend.services ──────────────────────────────────────────────────────────
# Prevents backend/services/__init__.py from loading the full service registry.
_stub("backend.services")

# karpenter_service.py is imported at module level by placement_rollout_service
# but is never called in tested code paths — stub it to avoid boto3/yaml deps.
_ks = _stub("backend.services.karpenter_service")
_ks.KarpenterService = type("KarpenterService", (), {})  # minimal class stub

# ── backend.api ───────────────────────────────────────────────────────────────
# Prevents backend/api/__init__.py from loading every FastAPI route file.
_stub("backend.api")
