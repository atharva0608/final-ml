import React, { useState, useEffect } from 'react';
import {
    Settings,
    TrendingDown,
    Zap,
    Server,
    Cpu,
    HardDrive,
    CheckCircle,
    AlertCircle,
    ChevronRight,
    Info,
    Save
} from 'lucide-react';

const OptimizationSettings = ({ clusterId }) => {
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [settings, setSettings] = useState(null);

    // Mock optimization settings data
    const mockSettings = {
        clusterId: clusterId || 'cluster-1',
        clusterName: 'production-cluster',
        workloadRightsizing: {
            enabled: true,
            currentEfficiency: 19.98,
            waste: {
                cpu: 1.47,
                memory: 6.43
            },
            savedAmount: 2557.08,
            additionalSavings: 35.8
        },
        spotInstances: {
            enabled: true,
            mode: 'friendly_only', // 'all' or 'friendly_only'
            workloadsToRunOnSpot: 45,
            additionalActionsNeeded: 3,
            availableSavings: 28.5
        },
        armSupport: {
            enabled: false,
            cpuPercentage: 0,
            availableSavings: 15.2
        }
    };

    useEffect(() => {
        // Simulate API call
        setTimeout(() => {
            setSettings(mockSettings);
            setLoading(false);
        }, 500);
    }, [clusterId]);

    const handleToggle = (category, value) => {
        setSettings(prev => ({
            ...prev,
            [category]: {
                ...prev[category],
                enabled: value
            }
        }));
    };

    const handleSpotModeChange = (mode) => {
        setSettings(prev => ({
            ...prev,
            spotInstances: {
                ...prev.spotInstances,
                mode: mode
            }
        }));
    };

    const handleArmPercentageChange = (percentage) => {
        setSettings(prev => ({
            ...prev,
            armSupport: {
                ...prev.armSupport,
                cpuPercentage: parseInt(percentage)
            }
        }));
    };

    const handleSave = async () => {
        setSaving(true);
        // Simulate API call
        await new Promise(resolve => setTimeout(resolve, 1000));
        setSaving(false);
        alert('Optimization settings saved successfully!');
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center h-96">
                <div className="text-center">
                    <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
                    <p className="text-gray-600">Loading optimization settings...</p>
                </div>
            </div>
        );
    }

    if (!settings) {
        return (
            <div className="text-center py-12">
                <AlertCircle className="w-12 h-12 text-gray-400 mx-auto mb-4" />
                <h3 className="text-lg font-semibold text-gray-900 mb-2">No settings available</h3>
                <p className="text-gray-600">Unable to load optimization settings</p>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900">Optimization Settings</h1>
                    <p className="text-sm text-gray-500 mt-1">
                        Configure cost optimization policies for {settings.clusterName}
                    </p>
                </div>
                <button
                    onClick={handleSave}
                    disabled={saving}
                    className={`flex items-center gap-2 px-4 py-2 rounded-lg transition-colors ${
                        saving
                            ? 'bg-gray-400 cursor-not-allowed'
                            : 'bg-blue-600 hover:bg-blue-700'
                    } text-white`}
                >
                    <Save className="w-4 h-4" />
                    {saving ? 'Saving...' : 'Save Changes'}
                </button>
            </div>

            {/* Workload Rightsizing Section */}
            <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
                <div className="p-6 border-b border-gray-200">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                            <div className="w-10 h-10 bg-blue-100 rounded-lg flex items-center justify-center">
                                <TrendingDown className="w-5 h-5 text-blue-600" />
                            </div>
                            <div>
                                <h2 className="text-lg font-semibold text-gray-900">Workload Rightsizing</h2>
                                <p className="text-sm text-gray-600">Optimize resource requests and limits</p>
                            </div>
                        </div>
                        <label className="relative inline-flex items-center cursor-pointer">
                            <input
                                type="checkbox"
                                checked={settings.workloadRightsizing.enabled}
                                onChange={(e) => handleToggle('workloadRightsizing', e.target.checked)}
                                className="sr-only peer"
                            />
                            <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-blue-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600"></div>
                            <span className="ml-3 text-sm font-medium text-gray-900">
                                {settings.workloadRightsizing.enabled ? 'Enabled' : 'Disabled'}
                            </span>
                        </label>
                    </div>
                </div>

                {settings.workloadRightsizing.enabled && (
                    <div className="p-6 bg-gray-50">
                        {/* Efficiency Metrics Grid */}
                        <div className="grid grid-cols-4 gap-4">
                            <div className="bg-white rounded-lg border border-gray-200 p-4">
                                <div className="text-sm text-gray-600 mb-1">Current Efficiency</div>
                                <div className="text-2xl font-bold text-gray-900">
                                    {settings.workloadRightsizing.currentEfficiency}%
                                </div>
                                <div className="flex items-center gap-1 mt-2">
                                    <div className="flex-1 bg-gray-200 rounded-full h-2">
                                        <div
                                            className="bg-orange-500 rounded-full h-2"
                                            style={{ width: `${settings.workloadRightsizing.currentEfficiency}%` }}
                                        ></div>
                                    </div>
                                </div>
                            </div>

                            <div className="bg-white rounded-lg border border-gray-200 p-4">
                                <div className="text-sm text-gray-600 mb-1">Waste</div>
                                <div className="space-y-1">
                                    <div className="flex items-center justify-between text-sm">
                                        <span className="text-gray-600">CPU</span>
                                        <span className="font-medium text-gray-900">
                                            {settings.workloadRightsizing.waste.cpu} cores
                                        </span>
                                    </div>
                                    <div className="flex items-center justify-between text-sm">
                                        <span className="text-gray-600">Memory</span>
                                        <span className="font-medium text-gray-900">
                                            {settings.workloadRightsizing.waste.memory} GiB
                                        </span>
                                    </div>
                                </div>
                            </div>

                            <div className="bg-white rounded-lg border border-gray-200 p-4">
                                <div className="text-sm text-gray-600 mb-1">$ Saved by Rightsizing</div>
                                <div className="text-2xl font-bold text-green-600">
                                    ${settings.workloadRightsizing.savedAmount.toLocaleString()}
                                </div>
                                <div className="text-xs text-gray-500 mt-1">per month</div>
                            </div>

                            <div className="bg-white rounded-lg border border-gray-200 p-4">
                                <div className="text-sm text-gray-600 mb-1">Additional Savings</div>
                                <div className="text-2xl font-bold text-blue-600">
                                    {settings.workloadRightsizing.additionalSavings}%
                                </div>
                                <button className="mt-2 text-xs text-blue-600 hover:text-blue-700 flex items-center gap-1">
                                    View Report
                                    <ChevronRight className="w-3 h-3" />
                                </button>
                            </div>
                        </div>

                        <div className="mt-4 flex items-start gap-2 p-3 bg-blue-50 border border-blue-200 rounded-lg">
                            <Info className="w-4 h-4 text-blue-600 flex-shrink-0 mt-0.5" />
                            <p className="text-sm text-blue-800">
                                Rightsizing automatically adjusts CPU and memory requests based on actual usage patterns to eliminate waste.
                            </p>
                        </div>
                    </div>
                )}
            </div>

            {/* Spot Instances Section */}
            <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
                <div className="p-6 border-b border-gray-200">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                            <div className="w-10 h-10 bg-green-100 rounded-lg flex items-center justify-center">
                                <Zap className="w-5 h-5 text-green-600" />
                            </div>
                            <div>
                                <h2 className="text-lg font-semibold text-gray-900">Use Spot Instances</h2>
                                <p className="text-sm text-gray-600">Reduce costs with spot/preemptible instances</p>
                            </div>
                        </div>
                        <label className="relative inline-flex items-center cursor-pointer">
                            <input
                                type="checkbox"
                                checked={settings.spotInstances.enabled}
                                onChange={(e) => handleToggle('spotInstances', e.target.checked)}
                                className="sr-only peer"
                            />
                            <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-green-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-green-600"></div>
                            <span className="ml-3 text-sm font-medium text-gray-900">
                                {settings.spotInstances.enabled ? 'Enabled' : 'Disabled'}
                            </span>
                        </label>
                    </div>
                </div>

                {settings.spotInstances.enabled && (
                    <div className="p-6 bg-gray-50">
                        <div className="space-y-4">
                            {/* Spot Mode Selection */}
                            <div>
                                <label className="text-sm font-medium text-gray-700 mb-2 block">
                                    Workload Selection
                                </label>
                                <div className="space-y-2">
                                    <label className="flex items-center gap-3 p-3 bg-white border border-gray-200 rounded-lg cursor-pointer hover:border-green-300 transition-colors">
                                        <input
                                            type="radio"
                                            name="spotMode"
                                            value="all"
                                            checked={settings.spotInstances.mode === 'all'}
                                            onChange={(e) => handleSpotModeChange(e.target.value)}
                                            className="w-4 h-4 text-green-600 focus:ring-green-500"
                                        />
                                        <div className="flex-1">
                                            <div className="text-sm font-medium text-gray-900">All workloads</div>
                                            <div className="text-xs text-gray-600">
                                                Run all compatible workloads on spot instances
                                            </div>
                                        </div>
                                    </label>

                                    <label className="flex items-center gap-3 p-3 bg-white border border-gray-200 rounded-lg cursor-pointer hover:border-green-300 transition-colors">
                                        <input
                                            type="radio"
                                            name="spotMode"
                                            value="friendly_only"
                                            checked={settings.spotInstances.mode === 'friendly_only'}
                                            onChange={(e) => handleSpotModeChange(e.target.value)}
                                            className="w-4 h-4 text-green-600 focus:ring-green-500"
                                        />
                                        <div className="flex-1">
                                            <div className="text-sm font-medium text-gray-900">
                                                Spot-friendly workloads only
                                            </div>
                                            <div className="text-xs text-gray-600">
                                                Only run fault-tolerant workloads on spot instances
                                            </div>
                                        </div>
                                    </label>
                                </div>
                            </div>

                            {/* Metrics */}
                            <div className="grid grid-cols-3 gap-4">
                                <div className="bg-white rounded-lg border border-gray-200 p-4">
                                    <div className="text-sm text-gray-600 mb-1">Workloads to Run on Spot</div>
                                    <div className="text-2xl font-bold text-gray-900">
                                        {settings.spotInstances.workloadsToRunOnSpot}
                                    </div>
                                    <div className="text-xs text-gray-500 mt-1">eligible workloads</div>
                                </div>

                                <div className="bg-white rounded-lg border border-gray-200 p-4">
                                    <div className="text-sm text-gray-600 mb-1">Additional Actions Needed</div>
                                    <div className="text-2xl font-bold text-orange-600">
                                        {settings.spotInstances.additionalActionsNeeded}
                                    </div>
                                    <button className="mt-1 text-xs text-blue-600 hover:text-blue-700 flex items-center gap-1">
                                        View Details
                                        <ChevronRight className="w-3 h-3" />
                                    </button>
                                </div>

                                <div className="bg-white rounded-lg border border-gray-200 p-4">
                                    <div className="text-sm text-gray-600 mb-1">Available Savings</div>
                                    <div className="text-2xl font-bold text-green-600">
                                        {settings.spotInstances.availableSavings}%
                                    </div>
                                    <div className="text-xs text-gray-500 mt-1">cost reduction</div>
                                </div>
                            </div>
                        </div>
                    </div>
                )}
            </div>

            {/* ARM Support Section */}
            <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
                <div className="p-6 border-b border-gray-200">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                            <div className="w-10 h-10 bg-purple-100 rounded-lg flex items-center justify-center">
                                <Cpu className="w-5 h-5 text-purple-600" />
                            </div>
                            <div>
                                <h2 className="text-lg font-semibold text-gray-900">ARM Support</h2>
                                <p className="text-sm text-gray-600">Use ARM-based instances for better price/performance</p>
                            </div>
                        </div>
                        <label className="relative inline-flex items-center cursor-pointer">
                            <input
                                type="checkbox"
                                checked={settings.armSupport.enabled}
                                onChange={(e) => handleToggle('armSupport', e.target.checked)}
                                className="sr-only peer"
                            />
                            <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-purple-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-purple-600"></div>
                            <span className="ml-3 text-sm font-medium text-gray-900">
                                {settings.armSupport.enabled ? 'Enabled' : 'Disabled'}
                            </span>
                        </label>
                    </div>
                </div>

                {settings.armSupport.enabled && (
                    <div className="p-6 bg-gray-50">
                        <div className="space-y-4">
                            {/* ARM CPU Percentage Slider */}
                            <div>
                                <div className="flex items-center justify-between mb-2">
                                    <label className="text-sm font-medium text-gray-700">
                                        Target ARM CPU Percentage
                                    </label>
                                    <span className="text-sm font-semibold text-purple-600">
                                        {settings.armSupport.cpuPercentage}%
                                    </span>
                                </div>
                                <input
                                    type="range"
                                    min="0"
                                    max="100"
                                    step="5"
                                    value={settings.armSupport.cpuPercentage}
                                    onChange={(e) => handleArmPercentageChange(e.target.value)}
                                    className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-purple-600"
                                />
                                <div className="flex justify-between text-xs text-gray-600 mt-1">
                                    <span>0%</span>
                                    <span>25%</span>
                                    <span>50%</span>
                                    <span>75%</span>
                                    <span>100%</span>
                                </div>
                            </div>

                            {/* Available Savings */}
                            <div className="bg-white rounded-lg border border-gray-200 p-4">
                                <div className="text-sm text-gray-600 mb-1">Available Savings with ARM</div>
                                <div className="text-2xl font-bold text-purple-600">
                                    {settings.armSupport.availableSavings}%
                                </div>
                                <div className="text-xs text-gray-500 mt-1">compared to x86 instances</div>
                            </div>

                            <div className="flex items-start gap-2 p-3 bg-purple-50 border border-purple-200 rounded-lg">
                                <Info className="w-4 h-4 text-purple-600 flex-shrink-0 mt-0.5" />
                                <p className="text-sm text-purple-800">
                                    ARM instances (AWS Graviton, Azure Ampere) offer better price-performance for compatible workloads. Ensure your applications are ARM-compatible before enabling.
                                </p>
                            </div>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
};

export default OptimizationSettings;
