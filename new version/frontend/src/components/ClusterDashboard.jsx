import React, { useState, useEffect } from 'react';
import {
    Server,
    TrendingUp,
    Cpu,
    HardDrive,
    Package,
    Activity,
    Clock,
    Shield,
    CheckCircle,
    AlertCircle,
    XCircle,
    Zap,
    Moon,
    Settings,
    ChevronRight
} from 'lucide-react';

const ClusterDashboard = () => {
    const [clusterData, setClusterData] = useState(null);
    const [loading, setLoading] = useState(true);

    // Mock data for demonstration
    const mockClusterData = {
        cluster: {
            id: 'cluster-1',
            name: 'production-cluster',
            status: 'CONNECTED',
            provider: 'AWS EKS',
            region: 'us-east-1',
            version: '1.28',
            createdAt: '2024-11-15'
        },
        nodes: {
            total: 12,
            onDemand: 3,
            spot: 8,
            fallback: 1,
            platformManaged: 9,
            cloudManaged: 3,
            totalCpu: 48,
            totalMemory: 192, // GB
            cpuUtilization: 67,
            memoryUtilization: 72,
            storageUtilization: 45
        },
        workloads: {
            totalPods: 156,
            scheduledPods: 152,
            pendingPods: 4,
            deployments: 23,
            statefulSets: 8,
            daemonSets: 5
        },
        autoscaler: {
            enabled: true,
            totalPolicies: 3,
            enabledPolicies: 2,
            policies: [
                { name: 'Unscheduled Pods', enabled: true },
                { name: 'Node Deletion', enabled: true },
                { name: 'Evictor', enabled: false }
            ]
        },
        hibernation: {
            totalSchedules: 2,
            activeSchedules: 1,
            schedules: [
                { name: 'Weekday Schedule', enabled: true, nextAction: '2025-12-27 08:00' },
                { name: 'Weekend Hibernation', enabled: false, nextAction: null }
            ]
        },
        resources: {
            cpu: {
                total: 48,
                used: 32,
                available: 16,
                utilization: 67
            },
            memory: {
                total: 192, // GB
                used: 138,
                available: 54,
                utilization: 72
            },
            storage: {
                total: 2000, // GB
                used: 900,
                available: 1100,
                utilization: 45
            }
        }
    };

    useEffect(() => {
        // Simulate API call
        setTimeout(() => {
            setClusterData(mockClusterData);
            setLoading(false);
        }, 500);
    }, []);

    const getStatusBadge = (status) => {
        const configs = {
            CONNECTED: { color: 'bg-green-100 text-green-700 border-green-300', icon: CheckCircle, label: 'Connected' },
            DISCONNECTED: { color: 'bg-gray-100 text-gray-600 border-gray-300', icon: XCircle, label: 'Disconnected' },
            READ_ONLY: { color: 'bg-yellow-100 text-yellow-700 border-yellow-300', icon: Shield, label: 'Read-only' },
            ERROR: { color: 'bg-red-100 text-red-700 border-red-300', icon: AlertCircle, label: 'Error' }
        };

        const config = configs[status] || configs.DISCONNECTED;
        const Icon = config.icon;

        return (
            <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium border ${config.color}`}>
                <Icon className="w-3.5 h-3.5" />
                {config.label}
            </span>
        );
    };

    const renderDonutChart = (percentage, label, color = 'blue') => {
        const circumference = 2 * Math.PI * 40; // radius = 40
        const offset = circumference - (percentage / 100) * circumference;

        const colorMap = {
            blue: 'stroke-blue-600',
            green: 'stroke-green-600',
            purple: 'stroke-purple-600'
        };

        return (
            <div className="flex flex-col items-center">
                <div className="relative w-32 h-32">
                    <svg className="transform -rotate-90 w-32 h-32">
                        <circle
                            cx="64"
                            cy="64"
                            r="40"
                            stroke="currentColor"
                            strokeWidth="8"
                            fill="transparent"
                            className="text-gray-200"
                        />
                        <circle
                            cx="64"
                            cy="64"
                            r="40"
                            stroke="currentColor"
                            strokeWidth="8"
                            fill="transparent"
                            strokeDasharray={circumference}
                            strokeDashoffset={offset}
                            className={colorMap[color] || colorMap.blue}
                        />
                    </svg>
                    <div className="absolute inset-0 flex items-center justify-center">
                        <span className="text-2xl font-bold text-gray-900">{percentage}%</span>
                    </div>
                </div>
                <div className="mt-2 text-sm font-medium text-gray-600">{label}</div>
            </div>
        );
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center h-96">
                <div className="text-center">
                    <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
                    <p className="text-gray-600">Loading cluster dashboard...</p>
                </div>
            </div>
        );
    }

    if (!clusterData) {
        return (
            <div className="text-center py-12">
                <AlertCircle className="w-12 h-12 text-gray-400 mx-auto mb-4" />
                <h3 className="text-lg font-semibold text-gray-900 mb-2">No cluster data available</h3>
                <p className="text-gray-600">Please select a cluster to view the dashboard</p>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-4">
                    <Server className="w-8 h-8 text-blue-600" />
                    <div>
                        <h1 className="text-2xl font-bold text-gray-900">{clusterData.cluster.name}</h1>
                        <p className="text-sm text-gray-500">
                            {clusterData.cluster.provider} • {clusterData.cluster.region} • v{clusterData.cluster.version}
                        </p>
                    </div>
                    {getStatusBadge(clusterData.cluster.status)}
                </div>
                <button className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors">
                    <Settings className="w-4 h-4" />
                    Configure
                </button>
            </div>

            {/* Main Grid */}
            <div className="grid grid-cols-3 gap-6">
                {/* Left Column - Cluster Details */}
                <div className="col-span-1 space-y-6">
                    {/* Cluster Details Card */}
                    <div className="bg-white rounded-lg border border-gray-200 p-6">
                        <h2 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
                            <Server className="w-5 h-5 text-blue-600" />
                            Cluster Details
                        </h2>
                        <div className="space-y-3">
                            <div className="flex justify-between items-center py-2 border-b border-gray-100">
                                <span className="text-sm text-gray-600">Provider</span>
                                <span className="text-sm font-medium text-gray-900">{clusterData.cluster.provider}</span>
                            </div>
                            <div className="flex justify-between items-center py-2 border-b border-gray-100">
                                <span className="text-sm text-gray-600">Region</span>
                                <span className="text-sm font-medium text-gray-900">{clusterData.cluster.region}</span>
                            </div>
                            <div className="flex justify-between items-center py-2 border-b border-gray-100">
                                <span className="text-sm text-gray-600">Kubernetes Version</span>
                                <span className="text-sm font-medium text-gray-900">v{clusterData.cluster.version}</span>
                            </div>
                            <div className="flex justify-between items-center py-2 border-b border-gray-100">
                                <span className="text-sm text-gray-600">Status</span>
                                {getStatusBadge(clusterData.cluster.status)}
                            </div>
                            <div className="flex justify-between items-center py-2">
                                <span className="text-sm text-gray-600">Created</span>
                                <span className="text-sm font-medium text-gray-900">{clusterData.cluster.createdAt}</span>
                            </div>
                        </div>
                    </div>

                    {/* Autoscaler Policies Card */}
                    <div className="bg-white rounded-lg border border-gray-200 p-6">
                        <div className="flex items-center justify-between mb-4">
                            <h2 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
                                <Zap className="w-5 h-5 text-yellow-600" />
                                Autoscaler
                            </h2>
                            <span className="text-xs font-medium text-gray-600">
                                {clusterData.autoscaler.enabledPolicies} / {clusterData.autoscaler.totalPolicies} enabled
                            </span>
                        </div>
                        <div className="space-y-2">
                            {clusterData.autoscaler.policies.map((policy, index) => (
                                <div key={index} className="flex items-center justify-between py-2">
                                    <span className="text-sm text-gray-700">{policy.name}</span>
                                    <div className={`w-10 h-5 rounded-full transition-colors ${policy.enabled ? 'bg-green-500' : 'bg-gray-300'} relative`}>
                                        <div className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white transition-transform ${policy.enabled ? 'translate-x-5' : ''}`}></div>
                                    </div>
                                </div>
                            ))}
                        </div>
                        <button className="mt-4 w-full px-4 py-2 text-sm text-blue-600 hover:bg-blue-50 rounded-lg transition-colors flex items-center justify-center gap-2">
                            Manage Policies
                            <ChevronRight className="w-4 h-4" />
                        </button>
                    </div>

                    {/* Hibernation Schedules Card */}
                    <div className="bg-white rounded-lg border border-gray-200 p-6">
                        <div className="flex items-center justify-between mb-4">
                            <h2 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
                                <Moon className="w-5 h-5 text-purple-600" />
                                Hibernation
                            </h2>
                            <span className="text-xs font-medium text-gray-600">
                                {clusterData.hibernation.activeSchedules} / {clusterData.hibernation.totalSchedules} active
                            </span>
                        </div>
                        <div className="space-y-3">
                            {clusterData.hibernation.schedules.map((schedule, index) => (
                                <div key={index} className="p-3 bg-gray-50 rounded-lg">
                                    <div className="flex items-center justify-between mb-1">
                                        <span className="text-sm font-medium text-gray-900">{schedule.name}</span>
                                        <span className={`text-xs px-2 py-0.5 rounded ${schedule.enabled ? 'bg-green-100 text-green-700' : 'bg-gray-200 text-gray-600'}`}>
                                            {schedule.enabled ? 'Active' : 'Disabled'}
                                        </span>
                                    </div>
                                    {schedule.nextAction && (
                                        <div className="flex items-center gap-1 text-xs text-gray-600 mt-1">
                                            <Clock className="w-3 h-3" />
                                            Next: {schedule.nextAction}
                                        </div>
                                    )}
                                </div>
                            ))}
                        </div>
                        <button className="mt-4 w-full px-4 py-2 text-sm text-blue-600 hover:bg-blue-50 rounded-lg transition-colors flex items-center justify-center gap-2">
                            Manage Schedules
                            <ChevronRight className="w-4 h-4" />
                        </button>
                    </div>
                </div>

                {/* Right Column - Metrics */}
                <div className="col-span-2 space-y-6">
                    {/* Nodes Summary Card */}
                    <div className="bg-white rounded-lg border border-gray-200 p-6">
                        <h2 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
                            <Server className="w-5 h-5 text-blue-600" />
                            Nodes Summary
                        </h2>

                        <div className="grid grid-cols-2 gap-6">
                            {/* Node Breakdown */}
                            <div>
                                <div className="text-3xl font-bold text-gray-900 mb-2">{clusterData.nodes.total}</div>
                                <div className="text-sm text-gray-600 mb-4">Total Nodes</div>

                                <div className="space-y-2">
                                    <div className="flex items-center justify-between">
                                        <div className="flex items-center gap-2">
                                            <div className="w-3 h-3 rounded-full bg-green-500"></div>
                                            <span className="text-sm text-gray-700">Spot Instances</span>
                                        </div>
                                        <span className="text-sm font-medium text-gray-900">{clusterData.nodes.spot}</span>
                                    </div>
                                    <div className="flex items-center justify-between">
                                        <div className="flex items-center gap-2">
                                            <div className="w-3 h-3 rounded-full bg-blue-500"></div>
                                            <span className="text-sm text-gray-700">On-Demand</span>
                                        </div>
                                        <span className="text-sm font-medium text-gray-900">{clusterData.nodes.onDemand}</span>
                                    </div>
                                    <div className="flex items-center justify-between">
                                        <div className="flex items-center gap-2">
                                            <div className="w-3 h-3 rounded-full bg-orange-500"></div>
                                            <span className="text-sm text-gray-700">Fallback</span>
                                        </div>
                                        <span className="text-sm font-medium text-gray-900">{clusterData.nodes.fallback}</span>
                                    </div>
                                </div>
                            </div>

                            {/* Node Ownership */}
                            <div>
                                <div className="text-sm text-gray-600 mb-4">Node Ownership</div>

                                <div className="space-y-2">
                                    <div className="flex items-center justify-between">
                                        <div className="flex items-center gap-2">
                                            <Shield className="w-4 h-4 text-purple-600" />
                                            <span className="text-sm text-gray-700">Platform-managed</span>
                                        </div>
                                        <span className="text-sm font-medium text-gray-900">{clusterData.nodes.platformManaged}</span>
                                    </div>
                                    <div className="flex items-center justify-between">
                                        <div className="flex items-center gap-2">
                                            <Server className="w-4 h-4 text-gray-600" />
                                            <span className="text-sm text-gray-700">Cloud-managed</span>
                                        </div>
                                        <span className="text-sm font-medium text-gray-900">{clusterData.nodes.cloudManaged}</span>
                                    </div>
                                </div>

                                <div className="mt-4 pt-4 border-t border-gray-200">
                                    <div className="flex items-center justify-between text-sm">
                                        <span className="text-gray-600">Total Resources</span>
                                    </div>
                                    <div className="flex items-center gap-4 mt-2">
                                        <div className="flex items-center gap-1">
                                            <Cpu className="w-4 h-4 text-blue-600" />
                                            <span className="text-sm font-medium">{clusterData.nodes.totalCpu} vCPU</span>
                                        </div>
                                        <div className="flex items-center gap-1">
                                            <HardDrive className="w-4 h-4 text-purple-600" />
                                            <span className="text-sm font-medium">{clusterData.nodes.totalMemory} GB</span>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* Workloads Summary Card */}
                    <div className="bg-white rounded-lg border border-gray-200 p-6">
                        <h2 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
                            <Package className="w-5 h-5 text-green-600" />
                            Workloads Summary
                        </h2>

                        <div className="grid grid-cols-3 gap-6">
                            <div>
                                <div className="text-3xl font-bold text-gray-900 mb-1">{clusterData.workloads.totalPods}</div>
                                <div className="text-sm text-gray-600 mb-2">Total Pods</div>
                                <div className="flex items-center gap-2 text-xs">
                                    <span className="px-2 py-1 bg-green-100 text-green-700 rounded">
                                        {clusterData.workloads.scheduledPods} Scheduled
                                    </span>
                                    {clusterData.workloads.pendingPods > 0 && (
                                        <span className="px-2 py-1 bg-yellow-100 text-yellow-700 rounded">
                                            {clusterData.workloads.pendingPods} Pending
                                        </span>
                                    )}
                                </div>
                            </div>

                            <div>
                                <div className="text-2xl font-bold text-gray-900 mb-1">{clusterData.workloads.deployments}</div>
                                <div className="text-sm text-gray-600">Deployments</div>
                            </div>

                            <div className="space-y-2">
                                <div className="flex items-center justify-between text-sm">
                                    <span className="text-gray-600">StatefulSets</span>
                                    <span className="font-medium text-gray-900">{clusterData.workloads.statefulSets}</span>
                                </div>
                                <div className="flex items-center justify-between text-sm">
                                    <span className="text-gray-600">DaemonSets</span>
                                    <span className="font-medium text-gray-900">{clusterData.workloads.daemonSets}</span>
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* Resource Utilization Card */}
                    <div className="bg-white rounded-lg border border-gray-200 p-6">
                        <h2 className="text-lg font-semibold text-gray-900 mb-6 flex items-center gap-2">
                            <Activity className="w-5 h-5 text-blue-600" />
                            Resource Utilization
                        </h2>

                        <div className="grid grid-cols-3 gap-8">
                            {renderDonutChart(clusterData.resources.cpu.utilization, 'CPU', 'blue')}
                            {renderDonutChart(clusterData.resources.memory.utilization, 'Memory', 'green')}
                            {renderDonutChart(clusterData.resources.storage.utilization, 'Storage', 'purple')}
                        </div>

                        <div className="grid grid-cols-3 gap-6 mt-6 pt-6 border-t border-gray-200">
                            <div className="text-center">
                                <div className="text-xs text-gray-600 mb-1">CPU Usage</div>
                                <div className="text-sm font-medium text-gray-900">
                                    {clusterData.resources.cpu.used} / {clusterData.resources.cpu.total} cores
                                </div>
                            </div>
                            <div className="text-center">
                                <div className="text-xs text-gray-600 mb-1">Memory Usage</div>
                                <div className="text-sm font-medium text-gray-900">
                                    {clusterData.resources.memory.used} / {clusterData.resources.memory.total} GB
                                </div>
                            </div>
                            <div className="text-center">
                                <div className="text-xs text-gray-600 mb-1">Storage Usage</div>
                                <div className="text-sm font-medium text-gray-900">
                                    {clusterData.resources.storage.used} / {clusterData.resources.storage.total} GB
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default ClusterDashboard;
