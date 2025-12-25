# Frontend Changes Required

## Overview
The backend has been fully updated with new features and fixes, but the frontend needs to be updated to support these changes.

---

## ✅ Already Working (No Changes Needed)

1. **Manual Replica Toggle** - AgentConfigModal already has mutual exclusivity with auto-switch
2. **Agent Config Modal** - Already exists and functional
3. **Price History API** - Backend fixed, frontend should now work

---

## 🔴 REQUIRED Frontend Changes

### 1. Agent Deletion Support

#### **Location:** `frontend/src/components/details/tabs/ClientAgentsTab.jsx`

**Add Delete Button to Agent Cards:**

```jsx
// Add to each agent card (around line 90-140)
const handleDelete = async (agentId) => {
  if (!window.confirm('Are you sure you want to delete this agent? This will terminate all replicas and mark the agent as deleted.')) {
    return;
  }

  try {
    await api.deleteAgent(agentId);
    await loadAgents();
    alert('Agent deleted successfully');
  } catch (error) {
    alert('Failed to delete agent: ' + error.message);
  }
};

// Add button in the agent card JSX:
<Button
  variant="danger"
  size="sm"
  onClick={() => handleDelete(agent.id)}
  icon={<Trash2 size={16} />}
>
  Delete Agent
</Button>
```

#### **Add to API Client:** `frontend/src/services/api.jsx`

```javascript
// Add new function
deleteAgent: async (agentId) => {
  const response = await apiClient.delete(`/api/client/agents/${agentId}`);
  return response.data;
},
```

---

### 2. Agent Status Display

#### **Location:** `frontend/src/components/details/tabs/ClientAgentsTab.jsx`

**Update Status Badge Logic (around line 95-99):**

```jsx
// Current code only handles online/offline
{agent.status === 'online' ? (
  <CheckCircle size={18} className="text-green-500 flex-shrink-0" />
) : (
  <XCircle size={18} className="text-red-500 flex-shrink-0" />
)}

// NEW: Handle all statuses including 'deleted'
const getStatusBadge = (status) => {
  switch (status) {
    case 'online':
      return <Badge variant="success" icon={<CheckCircle size={14} />}>Online</Badge>;
    case 'offline':
      return <Badge variant="warning" icon={<XCircle size={14} />}>Offline</Badge>;
    case 'deleted':
      return <Badge variant="danger" icon={<Trash2 size={14} />}>Deleted</Badge>;
    case 'switching':
      return <Badge variant="info" icon={<RefreshCw size={14} />}>Switching</Badge>;
    default:
      return <Badge variant="secondary">{status}</Badge>;
  }
};

// Use it:
{getStatusBadge(agent.status)}
```

---

### 3. Agent History View (NEW PAGE)

#### **Create New Page:** `frontend/src/pages/AgentHistoryPage.jsx`

```jsx
import React, { useState, useEffect } from 'react';
import { Clock, Trash2, CheckCircle, XCircle } from 'lucide-react';
import LoadingSpinner from '../components/common/LoadingSpinner';
import ErrorMessage from '../components/common/ErrorMessage';
import Badge from '../components/common/Badge';
import api from '../services/api';

const AgentHistoryPage = ({ clientId }) => {
  const [agents, setAgents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filter, setFilter] = useState('all'); // 'all', 'online', 'offline', 'deleted'

  useEffect(() => {
    loadAgentHistory();
  }, [clientId]);

  const loadAgentHistory = async () => {
    setLoading(true);
    try {
      const data = await api.getAgentHistory(clientId);
      setAgents(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const filteredAgents = agents.filter(agent => {
    if (filter === 'all') return true;
    return agent.status === filter;
  });

  if (loading) return <LoadingSpinner />;
  if (error) return <ErrorMessage message={error} onRetry={loadAgentHistory} />;

  return (
    <div className="p-6">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Agent History</h1>
        <p className="text-gray-600">View all agents including deleted ones</p>
      </div>

      {/* Filter Buttons */}
      <div className="flex gap-2 mb-6">
        <button
          onClick={() => setFilter('all')}
          className={`px-4 py-2 rounded-lg ${filter === 'all' ? 'bg-blue-600 text-white' : 'bg-gray-200'}`}
        >
          All ({agents.length})
        </button>
        <button
          onClick={() => setFilter('online')}
          className={`px-4 py-2 rounded-lg ${filter === 'online' ? 'bg-green-600 text-white' : 'bg-gray-200'}`}
        >
          Online ({agents.filter(a => a.status === 'online').length})
        </button>
        <button
          onClick={() => setFilter('offline')}
          className={`px-4 py-2 rounded-lg ${filter === 'offline' ? 'bg-yellow-600 text-white' : 'bg-gray-200'}`}
        >
          Offline ({agents.filter(a => a.status === 'offline').length})
        </button>
        <button
          onClick={() => setFilter('deleted')}
          className={`px-4 py-2 rounded-lg ${filter === 'deleted' ? 'bg-red-600 text-white' : 'bg-gray-200'}`}
        >
          Deleted ({agents.filter(a => a.status === 'deleted').length})
        </button>
      </div>

      {/* Agent Table */}
      <div className="bg-white rounded-lg shadow overflow-hidden">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Agent ID</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Instance</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Created</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Last Heartbeat</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Terminated</th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {filteredAgents.map(agent => (
              <tr key={agent.id} className={agent.status === 'deleted' ? 'bg-red-50' : ''}>
                <td className="px-6 py-4 whitespace-nowrap">
                  <div className="text-sm font-mono text-gray-900">{agent.logicalAgentId || agent.id}</div>
                </td>
                <td className="px-6 py-4 whitespace-nowrap">
                  <Badge
                    variant={
                      agent.status === 'online' ? 'success' :
                      agent.status === 'offline' ? 'warning' :
                      agent.status === 'deleted' ? 'danger' : 'secondary'
                    }
                  >
                    {agent.status}
                  </Badge>
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                  {agent.instanceId || 'N/A'}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                  {agent.createdAt ? new Date(agent.createdAt).toLocaleDateString() : 'N/A'}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                  {agent.lastHeartbeat ? new Date(agent.lastHeartbeat).toLocaleString() : 'Never'}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                  {agent.terminatedAt ? new Date(agent.terminatedAt).toLocaleString() : '-'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default AgentHistoryPage;
```

#### **Add to API Client:** `frontend/src/services/api.jsx`

```javascript
getAgentHistory: async (clientId) => {
  const response = await apiClient.get(`/api/client/${clientId}/agents/history`);
  return response.data;
},
```

#### **Add Route:** `frontend/src/App.jsx`

```jsx
import AgentHistoryPage from './pages/AgentHistoryPage';

// Add to routes
<Route path="/clients/:clientId/agent-history" element={<AgentHistoryPage />} />
```

---

### 4. Auto-Terminate Toggle

#### **Location:** `frontend/src/components/modals/AgentConfigModal.jsx`

**Add after Manual Replica Toggle (around line 100-120):**

```jsx
{/* Auto-Terminate Toggle */}
<div className="pb-4 border-b border-gray-200">
  <div className="flex items-center justify-between mb-2">
    <div className="flex-1 mr-4">
      <label className="block text-sm font-medium text-gray-900">
        Auto-Terminate Old Instances
      </label>
      <p className="text-xs text-gray-500 mt-1">
        Automatically terminate old instances after switching to new ones.
        When disabled, old instances remain running for manual cleanup.
      </p>
    </div>
    <label className="relative inline-flex items-center cursor-pointer flex-shrink-0">
      <input
        type="checkbox"
        checked={autoTerminateEnabled}
        onChange={(e) => setAutoTerminateEnabled(e.target.checked)}
        className="sr-only peer"
      />
      <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-blue-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600"></div>
    </label>
  </div>
  {!autoTerminateEnabled && (
    <p className="text-xs text-amber-600 mt-2">
      ⚠️ Old instances will remain running. You must manually terminate them.
    </p>
  )}
</div>
```

**Add State:**
```jsx
const [autoTerminateEnabled, setAutoTerminateEnabled] = useState(agent.autoTerminateEnabled ?? true);
```

**Update Save Handler:**
```jsx
const handleSave = async () => {
  setSaving(true);
  try {
    await api.updateAgentConfig(agent.id, {
      terminateWaitMinutes,
      autoSwitchEnabled,
      manualReplicaEnabled,
      autoTerminateEnabled  // ADD THIS
    });
    onSave();
    onClose();
  } catch (error) {
    alert('Failed to save configuration: ' + error.message);
  } finally {
    setSaving(false);
  }
};
```

---

### 5. Remove Duplicate Auto-Switch Toggle from Agent Card

#### **Location:** `frontend/src/components/details/tabs/ClientAgentsTab.jsx`

**Find and REMOVE** any auto-switch toggle from the agent card display (lines ~130-150).
The auto-switch toggle should ONLY be in the config modal, not on the card.

**Keep only:**
- Enable/Disable agent toggle
- Settings button to open config modal
- Delete button (new)

---

### 6. Pricing Data Display

#### **Instance Management Page**

Pricing data endpoints already exist. You may want to add pricing display to:

**Location:** `frontend/src/components/details/tabs/ClientInstancesTab.jsx`

```jsx
// Already has spotPrice and onDemandPrice in the API response
// Just ensure they're displayed in the UI:
<div className="text-sm">
  <span className="text-gray-600">Spot:</span> ${instance.spotPrice?.toFixed(4)}/hr
  <span className="text-gray-600 ml-4">On-Demand:</span> ${instance.onDemandPrice?.toFixed(4)}/hr
  {instance.spotPrice && instance.onDemandPrice && (
    <span className="text-green-600 ml-4">
      Savings: {((1 - instance.spotPrice / instance.onDemandPrice) * 100).toFixed(1)}%
    </span>
  )}
</div>
```

---

## 📋 Implementation Checklist

### High Priority (Core Functionality)
- [ ] Add delete agent button to ClientAgentsTab
- [ ] Add deleteAgent function to API client
- [ ] Update agent status badge to handle 'deleted' status
- [ ] Add auto_terminate_enabled toggle to AgentConfigModal
- [ ] Update updateAgentConfig API call to include autoTerminateEnabled
- [ ] Remove duplicate auto-switch toggle from agent card (keep only in modal)

### Medium Priority (Enhanced UX)
- [ ] Create AgentHistoryPage component
- [ ] Add getAgentHistory to API client
- [ ] Add route for agent history page
- [ ] Add navigation link to agent history
- [ ] Improve pricing data display in instance views

### Low Priority (Nice to Have)
- [ ] Add confirmation dialogs with better messaging
- [ ] Add success/error toasts instead of alerts
- [ ] Add loading states for delete operations
- [ ] Add agent count badges by status
- [ ] Add refresh button for agent history

---

## 🔌 API Client Updates Summary

Add these functions to `frontend/src/services/api.jsx`:

```javascript
export default {
  // ... existing functions ...

  // NEW: Agent deletion
  deleteAgent: async (agentId) => {
    const response = await apiClient.delete(`/api/client/agents/${agentId}`);
    return response.data;
  },

  // NEW: Agent history
  getAgentHistory: async (clientId) => {
    const response = await apiClient.get(`/api/client/${clientId}/agents/history`);
    return response.data;
  },

  // UPDATE: Add autoTerminateEnabled support
  updateAgentConfig: async (agentId, config) => {
    const response = await apiClient.post(`/api/client/agents/${agentId}/config`, {
      terminateWaitMinutes: config.terminateWaitMinutes,
      autoSwitchEnabled: config.autoSwitchEnabled,
      manualReplicaEnabled: config.manualReplicaEnabled,
      autoTerminateEnabled: config.autoTerminateEnabled  // NEW
    });
    return response.data;
  },
};
```

---

## 🧪 Testing Steps

After implementing frontend changes:

1. **Delete Agent:**
   - Click delete button on agent card
   - Confirm deletion
   - Verify agent disappears from active list
   - Check agent history - should appear with 'deleted' status

2. **Agent History:**
   - Navigate to agent history page
   - See all agents including deleted
   - Filter by status (all/online/offline/deleted)
   - Verify timestamps displayed correctly

3. **Auto-Terminate Toggle:**
   - Open agent config modal
   - Toggle auto-terminate OFF
   - Save and trigger a switch
   - Verify old instance stays running

4. **Status Display:**
   - Verify online agents show green badge
   - Verify offline agents show yellow badge
   - Verify deleted agents show red badge
   - Verify status updates in real-time

---

## 📚 References

- Backend API Documentation: `docs/FIXES_AND_FEATURES.md`
- Agent-Side Changes: `docs/AGENT_SIDE_CHANGES.md`
- Existing Components: Check `frontend/src/components/` for examples

---

**Last Updated:** 2025-11-23
**Frontend Version:** Needs Update
