# Cleanup Report

## Moved Files
- `backend/services/chaos_testing_service.py`
  - **Reason**: Zero references in the codebase execution paths. Only referenced in documentation (`docs/database-audit.md` and `problems.md`). Not imported dynamically or statically by any runtime file.
- `backend/services/instability_propagator.py`
  - **Reason**: Zero occurrences across the entire codebase. Completely orphaned service.
- `backend/services/partition_management_service.py`
  - **Reason**: Only imports itself on line 613. Zero references from outside the file. Not attached to any active execution path or router.
- `backend/services/sts_credential_broker.py`
  - **Reason**: Zero occurrences across the entire codebase. Completely orphaned service.
- `backend/workers/tasks/alert_worker.py`
  - **Reason**: Only imports itself recursively. Not registered in `backend/workers/app.py`'s `include` list. Not exported in `backend/workers/tasks/__init__.py`. 
- `backend/workers/tasks/tag_automation_tasks.py`
  - **Reason**: Zero occurrences across the entire codebase. Not registered in `backend/workers/app.py`'s `include` list. Not exported in `backend/workers/tasks/__init__.py`.
- `backend/api/ai_agent_routes.py`
  - **Reason**: Zero references in code. Only referenced in documentation (`documents/all-components.md` and `docs/API_TESTING_COMMANDS.md`). Completely orphaned route module.

## Skipped Files (uncertain)
- `backend/workers/tasks/optimization.py`
  - **Reason**: Although not registered in the Celery beat schedule or the worker `include` list, it is explicitly exported in `backend/workers/tasks/__init__.py` (line 15). Moving this file without modifying `__init__.py` would break application imports on boot.
- `backend/workers/tasks/event_processor.py`
  - **Reason**: Exported in `backend/workers/tasks/__init__.py` (line 27). Moving it would cause `ModuleNotFoundError` during package initialization.
- `backend/workers/tasks/report_worker.py`
  - **Reason**: Exported in `backend/workers/tasks/__init__.py` (line 22). Moving it would cause `ModuleNotFoundError` during package initialization.

## Summary
- **Total files scanned**: 69 services + 47 worker tasks + 49 API routes + 14 agent files
- **Total moved**: 7
- **Warnings**: Three files identified as potentially dead code (`optimization.py`, `event_processor.py`, `report_worker.py`) were skipped to comply strictly with the "DO NOT modify active code" and "DO NOT break imports" rules, because they are bound to the `backend.workers.tasks` package namespace via `__init__.py`.
