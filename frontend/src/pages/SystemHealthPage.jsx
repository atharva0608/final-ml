import React, { useState, useEffect } from 'react';
import { Activity, Database, Cpu, Brain, CheckCircle, AlertCircle, RefreshCw, RotateCcw } from 'lucide-react';
import StatCard from '../components/common/StatCard';
import LoadingSpinner from '../components/common/LoadingSpinner';
import Badge from '../components/common/Badge';
import FileUpload from '../components/common/FileUpload';
import Button from '../components/common/Button';
import api from '../services/api';

const SystemHealthPage = () => {
  const [health, setHealth] = useState(null);
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showDecisionEngineUpload, setShowDecisionEngineUpload] = useState(false);
  const [showMLModelsUpload, setShowMLModelsUpload] = useState(false);
  const [restarting, setRestarting] = useState(false);
  const [lastUploadSessionId, setLastUploadSessionId] = useState(null);

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 30000); // Refresh every 30s
    return () => clearInterval(interval);
  }, []);

  const loadData = async () => {
    try {
      const [healthData, sessionsData] = await Promise.all([
        api.getSystemHealth(),
        api.getMLModelSessions().catch(() => [])
      ]);

      setHealth(healthData);
      // Backend returns array directly, not wrapped in object
      setSessions(Array.isArray(sessionsData) ? sessionsData : []);
    } catch (error) {
      console.error('Failed to load data:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleDecisionEngineUpload = async (files) => {
    try {
      const result = await api.uploadDecisionEngine(files);
      alert(`✓ Decision engine files uploaded successfully!\n\nFiles: ${files.map(f => f.name).join(', ')}\n\nClick the RED RESTART button to activate the new engine.`);

      // Don't reload automatically - user must click RESTART
      await loadData();
    } catch (error) {
      alert(`❌ Upload failed: ${error.message}`);
      throw error;
    }
  };

  const handleMLModelsUpload = async (files) => {
    try {
      const result = await api.uploadMLModels(files);

      // Save the session ID for activation
      if (result.sessionId) {
        setLastUploadSessionId(result.sessionId);
      }

      alert(`✓ ML model files uploaded successfully!\n\nFiles: ${files.map(f => f.name).join(', ')}\nSession ID: ${result.sessionId || 'N/A'}\n\nClick the RED RESTART button to activate the new models.`);

      // Reload data to show new session
      await loadData();
    } catch (error) {
      alert(`❌ Upload failed: ${error.message}`);
      throw error;
    }
  };

  const handleActivate = async () => {
    if (!lastUploadSessionId) {
      alert('⚠️ No recent upload session found.\n\nPlease upload ML model files first, then click RESTART.');
      return;
    }

    if (!window.confirm(
      `🔴 RESTART BACKEND WITH NEW MODELS\n\n` +
      `This will:\n` +
      `• Activate uploaded models (Session: ${lastUploadSessionId})\n` +
      `• Restart the backend service\n` +
      `• Take ~10-15 seconds to complete\n\n` +
      `Current models will become the fallback version.\n\n` +
      `Continue?`
    )) {
      return;
    }

    setRestarting(true);
    try {
      const result = await api.activateMLModels(lastUploadSessionId);

      alert(
        `✓ BACKEND RESTARTING...\n\n` +
        `The backend is restarting with new models.\n\n` +
        `⏱️ Please wait 10-15 seconds...\n\n` +
        `The page will reload automatically when ready.`
      );

      // Wait for backend to restart and reload data
      setTimeout(async () => {
        let retries = 0;
        const maxRetries = 20;

        const checkBackend = async () => {
          try {
            await api.healthCheck();
            // Backend is back!
            await loadData();
            setRestarting(false);
            setLastUploadSessionId(null);
            alert('✅ Backend restarted successfully!\n\nNew models are now active.');
          } catch (error) {
            retries++;
            if (retries < maxRetries) {
              setTimeout(checkBackend, 1000); // Check every second
            } else {
              setRestarting(false);
              alert('⚠️ Backend restart is taking longer than expected.\n\nPlease refresh the page manually.');
            }
          }
        };

        checkBackend();
      }, 3000); // Start checking after 3 seconds

    } catch (error) {
      setRestarting(false);
      alert(`❌ Activation failed: ${error.message}`);
    }
  };

  const handleFallback = async () => {
    if (!window.confirm(
      `⚠️ FALLBACK TO PREVIOUS VERSION\n\n` +
      `This will:\n` +
      `• Roll back to the previous model version\n` +
      `• Restart the backend service\n` +
      `• Take ~10-15 seconds to complete\n\n` +
      `Continue?`
    )) {
      return;
    }

    setRestarting(true);
    try {
      const result = await api.fallbackMLModels();

      alert(
        `✓ ROLLING BACK...\n\n` +
        `The backend is restarting with previous models.\n\n` +
        `⏱️ Please wait 10-15 seconds...`
      );

      // Wait for backend to restart
      setTimeout(async () => {
        let retries = 0;
        const maxRetries = 20;

        const checkBackend = async () => {
          try {
            await api.healthCheck();
            await loadData();
            setRestarting(false);
            alert('✅ Fallback completed successfully!\n\nPrevious models are now active.');
          } catch (error) {
            retries++;
            if (retries < maxRetries) {
              setTimeout(checkBackend, 1000);
            } else {
              setRestarting(false);
              alert('⚠️ Fallback is taking longer than expected.\n\nPlease refresh the page manually.');
            }
          }
        };

        checkBackend();
      }, 3000);

    } catch (error) {
      setRestarting(false);
      alert(`❌ Fallback failed: ${error.message}`);
    }
  };

  if (loading) {
    return <div className="flex justify-center items-center h-64"><LoadingSpinner /></div>;
  }

  // Backend returns camelCase fields: isLive, isFallback
  const liveSession = sessions.find(s => s.isLive);
  const fallbackSession = sessions.find(s => s.isFallback);
  const pendingSession = sessions.find(s => !s.isLive && !s.isFallback);

  return (
    <div className="space-y-6">
      {/* Restart Warning Banner */}
      {restarting && (
        <div className="bg-yellow-50 border-l-4 border-yellow-400 p-4 rounded-lg">
          <div className="flex items-center">
            <RefreshCw className="animate-spin h-5 w-5 text-yellow-600 mr-3" />
            <div>
              <p className="text-sm font-medium text-yellow-800">
                Backend is restarting... Please wait 10-15 seconds.
              </p>
              <p className="text-xs text-yellow-700 mt-1">
                Do not close this page or refresh manually.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Action Buttons */}
      {(lastUploadSessionId || fallbackSession) && !restarting && (
        <div className="bg-white p-4 rounded-xl shadow-sm border border-gray-200 flex flex-wrap gap-3">
          {lastUploadSessionId && (
            <Button
              variant="danger"
              size="lg"
              onClick={handleActivate}
              icon={<RefreshCw size={18} />}
              className="flex-1 min-w-[200px]"
            >
              🔴 RESTART WITH NEW MODELS
            </Button>
          )}

          {fallbackSession && (
            <Button
              variant="warning"
              size="lg"
              onClick={handleFallback}
              icon={<RotateCcw size={18} />}
              className="flex-1 min-w-[200px]"
            >
              ↩️ FALLBACK TO PREVIOUS
            </Button>
          )}
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 md:gap-6">
        {/* Decision Engine Card */}
        <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center space-x-3">
              <div className={`p-3 rounded-lg ${
                health?.decisionEngineStatus?.loaded ? 'bg-green-100' : 'bg-red-100'
              }`}>
                <Cpu size={24} className={
                  health?.decisionEngineStatus?.loaded ? 'text-green-600' : 'text-red-600'
                } />
              </div>
              <div>
                <h3 className="text-lg font-bold text-gray-900">Decision Engine</h3>
                <Badge variant={health?.decisionEngineStatus?.loaded ? 'success' : 'danger'}>
                  {health?.decisionEngineStatus?.loaded ? 'Loaded' : 'Not Loaded'}
                </Badge>
              </div>
            </div>
          </div>

          <div className="space-y-3 mt-4">
            <div className="flex justify-between items-center">
              <span className="text-sm text-gray-600">Type:</span>
              <span className="text-sm font-semibold text-gray-900">
                {health?.decisionEngineStatus?.type || 'MLBasedDecisionEngine'}
              </span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm text-gray-600">Version:</span>
              <span className="text-sm font-semibold text-gray-900">
                {health?.decisionEngineStatus?.version || '1.0.0'}
              </span>
            </div>
            {health?.decisionEngineStatus?.loaded && (
              <div className="mt-4 p-3 bg-green-50 rounded-lg border border-green-200">
                <p className="text-xs font-medium text-green-800">
                  ✓ Decision engine loaded and ready
                </p>
              </div>
            )}

            {/* Currently In Use */}
            <div className="mt-4 pt-4 border-t border-gray-200">
              <div className="mb-3">
                <p className="text-xs font-semibold text-gray-700 mb-2">📂 Currently In Use:</p>
                <div className="bg-gray-50 rounded-lg p-2 border border-gray-200">
                  <code className="text-xs text-gray-800 font-mono">
                    decision_engines/ml_based_engine.py
                  </code>
                </div>
              </div>

              <button
                onClick={() => setShowDecisionEngineUpload(!showDecisionEngineUpload)}
                className="w-full text-left text-sm font-semibold text-blue-600 hover:text-blue-800 transition-colors"
              >
                {showDecisionEngineUpload ? '▼' : '▶'} Upload New Decision Engine
              </button>

              {showDecisionEngineUpload && (
                <div className="mt-4">
                  <FileUpload
                    onUpload={handleDecisionEngineUpload}
                    accept=".py,.pkl,.joblib"
                    multiple={false}
                    title="Upload Decision Engine"
                    description="Upload decision engine Python file (.py)"
                  />
                  <p className="text-xs text-gray-500 mt-2">
                    ⚠️ Upload only uploads the file. Click 🔴 RESTART to activate.
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* ML Models Card */}
        <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center space-x-3">
              <div className={`p-3 rounded-lg ${
                liveSession ? 'bg-blue-100' : 'bg-gray-100'
              }`}>
                <Brain size={24} className={
                  liveSession ? 'text-blue-600' : 'text-gray-600'
                } />
              </div>
              <div>
                <h3 className="text-lg font-bold text-gray-900">ML Models</h3>
                <Badge variant={liveSession ? 'success' : 'warning'}>
                  {liveSession ? 'Active' : 'Not Active'}
                </Badge>
              </div>
            </div>
          </div>

          <div className="space-y-3 mt-4">
            {/* Live Session */}
            {liveSession && (
              <div className="p-3 bg-blue-50 rounded-lg border border-blue-200">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-semibold text-blue-900">🟢 LIVE SESSION</span>
                  <Badge variant="success" size="sm">Active</Badge>
                </div>
                <div className="space-y-1">
                  <div className="flex justify-between text-xs">
                    <span className="text-blue-700">Files:</span>
                    <span className="font-semibold text-blue-900">{liveSession.fileCount || 0}</span>
                  </div>
                  <div className="text-xs text-blue-600">
                    {liveSession.files && liveSession.files.length > 0 ? liveSession.files.join(', ') : 'N/A'}
                  </div>
                </div>
              </div>
            )}

            {/* Fallback Session */}
            {fallbackSession && (
              <div className="p-3 bg-orange-50 rounded-lg border border-orange-200">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-semibold text-orange-900">🟡 FALLBACK SESSION</span>
                  <Badge variant="warning" size="sm">Standby</Badge>
                </div>
                <div className="space-y-1">
                  <div className="flex justify-between text-xs">
                    <span className="text-orange-700">Files:</span>
                    <span className="font-semibold text-orange-900">{fallbackSession.fileCount || 0}</span>
                  </div>
                  <div className="text-xs text-orange-600">
                    {fallbackSession.files && fallbackSession.files.length > 0 ? fallbackSession.files.join(', ') : 'N/A'}
                  </div>
                </div>
              </div>
            )}

            {/* Pending Upload */}
            {pendingSession && (
              <div className="p-3 bg-yellow-50 rounded-lg border border-yellow-200">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-semibold text-yellow-900">⏳ PENDING ACTIVATION</span>
                  <Badge variant="warning" size="sm">Uploaded</Badge>
                </div>
                <div className="space-y-1">
                  <div className="flex justify-between text-xs">
                    <span className="text-yellow-700">Files:</span>
                    <span className="font-semibold text-yellow-900">{pendingSession.fileCount || 0}</span>
                  </div>
                  <div className="text-xs text-yellow-600">
                    {pendingSession.files && pendingSession.files.length > 0 ? pendingSession.files.join(', ') : 'N/A'}
                  </div>
                  <p className="text-xs text-yellow-800 mt-2 font-medium">
                    ⚠️ Click 🔴 RESTART to activate these models
                  </p>
                </div>
              </div>
            )}

            {!liveSession && !fallbackSession && !pendingSession && (
              <div className="mt-4 p-3 bg-gray-50 rounded-lg border border-gray-200">
                <p className="text-xs text-gray-600">No model sessions found</p>
              </div>
            )}

            {/* Currently In Use */}
            <div className="mt-4 pt-4 border-t border-gray-200">
              <div className="mb-3">
                <p className="text-xs font-semibold text-gray-700 mb-2">📂 Currently In Use:</p>
                {liveSession ? (
                  <div className="bg-blue-50 rounded-lg p-3 border border-blue-200">
                    <div className="space-y-1">
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-blue-700">Files:</span>
                        <span className="text-xs font-semibold text-blue-900">
                          {liveSession.fileCount || 0} file{liveSession.fileCount !== 1 ? 's' : ''}
                        </span>
                      </div>
                      {liveSession.files && liveSession.files.map((filename, idx) => (
                        <div key={idx} className="flex items-center space-x-2 mt-2">
                          <CheckCircle size={12} className="text-blue-600 flex-shrink-0" />
                          <code className="text-xs text-blue-800 font-mono break-all">
                            {filename}
                          </code>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : (
                  <div className="bg-gray-50 rounded-lg p-2 border border-gray-200">
                    <p className="text-xs text-gray-600 italic">No active model files</p>
                  </div>
                )}
              </div>

              <button
                onClick={() => setShowMLModelsUpload(!showMLModelsUpload)}
                className="w-full text-left text-sm font-semibold text-blue-600 hover:text-blue-800 transition-colors"
              >
                {showMLModelsUpload ? '▼' : '▶'} Upload New ML Models
              </button>

              {showMLModelsUpload && (
                <div className="mt-4">
                  <FileUpload
                    onUpload={handleMLModelsUpload}
                    accept=".pkl,.joblib,.h5,.pb,.pth,.onnx,.pt"
                    multiple={true}
                    title="Upload ML Models"
                    description="Upload ML model files (multiple supported)"
                  />
                  <p className="text-xs text-gray-500 mt-2">
                    ⚠️ Upload only uploads the files. Click 🔴 RESTART to activate.
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default SystemHealthPage;
