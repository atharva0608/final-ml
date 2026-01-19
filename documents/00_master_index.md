# 🗺️ Granular System Architecture Map

## 🆔 ID Naming Convention
Format: `[PREFIX] :: [FILENAME] :: [FUNCTION/COMPONENT_NAME]`

| Domain | Prefix | Example ID | Target Type |
| :--- | :--- | :--- | :--- |
| **Frontend UI** | `FE-CMP` | `FE-CMP::PolicyConfig::KarpenterToggle` | React Component / Helper |
| **Frontend Logic** | `FE-HK` | `FE-HK::useAuth::login` | Hook Function |
| **Backend API** | `BE-API` | `BE-API::auth_routes::login` | API Endpoint Function |
| **Backend Logic** | `BE-SRV` | `BE-SRV::AuthService::authenticate_user` | Service Class Method |
| **Backend Model** | `BE-MOD` | `BE-MOD::User::role` | Database Column / Field |
| **Worker Task** | `BE-WRK` | `BE-WRK::optimization::run_spot_analysis` | Celery Task Function |

## 📂 Core Directory Map
- **Frontend Components:** `frontend/src/components`
- **Backend Services:** `backend/services`
- **Backend API:** `backend/api`
- **Backend Models:** `backend/models`

## 📚 Documentation Index
| Document | Description | Last Updated |
| :--- | :--- | :--- |
| **[Frontend Catalog](01_frontend_catalog.md)** | Inventory of all UI components, hooks, and routes. | **2026-01-19** |
| **[Backend Catalog](02_backend_catalog.md)** | Inventory of services, APIs, models, and workers. | **2026-01-19** |
| **[Change Ledger](03_change_ledger.md)** | Log of critical system changes and fixes. | **2026-01-19** |
| **[Gap Analysis](03_frontend_backend_gap_analysis.md)** | Frontend vs Backend API alignment report. | **2026-01-19** |
| **[Permissions Matrix](04_application_permissions.md)** | Detailed RBAC permissions and access rules. | **2026-01-19** |
