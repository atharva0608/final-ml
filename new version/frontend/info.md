# Frontend Application

## Purpose

React-based single-page application (SPA) providing user interfaces for clients and admins.

**Last Updated**: 2025-12-25

---

## Directory Structure

```
frontend/
├── src/
│   ├── components/     - Reusable UI components
│   ├── layouts/        - Page layout components
│   ├── services/       - API client and services
│   ├── context/        - React Context providers
│   ├── pages/          - Page components
│   ├── config/         - Configuration files
│   ├── assets/         - Static assets
│   └── App.jsx         - Main application component
├── public/             - Public static files
├── package.json        - Dependencies
└── vite.config.js      - Vite configuration
```

---

## Key Files

### src/App.jsx
**Purpose**: Main application routing and layout
**Lines**: ~400

**Routes**:
- `/login` - Login page
- `/` - Admin dashboard (role: admin)
- `/client` - Client dashboard (role: client)
- `/onboarding/setup` - AWS account setup

**Recent Changes**:
- **2025-12-25**: Added AuthGateway wrapper for client routes
  - **Reason**: Smart routing based on account status
  - **Impact**: Prevents blank dashboard pages
  - **Reference**: `/progress/fixed_issues_log.md#P-2025-12-25-001`

### package.json
**Purpose**: NPM dependencies and scripts

**Key Dependencies**:
- react ^18.x
- react-router-dom - Routing
- lucide-react - Icons
- tailwindcss - Styling

**Scripts**:
```bash
npm run dev     # Development server
npm run build   # Production build
npm run preview # Preview build
```

---

## Running Locally

```bash
cd frontend
npm install
npm run dev
```

Access: `http://localhost:5173`

---

## Recent Changes

### 2025-12-25: Multi-Account Support
**Files Changed**:
- `src/App.jsx` - Added AuthGateway
- `src/components/ClientSetup.jsx` - Account list view
- `src/components/AuthGateway.jsx` - New component

**Reason**: Support multiple AWS accounts per user
**Impact**: All client flows
**Reference**: `/progress/fixed_issues_log.md#P-2025-12-25-001`

---

See: `src/info.md` for detailed component information

---

_Last Updated: 2025-12-25_
