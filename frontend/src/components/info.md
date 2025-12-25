# Frontend Components

## Purpose

Reusable React components for the application UI.

**Last Updated**: 2025-12-25

---

## Key Components

### AuthGateway.jsx ⭐ NEW
**Purpose**: Smart routing based on account status
**Lines**: ~50
**Created**: 2025-12-25

**Functionality**:
- Checks if user has connected AWS accounts
- Redirects to `/onboarding/setup` if no accounts
- Redirects to `/client` if accounts exist
- Prevents blank dashboard pages

**Usage**:
```jsx
<AuthGateway>
  <ClientDashboard />
</AuthGateway>
```

**Dependencies**:
- `/client/accounts` API endpoint
- React Router (useNavigate)

**Recent Changes**:
- **2025-12-25**: Initial creation for multi-account support
**Reference**: `/scenarios/auth_flow.md#authgateway-routing`

---

### ClientSetup.jsx ⭐ MAJOR
**Purpose**: AWS account connection and management
**Lines**: ~860
**Status**: ACTIVE DEVELOPMENT

**Features**:
1. **Account List View**:
   - Shows all connected AWS accounts
   - Status badges (active, connected, discovering)
   - Disconnect button
   - "Add Account" button

2. **Connection Methods**:
   - CloudFormation (IAM Role)
   - Access Keys (Direct credentials)

3. **Live Polling**:
   - Polls `/client/accounts` every 3 seconds
   - Shows progress during discovery
   - Auto-stops when active or timeout

**Key Functions**:
- `checkConnectedAccounts()` - Fetch account list (line 218)
- `handleDisconnect(accountId)` - Delete account (line 253)
- `startPollingAccountStatus()` - Real-time updates (line 162)
- `verifyConnection()` - CloudFormation verification (line 86)
- `connectWithCredentials()` - Access key connection (line 119)

**State Management**:
```javascript
const [connectedAccounts, setConnectedAccounts] = useState([])
const [showOnboarding, setShowOnboarding] = useState(true)
const [pollingIntervalId, setPollingIntervalId] = useState(null)
```

**Recent Changes**:
- **2025-12-25**: Added disconnect functionality
  - DELETE `/client/accounts/{id}` integration
  - Account list refresh after disconnect
- **2025-12-25**: Added live polling
  - 3-second interval status checks
  - Progress messages with elapsed time
  - Cleanup on unmount

**Reference**: `/scenarios/client_onboarding_flow.md`

---

### LoginPage.jsx
**Purpose**: User authentication UI
**Lines**: ~300

**Features**:
- Username/password form
- Role-based redirect after login
- Error handling

**Dependencies**:
- `/api/auth/login` endpoint
- AuthContext

**Recent Changes**: None recent

---

### NodeFleet.jsx
**Purpose**: EC2 instance fleet management view
**Lines**: ~1000

**Features**:
- Instance list with filters
- Status visualization
- Instance details
- Optimization recommendations

**Dependencies**:
- `/client/dashboard` API

**Recent Changes**: None recent

---

### ClientManagement.jsx
**Purpose**: Admin view for managing client users
**Lines**: ~600

**Features**:
- Client user list
- User CRUD operations
- Account status overview

**Dependencies**:
- Admin API endpoints

**Recent Changes**: None recent

---

### LiveOperations.jsx
**Purpose**: Real-time operation monitoring
**Lines**: ~400

**Features**:
- Live operation feed
- WebSocket updates
- Operation status

**Dependencies**:
- WebSocket connection

**Recent Changes**: None recent

---

### Controls.jsx
**Purpose**: System control panel
**Lines**: ~400

**Features**:
- System settings
- Manual operations
- Configuration

**Dependencies**:
- Admin APIs

**Recent Changes**: None recent

---

## Component Patterns

### API Integration
```jsx
import api from '../services/api';

const fetchData = async () => {
  try {
    const response = await api.get('/endpoint');
    setData(response.data);
  } catch (error) {
    console.error(error);
  }
};
```

### Polling Pattern
```jsx
useEffect(() => {
  const interval = setInterval(async () => {
    await checkStatus();
  }, 3000);

  return () => clearInterval(interval);
}, []);
```

### Protected Routes
```jsx
import { useAuth } from '../context/AuthContext';

const { user } = useAuth();
if (user.role !== 'client') {
  navigate('/');
}
```

---

## Recent Changes Summary

### 2025-12-25: Multi-Account & Polling Features
**Files Changed**:
1. `ClientSetup.jsx`:
   - Added account list view
   - Added disconnect functionality
   - Added live status polling
   - Added cleanup on unmount

2. `AuthGateway.jsx` (NEW):
   - Created smart routing component
   - Account-based navigation logic

**Reason**: Support multiple AWS accounts with persistent connected state
**Impact**: All client onboarding and dashboard flows
**Reference**: `/progress/fixed_issues_log.md`

---

## Dependencies

**Requires**:
- React 18+
- React Router
- API services (`services/api.js`)
- Context providers (`context/`)

**Required By**:
- App.jsx routing
- Layout components

---

_Last Updated: 2025-12-25_
_See: `/index/feature_index.md` for feature details_
