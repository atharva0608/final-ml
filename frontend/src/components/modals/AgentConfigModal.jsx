import React, { useState } from 'react';
import { X, Save } from 'lucide-react';
import Button from '../common/Button';
import api from '../../services/api';

const AgentConfigModal = ({ agent, onClose, onSave }) => {
  const [terminateWaitMinutes, setTerminateWaitMinutes] = useState(agent.terminateWaitMinutes || 30);
  const [autoSwitchEnabled, setAutoSwitchEnabled] = useState(agent.autoSwitchEnabled ?? true);
  const [autoReplicaEnabled, setAutoReplicaEnabled] = useState(agent.autoReplicaEnabled ?? true);
  const [manualReplicaEnabled, setManualReplicaEnabled] = useState(agent.manualReplicaEnabled ?? true);
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.updateAgentConfig(agent.id, {
        terminateWaitMinutes,
        autoSwitchEnabled,
        autoReplicaEnabled,
        manualReplicaEnabled
      });
      onSave();
      onClose();
    } catch (error) {
      alert('Failed to save configuration: ' + error.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto">
        <div className="p-6 border-b border-gray-200 sticky top-0 bg-white">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-xl font-bold text-gray-900">Agent Configuration</h3>
              <p className="text-sm text-gray-500 mt-1 font-mono break-all">{agent.id}</p>
            </div>
            <button onClick={onClose} className="text-gray-400 hover:text-gray-600 transition-colors">
              <X size={24} />
            </button>
          </div>
        </div>

        <div className="p-6 space-y-6">
          {/* Auto-Switch Toggle */}
          <div className="pb-4 border-b border-gray-200">
            <div className="flex items-center justify-between mb-2">
              <div>
                <label className="block text-sm font-medium text-gray-900">
                  Auto-Switch
                </label>
                <p className="text-xs text-gray-500 mt-1">
                  When enabled, ML model recommendations will automatically trigger instance switches.
                  When disabled, recommendations are shown as suggestions only.
                </p>
              </div>
              <label className="relative inline-flex items-center cursor-pointer">
                <input
                  type="checkbox"
                  checked={autoSwitchEnabled}
                  onChange={(e) => setAutoSwitchEnabled(e.target.checked)}
                  className="sr-only peer"
                />
                <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-blue-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600"></div>
              </label>
            </div>
            <p className="text-xs text-blue-600">
              💡 Recommended: Enable for automated cost optimization
            </p>
          </div>

          {/* Auto-Replica Toggle */}
          <div className="pb-4 border-b border-gray-200">
            <div className="flex items-center justify-between mb-2">
              <div>
                <label className="block text-sm font-medium text-gray-900">
                  Auto-Replica (Emergency)
                </label>
                <p className="text-xs text-gray-500 mt-1">
                  Automatically create replicas when AWS sends rebalance recommendations or termination notices.
                  <span className="font-semibold text-red-600"> Emergency scenarios always bypass this setting.</span>
                </p>
              </div>
              <label className="relative inline-flex items-center cursor-pointer">
                <input
                  type="checkbox"
                  checked={autoReplicaEnabled}
                  onChange={(e) => setAutoReplicaEnabled(e.target.checked)}
                  className="sr-only peer"
                />
                <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-orange-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-orange-600"></div>
              </label>
            </div>
            <p className="text-xs text-orange-600">
              ⚡ Recommended: Keep enabled for automatic failover protection
            </p>
          </div>

          {/* Manual Replica Toggle */}
          <div className="pb-4 border-b border-gray-200">
            <div className="flex items-center justify-between mb-2">
              <div>
                <label className="block text-sm font-medium text-gray-900">
                  Manual Replica
                </label>
                <p className="text-xs text-gray-500 mt-1">
                  Allow creating manual replicas for testing or planned maintenance.
                  Manual replicas stay active until you promote or delete them.
                </p>
              </div>
              <label className="relative inline-flex items-center cursor-pointer">
                <input
                  type="checkbox"
                  checked={manualReplicaEnabled}
                  onChange={(e) => setManualReplicaEnabled(e.target.checked)}
                  className="sr-only peer"
                />
                <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-green-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-green-600"></div>
              </label>
            </div>
            <p className="text-xs text-green-600">
              🛡️ Recommended: Enable for manual control over failover preparation
            </p>
          </div>

          {/* Terminate Wait Minutes */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Minimum Retention Before Terminating (minutes)
            </label>
            <input
              type="number"
              value={terminateWaitMinutes}
              onChange={(e) => setTerminateWaitMinutes(parseInt(e.target.value) || 0)}
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              min="1"
              max="1440"
              placeholder="30"
            />
            <p className="text-xs text-gray-500 mt-2">
              Minimum time (in minutes) to wait before terminating an instance after switching.
              This prevents frequent terminations and ensures stability.
            </p>
            <p className="text-xs text-blue-600 mt-1">
              ⏱️ Recommended: 30-60 minutes
            </p>
          </div>
        </div>

        <div className="p-6 border-t border-gray-200 flex justify-end space-x-3 sticky bottom-0 bg-white">
          <Button variant="outline" onClick={onClose} disabled={saving}>
            Cancel
          </Button>
          <Button variant="primary" onClick={handleSave} loading={saving} icon={<Save size={16} />}>
            Save Configuration
          </Button>
        </div>
      </div>
    </div>
  );
};

export default AgentConfigModal;
