# Backend Information

**Documentation Centralized**: See `docs/backend.md` for detailed component mapping.

## Modules
- **API**: FastAPI routes (`api/`).
- **Core**: Configuration, Security, Logger (`core/`).
- **Models**: SQLAlchemy database models (`models/`).
- **Schemas**: Pydantic request/response schemas (`schemas/`).
- **Services**: Business logic (`services/`).
- **Workers**: Celery tasks (`workers/`).

## Recent Updates (Jan 2026)
- **Karpenter Config**: Added `cluster_policies.config` JSONB support.
- **AWS STS**: Added `AWSConnectRequest` and STS assumption logic.
- **Startup**: Auto-table creation and admin seeding enabled.
