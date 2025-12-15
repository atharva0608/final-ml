# Spot Optimizer Platform - Frontend Features Documentation

## Table of Contents
1. [Authentication System](#authentication-system)
2. [User Roles & Permissions](#user-roles--permissions)
3. [Admin Dashboard](#admin-dashboard)
4. [Client Dashboard](#client-dashboard)
5. [ML Model Management (Lab Mode)](#ml-model-management-lab-mode)
6. [System Controls](#system-controls)
7. [Navigation & UI Components](#navigation--ui-components)

---

## Authentication System

### Login Page
- **Split-Screen Layout**: Modern full-screen design with branding on the left, form on the right
- **Support for Multiple User Types**:
  - Admin Login: `admin/admin`
  - Demo Client Login: `ath/ath` (maps to TechCorp Solutions)
  - Custom Client Accounts (created via Admin panel)
- **Sign Up Option**: Link below login form for new account creation
- **Session Persistence**: Uses localStorage to maintain user sessions

### User Credentials
| Username | Password | Role | Access |
|----------|----------|------|--------|
| `admin` | `admin` | Admin | Full system access |
| `ath` | `ath` | Client | TechCorp Solutions dashboard |

---

## User Roles & Permissions

### Admin Role
**Full Platform Access:**
- ✅ Live Operations monitoring
- ✅ Node Fleet management (all clients)
- ✅ System Controls & configuration
- ✅ Lab Mode (R&D experiments)
- ✅ Global Policy management
- ✅ Client creation & management

### Client Role
**Restricted Access:**
- ✅ Personal dashboard (own clusters only)
- ✅ Profile management
- ❌ No access to System Controls
- ❌ No access to Lab Mode
- ❌ No access to other clients' data

---

## Admin Dashboard

### 1. Live Operations
**Purpose**: Real-time monitoring of the entire platform's optimization pipeline.

#### Key Metrics Cards
- **Total Monthly Savings**: Aggregate cost reduction across all clients
- **Active Instances**: Current number of managed EC2 instances
- **Optimization Rate**: Percentage of successfully optimized workloads
- **This Month's Cost Reduction**: Dollar amount saved in the current period

#### Visual Pipeline (Funnel Chart)
Shows the multi-stage optimization process:
1. **Starting Pool**: All candidate instances entering the system
2. **Model Inference**: Instances analyzed by ML stability predictor
3. **Bin Packing**: Workload consolidation optimization
4. **Spot Selection**: Final instance type selection
5. **Deployed**: Successfully optimized instances

**Interactive Elements**:
- Click on any funnel stage to view detailed breakdown
- Hover for specific counts and percentages

#### Real-Time Activity Feed
- **Live Updates**: Stream of recent optimization decisions
- **Color-Coded Events**:
  - 🟢 Green: Successful switch to Spot
  - 🟡 Yellow: Rebalancing in progress
  - 🔴 Red: Fallback to On-Demand
- **Filters**: Filter by event type, client, or time range

---

### 2. Node Fleet (Client Management)

#### Mission Control View
**Client List Grid**:
- **Client Cards**: Visual cards showing each managed client
- **Quick Stats per Client**:
  - Joined date
  - Number of clusters
  - Total managed nodes
  - Monthly savings

**Action Buttons**:
- **"Add Client"**: Opens modal to create new client account
  - Company Name input
  - Primary Region selection
  - Username creation (optional)
  - Auto-generates credentials
- **"Global Policies"**: Opens policy management modal

#### Global Policy Manager
**Purpose**: Set default fleet policies for all clients.

**Available Policies**:
1. **Spot Fallback Strategy**
   - Toggle: ON/OFF
   - Description: Auto-switch to On-Demand when Spot pools exhausted
   
2. **Aggressive Rebalancing**
   - Toggle: ON/OFF  
   - Description: Proactively cycle nodes for >10% savings opportunities
   
3. **Auto-Binpacking**
   - Toggle: ON/OFF
   - Description: Consolidate workloads to minimize node count

**Buttons**:
- **"Apply Global Changes"**: Updates all client policies
- **"Cancel"**: Closes modal without saving

#### Client Detail View
When clicking on a client card:

**Tabs**:
1. **Dashboard**: Overview with key metrics
   - Resource distribution charts (per cluster)
   - Cost savings graphs
   - Health status indicators
   - Instance topology visualization

2. **Clusters**: List of managed Kubernetes/ECS clusters
   - Click to drill down into cluster details
   - Shows region, node count, status

3. **Unregistered**: Rogue EC2 instances detected
   - Table showing unauthorized instances
   - Actions: Authorize or Terminate
   - Bulk operations via "Apply Actions" button

4. **Volumes**: Unmapped EBS volumes
   - List of unattached storage
   - Cost tracking for orphaned resources

5. **Snapshots**: AMI & snapshot management
   - Cleanup recommendations

**Policy Badges**: Shows active policies for this specific client
- Blue badge: Fallback enabled
- Purple badge: Rebalancing enabled
- Green badge: Binpacking enabled

---

### 3. System Controls

#### Manual Overrides Section
**Disable Spot Market Button**:
- **Purpose**: Force all workloads to On-Demand (emergency)
- **Behavior**: 
  - Click once → Confirmation modal appears
  - Modal warns: "Costs will increase significantly"
  - Confirm → All Spot instances stop being provisioned
  - Toggle again to re-enable Spot
- **Visual**: Red when active with pulsing animation

#### Production Configuration
**Threshold Sliders**:
- **Stability Score Threshold** (0-100)
  - Minimum ML model confidence required
  - Default: 75
  
- **Max Rebalance Frequency** (hours)
  - How often nodes can be cycled
  - Default: 24 hours

**Savings Target**: Input field for monthly cost reduction goal

**Apply Changes Button**:
- Fixed footer button
- Saves all configuration changes
- Shows success notification

#### Resource Distribution by Cluster
**Interactive Charts**:
- **Pie/Ring Chart per Cluster**:
  - Green segment: Spot instances
  - Blue segment: On-Demand instances
  - Gray segment: Reserved instances
- **Carousel Navigation**:
  - Left/Right arrows to switch between clusters
  - Auto-rotation option
  - Manual cluster selection

---

### 4. Lab Mode (R&D Interface)

**Access**: Click "Scope Switcher" → Select "Internal Lab (R&D)"

#### Purpose
Safe environment to test new ML stability models against real production data without affecting live systems.

#### Pipeline Visualizer
**Visual Workflow Display**:
- Shows data flow: `Filter → Model v2 → Switch Decision → AWS API`
- **Color States**:
  - Green border: Active component
  - Purple pulsing: Experimental/testing
  - Gray strikethrough: Bypassed component

#### Test Subject Instances Table
**Columns**:
- Instance ID (clickable for details)
- Current Model assignment
- Model override dropdown
- Performance status
- Actions (View Details, Reset)

**Click Instance**: Opens deep-dive panel with:
- Switching timeline
- Model performance history
- Savings vs. termination stats

#### Model Registry Table
**Columns**:
- Model Name (user-provided or timestamp)
- Status badge:
  - Orange: "Testing" (newly uploaded)
  - Blue: "Graduated" (passed validation)
  - Green: "Enabled" (active in production)
- Upload Date
- Performance Metrics (if available)
- Actions column

**Action Buttons by Status**:
- **Testing Status**:
  - "Graduate" → Moves to Graduated
  - "Reject" → Marks as failed
  
- **Graduated Status**:
  - "Enable in Prod" → Makes available in production dropdown
  - "Remove" → Deletes model
  
- **Enabled Status**:
  - "Disable" → Removes from production
  - "View Stats" → Shows performance dashboard

#### Model Upload Section
**Drag & Drop Zone**:
- **Supported Files**: `.pkl`, `.h5`, `.joblib`, `.pt`
- **Process**:
  1. Drag file or click to browse
  2. System validates format
  3. Auto-assigns to "Testing" status
  4. Shows in Model Registry immediately
- **Visual Feedback**: Upload progress bar, success/error states

#### Decision Log
**Toggle Switches**:
- **"Live Stream"** vs **"Historical Archive"**
  - Live: Real-time decisions as they happen
  - Archive: Date-range filtered past decisions

**Log Entries**:
- Timestamp
- Source component (Filter/Model/Switch/AWS)
- Decision message
- Color-coded severity
- Expandable details

---

## Client Dashboard

**URL**: `/client`

### Header Customization
- Shows: "Organization / [Client Name]" (e.g., "Organization / TechCorp Solutions")
- No Scope Switcher (Lab mode hidden)

### Simplified Sidebar
**Menu Items**:
1. **Dashboard** (default view)
2. **My Profile**
3. **Sign Out**

*Note*: System Controls, Lab Mode, and Global Fleet access are hidden for clients.

### Dashboard Tab Content

#### Resource Distribution Charts
**Per-Cluster Visualization**:
- Swipeable carousel of pie charts
- Shows resource allocation (Spot/On-Demand/Reserved)
- Animated counter showing total instances
- Navigation arrows

#### Managed Clusters List
**Cluster Cards**:
- Cluster name and region
- Node count
- Click to expand detailed node list
- Emergency Fallback button (with confirmation)

#### Cost & Savings Graphs
- Monthly savings trend
- Projected vs. actual costs
- Savings breakdown by cluster

#### Health Status Cards
- System health indicators
- Active alerts
- Optimization rate

#### Activity Log
- Recent optimization events
- Filtered to show only this client's activity

---

## ML Model Management (Lab Mode)

### Complete Workflow

#### 1. Upload New Model
**Steps**:
1. Switch to Lab Mode via Scope Switcher
2. Navigate to "Model Experiments"
3. Scroll to "Upload Model" section (bottom)
4. Drag `.pkl` or `.h5` file into dropzone
5. Model appears in registry with "Testing" status

#### 2. Test Model
**Assign to Test Instances**:
1. In Test Subject table, select instance
2. Use dropdown to assign new model
3. Monitor performance in real-time via Decision Log
4. View detailed switching history in instance details

#### 3. Graduate Model
**When to Graduate**:
- Model shows stable performance
- Accuracy meets threshold
- No unexpected terminations

**How to Graduate**:
1. Find model in registry (orange "Testing" badge)
2. Click "Graduate" button
3. Status changes to blue "Graduated"
4. Model is now validated but not yet in production

#### 4. Enable in Production
**Final Deployment**:
1. Click "Enable in Prod" on graduated model
2. Status changes to green "Enabled"
3. Model now appears in production Systems Controls dropdown
4. Admin can select it as active production model

#### 5. Monitor Production Performance
**In System Controls**:
- Select model from "Active Model" dropdown
- Monitor via Live Operations metrics
- Compare performance vs. previous models

---

## System Controls

### Model Selection Workflow

**Active Model Dropdown**:
- Shows only "Enabled" models from Lab
- Currently selected model highlighted
- Change selection to switch active model

**Upload New Production Model**:
- Alternative to Lab workflow
- Direct upload for trusted models
- Bypasses Testing/Graduation stages
- ⚠️ Higher risk - use Lab workflow for validation

---

## Navigation & UI Components

### Sidebar Navigation

#### Collapsible Behavior
**Desktop**:
- Click hamburger menu to toggle
- Sidebar pushes content when open
- Width: 256px when open, 0px when closed

**Mobile**:
- Sidebar as overlay (fixed position)
- Backdrop blur when open
- Click outside to close

#### Scope Switcher (Admin Only)
**Location**: Top right of header

**Button States**:
- Production: Green dot, "Production Environment"
- Lab: Purple dot, "Internal Lab (R&D)"

**Switch Behavior**:
1. Click button → Dropdown opens
2. Select new scope
3. Automatic navigation:
   - Production → `/` (Live Operations)
   - Lab → `/experiments` (Model Experiments)
4. Sidebar items update automatically
5. Theme changes (if configured)

### Profile Management

#### My Profile (Unified for All Users)
**Click "My Profile" or "Admin Profile"**:

**User Information Section**:
- Avatar icon (color-coded by role)
- Name/title
- Username display
- Role/Client ID badge
- Email support contact

**Security Settings Section**:
- Current Password field
- New Password field
- Confirm New Password field
- "Update Password" button
- Form validation on submit

#### Sign Out
**Click "Sign Out"**:
- Clears session from localStorage
- Redirects to `/login`
- Requires re-authentication

---

## Interactive Elements Reference

### Buttons & Actions Quick Reference

| Button/Element | Location | Action | User Type |
|----------------|----------|--------|-----------|
| **Add Client** | Node Fleet (Mission Control) | Opens client creation modal | Admin |
| **Global Policies** | Node Fleet (Mission Control) | Opens policy editor | Admin |
| **Apply Global Changes** | Policy Modal | Saves policies to all clients | Admin |
| **Emergency Fallback** | Cluster Detail View | Forces On-Demand provisioning | Admin, Client |
| **Disable Spot Market** | System Controls | Platform-wide Spot suspension | Admin |
| **Apply Changes** | System Controls | Saves configuration | Admin |
| **Upload Model** | Lab (Drag-Drop Zone) | Uploads ML model file | Admin |
| **Graduate** | Lab (Model Registry) | Promotes model to validated | Admin |
| **Enable in Prod** | Lab (Model Registry) | Activates model for production | Admin |
| **View Details** | Test Subjects Table | Opens instance deep-dive | Admin |
| **Update Password** | My Profile | Changes user password | All |
| **Sign Out** | Sidebar | Logs out user | All |

### Navigation Shortcuts

| View | Admin Shortcut | Client Access |
|------|---------------|---------------|
| Dashboard | Click "Live Operations" | Default view |
| Clients | Click "Node Fleet" | ❌ Hidden |
| Controls | Click "System Controls" | ❌ Hidden |
| Lab | Switch Scope → Lab | ❌ Hidden |
| Profile | Click "Admin Profile" | Click "My Profile" |

---

## Key Features Summary

### Admin Capabilities
✅ Monitor all clients in real-time  
✅ Manage global fleet policies  
✅ Create and configure client accounts  
✅ Test and deploy ML models safely  
✅ Emergency controls (disable Spot market)  
✅ Detailed analytics and logs  

### Client Capabilities  
✅ View personal cluster health  
✅ Monitor cost savings  
✅ Emergency fallback controls  
✅ Profile and password management  
✅ Activity logs (filtered to own data)  

### ML Model Lifecycle
1. **Upload** → Testing status in Lab
2. **Validate** → Monitor performance on test instances
3. **Graduate** → Mark as validated
4. **Enable** → Deploy to production
5. **Monitor** → Track performance metrics

---

## Technical Implementation Notes

### State Management
- Uses React Context for authentication (`AuthContext`)
- Uses React Context for ML models (`ModelContext`)
- Local state management via `useState` hooks

### Routing
- React Router for navigation
- Protected routes based on user role
- Auto-redirect on unauthorized access

### Mock Data
- Client data: `data/mockData.js`
- Instance details: Pre-configured realistic scenarios
- Model registry: In-memory state (not persisted)

### Styling
- Tailwind CSS for utility-first styling
- Custom animations for state transitions
- Responsive design (mobile-first)

---

## Future Enhancements (Planned)

- [ ] Real-time WebSocket integration
- [ ] CSV export for all data tables
- [ ] Advanced filtering in all list views
- [ ] Email notifications for critical events
- [ ] Multi-factor authentication
- [ ] Audit log for compliance tracking
- [ ] API documentation integration

---

*Last Updated: 2025-12-15*  
*Frontend Version: 1.0.0*  
*Developer: Atharva AI Team*
