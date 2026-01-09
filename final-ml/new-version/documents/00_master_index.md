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
