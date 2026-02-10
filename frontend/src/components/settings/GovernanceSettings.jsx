import React, { useState, useEffect } from 'react';
import { api } from '../../services/api';
import { FiZap, FiToggleLeft, FiToggleRight, FiSave, FiAlertTriangle, FiShield, FiMoon } from 'react-icons/fi';
import toast from 'react-hot-toast';

/**
 * Automation Settings - System-wide automation and approval controls
 */
const GovernanceSettings = () => {
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [config, setConfig] = useState({
        is_strict_mode: false,
        require_automation_approval: false,
        automation_config: {
            hibernation_defaults: {
                default_strategy: 'NAMESPACE_SLEEP',
                default_prewarm_minutes: 30,
                allow_zero_nodes: true,
                require_approval: false,
            }
        }
    });

    useEffect(() => {
        fetchPolicies();
    }, []);

    const fetchPolicies = async () => {
        try {
            const res = await api.get('/api/v1/governance/policies');
            setConfig({
                is_strict_mode: res.data.is_strict_mode || false,
                require_automation_approval: res.data.require_automation_approval || false,
                automation_config: {
                    hibernation_defaults: {
                        default_strategy: 'NAMESPACE_SLEEP',
                        default_prewarm_minutes: 30,
                        allow_zero_nodes: true,
                        require_approval: false,
                        ...(res.data.automation_config?.hibernation_defaults || {})
                    }
                }
            });
        } catch (err) {
            console.error('Failed to load automation settings', err);
            toast.error('Failed to load automation settings');
        } finally {
            setLoading(false);
        }
    };

    const handleSave = async () => {
        setSaving(true);
        try {
            await api.patch('/api/v1/governance/policies', config);
            toast.success('Automation settings saved successfully');
        } catch (err) {
            console.error(err);
            toast.error('Failed to save settings');
        } finally {
            setSaving(false);
        }
    };

    if (loading) {
        return (
            <div className="flex justify-center items-center h-64">
                <div className="animate-spin h-8 w-8 border-4 border-indigo-500 border-t-transparent rounded-full"></div>
            </div>
        );
    }

    return (
        <div className="p-6 space-y-6 bg-gray-50 min-h-screen">
            {/* Header */}
            <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
                <div className="flex justify-between items-center">
                    <div>
                        <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
                            <FiZap className="text-indigo-600" /> Automation Settings
                        </h1>
                        <p className="text-sm text-gray-500 mt-1">
                            Configure system automation behavior and approval requirements.
                        </p>
                    </div>
                    <button
                        onClick={handleSave}
                        disabled={saving}
                        className="flex items-center gap-2 bg-indigo-600 text-white px-4 py-2 rounded-md hover:bg-indigo-700 disabled:opacity-50 transition-colors"
                    >
                        <FiSave /> {saving ? 'Saving...' : 'Save Changes'}
                    </button>
                </div>
            </div>

            {/* System Approval Controls */}
            <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
                <div className="mb-6">
                    <h2 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
                        <FiShield className="text-purple-600" /> System Approval Controls
                    </h2>
                    <p className="text-sm text-gray-500 mt-1">Configure when human approval is required for automated actions.</p>
                </div>

                <div className="space-y-4">
                    {/* Strict Mode */}
                    <div className="flex items-center justify-between p-4 bg-yellow-50 rounded-lg border border-yellow-200">
                        <div className="flex items-center gap-3">
                            <div className="bg-yellow-100 p-2 rounded-full text-yellow-600">
                                <FiAlertTriangle />
                            </div>
                            <div>
                                <h3 className="font-medium text-yellow-900">Strict Mode (Four-Eyes Principle)</h3>
                                <p className="text-sm text-yellow-700">Require approval for ALL actions triggered by Team Leads and Members.</p>
                            </div>
                        </div>
                        <button
                            onClick={() => setConfig(prev => ({ ...prev, is_strict_mode: !prev.is_strict_mode }))}
                            className={`text-4xl transition-colors ${config.is_strict_mode ? 'text-green-500' : 'text-gray-300'}`}
                        >
                            {config.is_strict_mode ? <FiToggleRight /> : <FiToggleLeft />}
                        </button>
                    </div>

                    {/* System Decisions Approval */}
                    <div className="flex items-center justify-between p-4 bg-purple-50 rounded-lg border border-purple-200">
                        <div className="flex items-center gap-3">
                            <div className="bg-purple-100 p-2 rounded-full text-purple-600">
                                <FiShield />
                            </div>
                            <div>
                                <h3 className="font-medium text-purple-900">Require Approval for System Decisions</h3>
                                <p className="text-sm text-purple-700">System-triggered automated actions (cleanup, hibernation, optimization) require approval before execution.</p>
                            </div>
                        </div>
                        <button
                            onClick={() => setConfig(prev => ({ ...prev, require_automation_approval: !prev.require_automation_approval }))}
                            className={`text-4xl transition-colors ${config.require_automation_approval ? 'text-green-500' : 'text-gray-300'}`}
                        >
                            {config.require_automation_approval ? <FiToggleRight /> : <FiToggleLeft />}
                        </button>
                    </div>
                </div>
            </div>

            {/* Hibernation Defaults */}
            <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
                <h2 className="text-lg font-semibold text-gray-900 flex items-center gap-2 mb-1">
                    <FiMoon className="text-indigo-600" /> Hibernation Defaults
                </h2>
                <p className="text-sm text-gray-500 mb-4">Default settings applied when creating new hibernation schedules.</p>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    {/* Default Strategy */}
                    <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">Default Strategy</label>
                        <select
                            value={config.automation_config?.hibernation_defaults?.default_strategy || 'NAMESPACE_SLEEP'}
                            onChange={(e) => setConfig(prev => ({
                                ...prev,
                                automation_config: {
                                    ...prev.automation_config,
                                    hibernation_defaults: {
                                        ...prev.automation_config?.hibernation_defaults,
                                        default_strategy: e.target.value
                                    }
                                }
                            }))}
                            className="w-full border border-gray-300 rounded-md px-3 py-2 focus:ring-indigo-500 focus:border-indigo-500"
                        >
                            <option value="NAMESPACE_SLEEP">Namespace Sleep (Soft)</option>
                            <option value="NUCLEAR">Nuclear (Hard)</option>
                            <option value="SNAPSHOT_RESTORE">Snapshot & Restore (Safe)</option>
                        </select>
                    </div>

                    {/* Default Pre-warm Minutes */}
                    <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">Default Pre-warm Minutes</label>
                        <input
                            type="number"
                            min="0"
                            max="120"
                            value={config.automation_config?.hibernation_defaults?.default_prewarm_minutes ?? 30}
                            onChange={(e) => setConfig(prev => ({
                                ...prev,
                                automation_config: {
                                    ...prev.automation_config,
                                    hibernation_defaults: {
                                        ...prev.automation_config?.hibernation_defaults,
                                        default_prewarm_minutes: parseInt(e.target.value) || 0
                                    }
                                }
                            }))}
                            className="w-full border border-gray-300 rounded-md px-3 py-2 focus:ring-indigo-500 focus:border-indigo-500"
                        />
                    </div>
                </div>

                <div className="mt-4 space-y-3">
                    {/* Allow Zero Nodes */}
                    <div className="flex items-center justify-between p-3 bg-gray-50 rounded-lg border border-gray-200">
                        <div>
                            <h3 className="text-sm font-medium text-gray-900">Allow Zero Nodes</h3>
                            <p className="text-xs text-gray-500">Allow clusters to scale to zero nodes during hibernation.</p>
                        </div>
                        <button
                            onClick={() => setConfig(prev => ({
                                ...prev,
                                automation_config: {
                                    ...prev.automation_config,
                                    hibernation_defaults: {
                                        ...prev.automation_config?.hibernation_defaults,
                                        allow_zero_nodes: !prev.automation_config?.hibernation_defaults?.allow_zero_nodes
                                    }
                                }
                            }))}
                            className={`text-3xl transition-colors ${config.automation_config?.hibernation_defaults?.allow_zero_nodes ? 'text-green-500' : 'text-gray-300'}`}
                        >
                            {config.automation_config?.hibernation_defaults?.allow_zero_nodes ? <FiToggleRight /> : <FiToggleLeft />}
                        </button>
                    </div>

                    {/* Require Approval for Hibernation */}
                    <div className="flex items-center justify-between p-3 bg-gray-50 rounded-lg border border-gray-200">
                        <div>
                            <h3 className="text-sm font-medium text-gray-900">Require Approval for Hibernation</h3>
                            <p className="text-xs text-gray-500">Require admin approval before hibernation actions execute.</p>
                        </div>
                        <button
                            onClick={() => setConfig(prev => ({
                                ...prev,
                                automation_config: {
                                    ...prev.automation_config,
                                    hibernation_defaults: {
                                        ...prev.automation_config?.hibernation_defaults,
                                        require_approval: !prev.automation_config?.hibernation_defaults?.require_approval
                                    }
                                }
                            }))}
                            className={`text-3xl transition-colors ${config.automation_config?.hibernation_defaults?.require_approval ? 'text-green-500' : 'text-gray-300'}`}
                        >
                            {config.automation_config?.hibernation_defaults?.require_approval ? <FiToggleRight /> : <FiToggleLeft />}
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default GovernanceSettings;
