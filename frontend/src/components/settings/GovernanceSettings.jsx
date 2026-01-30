import React, { useState, useEffect } from 'react';
import { api } from '../../services/api';
import { FiSettings, FiShield, FiTag, FiZap, FiToggleLeft, FiToggleRight, FiSave, FiAlertTriangle } from 'react-icons/fi';
import toast from 'react-hot-toast';

/**
 * GovernanceSettings - Feature 4: Automated Governance / Policy-as-Code
 * Admin-only page for configuring automated cleanup policies and approval workflows.
 */
const GovernanceSettings = ({ embedded = false }) => {
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [config, setConfig] = useState({
        is_governance_enabled: false,
        is_strict_mode: false,
        require_automation_approval: false,
        required_tags: ['Owner', 'Environment'],
        policies: {
            critical_actions: []
        }
    });

    useEffect(() => {
        fetchPolicies();
    }, []);

    const fetchPolicies = async () => {
        try {
            const res = await api.get('/api/v1/governance/policies');
            setConfig(prev => ({
                ...res.data,
                policies: {
                    ...res.data.policies,
                    critical_actions: res.data.policies?.critical_actions || []
                }
            }));
        } catch (err) {
            console.error('Failed to load governance policies', err);
            toast.error('Failed to load policies');
        } finally {
            setLoading(false);
        }
    };

    const handleSave = async () => {
        setSaving(true);
        try {
            await api.patch('/api/v1/governance/policies', config);
            toast.success('Policies saved successfully');
        } catch (err) {
            console.error(err);
            toast.error('Failed to save policies');
        } finally {
            setSaving(false);
        }
    };

    const toggleMasterSwitch = () => {
        setConfig(prev => ({ ...prev, is_governance_enabled: !prev.is_governance_enabled }));
    };

    const togglePolicy = (policyKey) => {
        setConfig(prev => ({
            ...prev,
            policies: {
                ...prev.policies,
                [policyKey]: {
                    ...prev.policies[policyKey],
                    enabled: !prev.policies[policyKey]?.enabled
                }
            }
        }));
    };

    const toggleCriticalAction = (action) => {
        const currentActions = config.policies.critical_actions || [];
        const newActions = currentActions.includes(action)
            ? currentActions.filter(a => a !== action)
            : [...currentActions, action];

        setConfig(prev => ({
            ...prev,
            policies: {
                ...prev.policies,
                critical_actions: newActions
            }
        }));
    };

    const criticalActionOptions = [
        { value: 'TERMINATE_INSTANCE', label: 'Terminate Instance' },
        { value: 'DELETE_VOLUME', label: 'Delete Volume' },
        { value: 'DELETE_SNAPSHOT', label: 'Delete Snapshot' },
        { value: 'RELEASE_IP', label: 'Release Elastic IP' }
    ];

    const policyCards = [
        {
            key: 'auto_release_orphaned_ips',
            title: 'Auto-Release Unused Elastic IPs',
            description: 'Automatically release unattached Elastic IPs to save costs.',
            icon: FiZap,
            color: 'blue'
        },
        {
            key: 'auto_delete_orphaned_volumes',
            title: 'Auto-Delete Orphaned Volumes',
            description: 'Delete EBS volumes that have been unattached for 30+ days.',
            icon: FiShield,
            color: 'yellow'
        },
        {
            key: 'auto_delete_orphaned_snapshots',
            title: 'Auto-Delete Orphaned Snapshots',
            description: 'Delete snapshots whose parent volumes no longer exist.',
            icon: FiShield,
            color: 'red'
        }
    ];

    if (loading) {
        return (
            <div className="flex justify-center items-center h-64">
                <div className="animate-spin h-8 w-8 border-4 border-indigo-500 border-t-transparent rounded-full"></div>
            </div>
        );
    }

    return (
        <div className={embedded ? "space-y-6" : "p-6 space-y-6 bg-gray-50 min-h-screen"}>
            {/* Header - Show only if NOT embedded */}
            {!embedded && (
                <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
                    <div className="flex justify-between items-center">
                        <div>
                            <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
                                <FiSettings className="text-indigo-600" /> Automated Governance
                            </h1>
                            <p className="text-sm text-gray-500 mt-1">
                                Configure policy-as-code rules for automatic resource cleanup and approval workflows.
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

                    {/* Master Toggle for Non-Embedded Page */}
                    <div className="mt-6 p-4 bg-indigo-50 rounded-lg border border-indigo-100 flex justify-between items-center">
                        <div className="flex items-center gap-3">
                            <div className="bg-indigo-100 p-2 rounded-full text-indigo-600">
                                <FiZap className="w-6 h-6" />
                            </div>
                            <div>
                                <h3 className="font-semibold text-indigo-900">Enable Automated Governance</h3>
                                <p className="text-sm text-indigo-700">When enabled, the system will automatically execute cleanup actions based on the rules below.</p>
                            </div>
                        </div>
                        <button
                            onClick={toggleMasterSwitch}
                            className={`text-4xl transition-colors ${config.is_governance_enabled ? 'text-green-500' : 'text-gray-300'}`}
                        >
                            {config.is_governance_enabled ? <FiToggleRight /> : <FiToggleLeft />}
                        </button>
                    </div>
                </div>
            )}

            {/* Embedded Header Bar */}
            {embedded && (
                <div className="flex justify-between items-center mb-4">
                    <div className="flex items-center gap-3 bg-indigo-50 px-4 py-3 rounded-lg border border-indigo-100 flex-1 mr-4">
                        <div className="bg-indigo-100 p-1.5 rounded-full text-indigo-600">
                            <FiZap className="w-5 h-5" />
                        </div>
                        <div className="flex-1">
                            <h3 className="text-sm font-semibold text-indigo-900">Enable Automated Governance</h3>
                        </div>
                        <button
                            onClick={toggleMasterSwitch}
                            className={`text-3xl transition-colors ${config.is_governance_enabled ? 'text-green-500' : 'text-gray-300'}`}
                        >
                            {config.is_governance_enabled ? <FiToggleRight /> : <FiToggleLeft />}
                        </button>
                    </div>

                    <button
                        onClick={handleSave}
                        disabled={saving}
                        className="flex items-center gap-2 bg-indigo-600 text-white px-4 py-2 rounded-md hover:bg-indigo-700 disabled:opacity-50 transition-colors text-sm"
                    >
                        <FiSave /> {saving ? 'Saving...' : 'Save Changes'}
                    </button>
                </div>
            )}

            {/* Approval Workflows */}
            <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
                <div className="flex justify-between items-start mb-6">
                    <div>
                        <h2 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
                            <FiShield className="text-purple-600" /> Approval Workflows
                        </h2>
                        <p className="text-sm text-gray-500 mt-1">Configure when human approval is required before execution.</p>
                    </div>
                </div>

                <div className="space-y-6">
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

                    {/* System Action Approval - THIS IS THE MISSING TOGGLE */}
                    <div className="flex items-center justify-between p-4 bg-purple-50 rounded-lg border border-purple-200">
                        <div className="flex items-center gap-3">
                            <div className="bg-purple-100 p-2 rounded-full text-purple-600">
                                <FiShield />
                            </div>
                            <div>
                                <h3 className="font-medium text-purple-900">System Action Approval</h3>
                                <p className="text-sm text-purple-700">Require approval for automated system actions (e.g., Scheduled Cleanup).</p>
                            </div>
                        </div>
                        <button
                            onClick={() => setConfig(prev => ({ ...prev, require_automation_approval: !prev.require_automation_approval }))}
                            className={`text-4xl transition-colors ${config.require_automation_approval ? 'text-green-500' : 'text-gray-300'}`}
                        >
                            {config.require_automation_approval ? <FiToggleRight /> : <FiToggleLeft />}
                        </button>
                    </div>

                    {/* Critical Actions */}
                    <div>
                        <h3 className="font-medium text-gray-700 mb-3 flex items-center gap-2">
                            Critical Actions
                            <span className="text-xs bg-gray-100 text-gray-500 px-2 py-0.5 rounded">Always Require Approval</span>
                        </h3>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                            {criticalActionOptions.map(option => (
                                <label key={option.value} className="flex items-center gap-3 p-3 border rounded-lg cursor-pointer hover:bg-gray-50 transition-colors">
                                    <input
                                        type="checkbox"
                                        checked={(config.policies.critical_actions || []).includes(option.value)}
                                        onChange={() => toggleCriticalAction(option.value)}
                                        className="h-4 w-4 rounded text-indigo-600 focus:ring-indigo-500 border-gray-300"
                                    />
                                    <span className="text-sm font-medium text-gray-700">{option.label}</span>
                                </label>
                            ))}
                        </div>
                    </div>
                </div>
            </div>

            {/* Cleanup Policies */}
            <h2 className="text-lg font-semibold text-gray-900 px-1">Cleanup Policies</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {policyCards.map(policy => {
                    const isEnabled = config.policies[policy.key]?.enabled || false;
                    const Icon = policy.icon;
                    return (
                        <div key={policy.key} className={`bg-white p-5 rounded-lg shadow-sm border-l-4 transition-all ${isEnabled ? 'border-green-500' : 'border-gray-300 opacity-75'}`}>
                            <div className="flex justify-between items-start h-full flex-col">
                                <div className="flex items-center gap-3 mb-4">
                                    <div className={`p-2 rounded-full bg-${policy.color}-100`}>
                                        <Icon className={`text-${policy.color}-600`} />
                                    </div>
                                    <div>
                                        <h3 className="font-semibold text-gray-900">{policy.title}</h3>
                                    </div>
                                </div>
                                <p className="text-sm text-gray-500 mb-4 flex-grow">{policy.description}</p>
                                <div className="w-full flex justify-end pt-2 border-t border-gray-100">
                                    <button
                                        onClick={() => togglePolicy(policy.key)}
                                        disabled={!config.is_governance_enabled}
                                        className={`text-3xl transition-colors ${isEnabled ? 'text-green-500' : 'text-gray-300'} disabled:opacity-50`}
                                    >
                                        {isEnabled ? <FiToggleRight /> : <FiToggleLeft />}
                                    </button>
                                </div>
                            </div>
                        </div>
                    );
                })}
            </div>

            {/* Tag Compliance Settings */}
            <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
                <h2 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
                    <FiTag className="text-purple-600" /> Tag Compliance Settings
                </h2>
                <p className="text-sm text-gray-500 mt-1">Define which tags are required on all resources for compliance reporting.</p>

                <div className="mt-4">
                    <label className="block text-sm font-medium text-gray-700 mb-2">Required Tags (comma-separated)</label>
                    <input
                        type="text"
                        value={config.required_tags?.join(', ') || ''}
                        onChange={(e) => setConfig(prev => ({
                            ...prev,
                            required_tags: e.target.value.split(',').map(t => t.trim()).filter(Boolean)
                        }))}
                        className="w-full border border-gray-300 rounded-md px-3 py-2 focus:ring-indigo-500 focus:border-indigo-500"
                        placeholder="Owner, Environment, CostCenter"
                    />
                </div>
            </div>
        </div>
    );
};

export default GovernanceSettings;
