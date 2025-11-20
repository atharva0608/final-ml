# Frontend Integration Guide - ML Model Management Buttons

## Overview
This guide explains how to integrate the new ML model management buttons into the frontend.

## Backend Endpoints (Already Implemented ✅)

### 1. Upload Models
```http
POST /api/admin/ml-models/upload
Content-Type: multipart/form-data
Body: files (array of model files)
```

**Response:**
```json
{
  "success": true,
  "message": "Uploaded N files. Use RESTART button to activate.",
  "files": ["model1.pkl", "model2.pkl"],
  "sessionId": "uuid-here",
  "requiresRestart": true,
  "model_status": {
    "filesUploaded": 2,
    "totalSize": 1048576,
    "sessionType": "pending_activation"
  }
}
```

### 2. 🔴 RESTART Button - Activate Models (NEW ✅)
```http
POST /api/admin/ml-models/activate
Content-Type: application/json
Body: { "sessionId": "uuid-from-upload" }
```

**Response:**
```json
{
  "success": true,
  "message": "Models activated. Backend will restart in 3 seconds.",
  "sessionId": "uuid",
  "restarting": true
}
```

### 3. ⏪ FALLBACK Button - Roll Back (NEW ✅)
```http
POST /api/admin/ml-models/fallback
Content-Type: application/json
Body: {}
```

**Response:**
```json
{
  "success": true,
  "message": "Rolled back to previous version. Backend restarting in 3 seconds.",
  "fallbackSessionId": "uuid",
  "restarting": true
}
```

### 4. Get Upload Sessions (NEW ✅)
```http
GET /api/admin/ml-models/sessions
```

**Response:**
```json
[
  {
    "id": "uuid",
    "status": "active",
    "isLive": true,
    "isFallback": false,
    "fileCount": 2,
    "files": ["model1.pkl", "model2.pkl"],
    "totalSize": 1048576,
    "createdAt": "2025-11-20T06:00:00Z",
    "activatedAt": "2025-11-20T06:05:00Z"
  }
]
```

---

## Frontend Implementation Required

### Location
Add these buttons to your ML Model upload page (likely in `src/pages/` or `src/components/`)

### Required UI Components

#### 1. Upload Section (Update Existing)
```jsx
// After successful upload, store the sessionId
const [pendingSessionId, setPendingSessionId] = useState(null);
const [uploadedFiles, setUploadedFiles] = useState([]);

const handleUpload = async (files) => {
  const formData = new FormData();
  files.forEach(file => formData.append('files', file));

  const response = await fetch('/api/admin/ml-models/upload', {
    method: 'POST',
    body: formData
  });

  const data = await response.json();

  if (data.success) {
    setPendingSessionId(data.sessionId);
    setUploadedFiles(data.files);
    // Show success message
    toast.success(`Uploaded ${data.files.length} files. Click RESTART to activate.`);
  }
};
```

#### 2. RED RESTART Button (NEW - Add This)
```jsx
const handleRestart = async () => {
  if (!pendingSessionId) {
    toast.error('No uploaded session to activate');
    return;
  }

  const confirmed = confirm('⚠️ This will restart the backend server. Continue?');
  if (!confirmed) return;

  try {
    const response = await fetch('/api/admin/ml-models/activate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sessionId: pendingSessionId })
    });

    const data = await response.json();

    if (data.success) {
      toast.success('✅ Models activated! Backend restarting in 3 seconds...');
      setPendingSessionId(null);

      // Backend will restart, so wait and reload page
      setTimeout(() => {
        window.location.reload();
      }, 5000);
    } else {
      toast.error('Failed to activate models');
    }
  } catch (error) {
    toast.error(`Activation failed: ${error.message}`);
  }
};

// Button JSX
<button
  onClick={handleRestart}
  disabled={!pendingSessionId}
  className="btn btn-danger btn-lg"
  style={{
    backgroundColor: '#dc3545',
    color: 'white',
    padding: '12px 24px',
    fontSize: '16px',
    fontWeight: 'bold'
  }}
>
  🔴 RESTART BACKEND & ACTIVATE MODELS
</button>
```

#### 3. FALLBACK Button (NEW - Add This)
```jsx
const handleFallback = async () => {
  const confirmed = confirm('⚠️ Roll back to previous model version? This will restart the backend.');
  if (!confirmed) return;

  try {
    const response = await fetch('/api/admin/ml-models/fallback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    });

    const data = await response.json();

    if (data.success) {
      toast.success('✅ Rolled back to previous version! Backend restarting...');

      setTimeout(() => {
        window.location.reload();
      }, 5000);
    } else {
      toast.error(data.error || 'No fallback version available');
    }
  } catch (error) {
    toast.error(`Fallback failed: ${error.message}`);
  }
};

// Button JSX
<button
  onClick={handleFallback}
  className="btn btn-warning btn-lg"
  style={{
    padding: '12px 24px',
    fontSize: '16px',
    fontWeight: 'bold'
  }}
>
  ⏪ FALLBACK TO PREVIOUS VERSION
</button>
```

#### 4. Session History Display (NEW - Add This)
```jsx
const [sessions, setSessions] = useState([]);

const loadSessions = async () => {
  try {
    const response = await fetch('/api/admin/ml-models/sessions');
    const data = await response.json();
    setSessions(data);
  } catch (error) {
    console.error('Failed to load sessions:', error);
  }
};

useEffect(() => {
  loadSessions();
  // Reload sessions every 30 seconds
  const interval = setInterval(loadSessions, 30000);
  return () => clearInterval(interval);
}, []);

// Session History JSX
<div className="session-history mt-4">
  <h4>Upload Session History</h4>
  <table className="table table-striped">
    <thead>
      <tr>
        <th>Status</th>
        <th>Files</th>
        <th>Size</th>
        <th>Created</th>
        <th>Activated</th>
      </tr>
    </thead>
    <tbody>
      {sessions.map(session => (
        <tr key={session.id}>
          <td>
            {session.isLive && (
              <span className="badge badge-success">● LIVE</span>
            )}
            {session.isFallback && (
              <span className="badge badge-warning">⏸ FALLBACK</span>
            )}
            {!session.isLive && !session.isFallback && (
              <span className="badge badge-secondary">Archived</span>
            )}
          </td>
          <td>
            <strong>{session.fileCount} files</strong>
            <br />
            <small className="text-muted">
              {session.files.join(', ')}
            </small>
          </td>
          <td>{(session.totalSize / 1024 / 1024).toFixed(2)} MB</td>
          <td>{new Date(session.createdAt).toLocaleString()}</td>
          <td>
            {session.activatedAt
              ? new Date(session.activatedAt).toLocaleString()
              : '-'
            }
          </td>
        </tr>
      ))}
    </tbody>
  </table>
</div>
```

---

## Complete Component Example

```jsx
import React, { useState, useEffect } from 'react';
import { toast } from 'react-toastify'; // or your notification library

function MLModelManagement() {
  const [pendingSessionId, setPendingSessionId] = useState(null);
  const [uploadedFiles, setUploadedFiles] = useState([]);
  const [sessions, setSessions] = useState([]);
  const [isUploading, setIsUploading] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);

  // Load sessions on mount
  useEffect(() => {
    loadSessions();
  }, []);

  const loadSessions = async () => {
    try {
      const response = await fetch('/api/admin/ml-models/sessions');
      const data = await response.json();
      setSessions(data);
    } catch (error) {
      console.error('Failed to load sessions:', error);
    }
  };

  const handleUpload = async (event) => {
    const files = Array.from(event.target.files);
    if (files.length === 0) return;

    setIsUploading(true);
    const formData = new FormData();
    files.forEach(file => formData.append('files', file));

    try {
      const response = await fetch('/api/admin/ml-models/upload', {
        method: 'POST',
        body: formData
      });

      const data = await response.json();

      if (data.success) {
        setPendingSessionId(data.sessionId);
        setUploadedFiles(data.files);
        toast.success(`✅ Uploaded ${data.files.length} files. Click RESTART to activate.`);
        loadSessions(); // Refresh session list
      } else {
        toast.error(data.error || 'Upload failed');
      }
    } catch (error) {
      toast.error(`Upload failed: ${error.message}`);
    } finally {
      setIsUploading(false);
    }
  };

  const handleRestart = async () => {
    if (!pendingSessionId) {
      toast.error('No uploaded session to activate');
      return;
    }

    const confirmed = window.confirm('⚠️ This will restart the backend server. Continue?');
    if (!confirmed) return;

    setIsProcessing(true);

    try {
      const response = await fetch('/api/admin/ml-models/activate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sessionId: pendingSessionId })
      });

      const data = await response.json();

      if (data.success) {
        toast.success('✅ Models activated! Backend restarting in 3 seconds...');
        setPendingSessionId(null);

        // Wait for restart and reload
        setTimeout(() => {
          window.location.reload();
        }, 5000);
      } else {
        toast.error('Failed to activate models');
        setIsProcessing(false);
      }
    } catch (error) {
      toast.error(`Activation failed: ${error.message}`);
      setIsProcessing(false);
    }
  };

  const handleFallback = async () => {
    const confirmed = window.confirm('⚠️ Roll back to previous model version? This will restart the backend.');
    if (!confirmed) return;

    setIsProcessing(true);

    try {
      const response = await fetch('/api/admin/ml-models/fallback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });

      const data = await response.json();

      if (data.success) {
        toast.success('✅ Rolled back to previous version! Backend restarting...');

        setTimeout(() => {
          window.location.reload();
        }, 5000);
      } else {
        toast.error(data.error || 'No fallback version available');
        setIsProcessing(false);
      }
    } catch (error) {
      toast.error(`Fallback failed: ${error.message}`);
      setIsProcessing(false);
    }
  };

  const liveSession = sessions.find(s => s.isLive);
  const fallbackSession = sessions.find(s => s.isFallback);

  return (
    <div className="ml-model-management p-4">
      <h2 className="mb-4">ML Model Management</h2>

      {/* Upload Section */}
      <div className="card mb-4">
        <div className="card-body">
          <h4>Upload New Models</h4>
          <input
            type="file"
            multiple
            onChange={handleUpload}
            disabled={isUploading || isProcessing}
            className="form-control mb-3"
            accept=".pkl,.joblib,.h5,.pb,.pth,.onnx,.pt"
          />

          {pendingSessionId && (
            <div className="alert alert-success">
              <strong>✅ Files Uploaded!</strong>
              <br />
              Session ID: <code>{pendingSessionId}</code>
              <br />
              Files: {uploadedFiles.join(', ')}
            </div>
          )}
        </div>
      </div>

      {/* Action Buttons */}
      <div className="card mb-4">
        <div className="card-body">
          <h4>Actions</h4>
          <div className="d-flex gap-3">
            <button
              onClick={handleRestart}
              disabled={!pendingSessionId || isProcessing}
              className="btn btn-danger btn-lg"
              style={{
                backgroundColor: '#dc3545',
                color: 'white',
                padding: '12px 24px',
                fontSize: '16px',
                fontWeight: 'bold'
              }}
            >
              {isProcessing ? '⏳ Processing...' : '🔴 RESTART BACKEND & ACTIVATE MODELS'}
            </button>

            <button
              onClick={handleFallback}
              disabled={!fallbackSession || isProcessing}
              className="btn btn-warning btn-lg"
              style={{
                padding: '12px 24px',
                fontSize: '16px',
                fontWeight: 'bold'
              }}
            >
              {isProcessing ? '⏳ Processing...' : '⏪ FALLBACK TO PREVIOUS VERSION'}
            </button>
          </div>

          {!fallbackSession && (
            <p className="text-muted mt-2">
              <small>⚠️ No fallback version available. Upload and activate models at least twice to enable fallback.</small>
            </p>
          )}
        </div>
      </div>

      {/* Current Status */}
      <div className="card mb-4">
        <div className="card-body">
          <h4>Current Status</h4>
          <table className="table">
            <tbody>
              <tr>
                <td><strong>Live Session:</strong></td>
                <td>
                  {liveSession ? (
                    <>
                      {liveSession.fileCount} files ({(liveSession.totalSize / 1024 / 1024).toFixed(2)} MB)
                      <br />
                      <small className="text-muted">{liveSession.files.join(', ')}</small>
                    </>
                  ) : (
                    <span className="text-muted">No live session</span>
                  )}
                </td>
              </tr>
              <tr>
                <td><strong>Fallback Available:</strong></td>
                <td>
                  {fallbackSession ? (
                    <>
                      Yes - {fallbackSession.fileCount} files ({(fallbackSession.totalSize / 1024 / 1024).toFixed(2)} MB)
                      <br />
                      <small className="text-muted">{fallbackSession.files.join(', ')}</small>
                    </>
                  ) : (
                    <span className="text-muted">No fallback available</span>
                  )}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      {/* Session History */}
      <div className="card">
        <div className="card-body">
          <h4>Upload Session History</h4>
          <table className="table table-striped">
            <thead>
              <tr>
                <th>Status</th>
                <th>Files</th>
                <th>Size</th>
                <th>Created</th>
                <th>Activated</th>
              </tr>
            </thead>
            <tbody>
              {sessions.length === 0 ? (
                <tr>
                  <td colSpan="5" className="text-center text-muted">
                    No upload sessions yet
                  </td>
                </tr>
              ) : (
                sessions.map(session => (
                  <tr key={session.id}>
                    <td>
                      {session.isLive && (
                        <span className="badge bg-success">● LIVE</span>
                      )}
                      {session.isFallback && (
                        <span className="badge bg-warning">⏸ FALLBACK</span>
                      )}
                      {!session.isLive && !session.isFallback && (
                        <span className="badge bg-secondary">Archived</span>
                      )}
                    </td>
                    <td>
                      <strong>{session.fileCount} files</strong>
                      <br />
                      <small className="text-muted">
                        {session.files.join(', ')}
                      </small>
                    </td>
                    <td>{(session.totalSize / 1024 / 1024).toFixed(2)} MB</td>
                    <td>{new Date(session.createdAt).toLocaleString()}</td>
                    <td>
                      {session.activatedAt
                        ? new Date(session.activatedAt).toLocaleString()
                        : '-'
                      }
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

export default MLModelManagement;
```

---

## UI/UX Flow

### Upload Flow:
1. User selects model files
2. Click "Upload" → Files uploaded, sessionId stored
3. Success message: "Uploaded N files. Click RESTART to activate."
4. **RED RESTART button becomes enabled**

### Activation Flow:
1. Click **🔴 RESTART BACKEND & ACTIVATE MODELS**
2. Confirmation dialog: "⚠️ This will restart the backend server. Continue?"
3. Click "OK" → Backend activates models and restarts
4. Success message: "Models activated! Backend restarting in 3 seconds..."
5. Page auto-reloads after 5 seconds

### Fallback Flow:
1. Click **⏪ FALLBACK TO PREVIOUS VERSION**
2. Confirmation dialog: "⚠️ Roll back to previous model version?"
3. Click "OK" → Backend rolls back and restarts
4. Success message: "Rolled back! Backend restarting..."
5. Page auto-reloads after 5 seconds

---

## Testing Checklist

- [ ] Upload button works and shows success message
- [ ] RESTART button is disabled until files are uploaded
- [ ] RESTART button shows confirmation dialog
- [ ] Backend restarts after clicking RESTART
- [ ] Session history updates after activation
- [ ] FALLBACK button is disabled when no fallback available
- [ ] FALLBACK button shows confirmation dialog
- [ ] Backend restarts after clicking FALLBACK
- [ ] Page reloads automatically after backend restart
- [ ] Session status badges show correctly (LIVE, FALLBACK, Archived)

---

## Notes

- The backend endpoints are **already implemented** ✅
- The frontend **must add these buttons** to use the new features
- Use the complete component example above as a starting point
- Customize styling to match your design system
- Add proper error handling and loading states
- Test thoroughly before deploying to production
