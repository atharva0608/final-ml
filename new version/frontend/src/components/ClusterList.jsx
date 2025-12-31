import React, { useState, useEffect } from 'react';
import {
    Server,
    TrendingUp,
    Cpu,
    HardDrive,
    DollarSign,
    AlertCircle,
    CheckCircle,
    XCircle,
    Clock,
    Shield,
    Trash2,
    Settings
} from 'lucide-react';

const ClusterList = () => {
    const [clusters, setClusters] = useState([]);
    const [loading, setLoading] = useState(true);
    const [disconnectModal, setDisconnectModal] = useState(null);
    const [confirmationInput, setConfirmationInput] = useState('');
    const [deleteNodes, setDeleteNodes] = useState(false);

    // Cluster state configuration
    const clusterStates = {
        PENDING: {
            color: 'bg-gray-100 text-gray-700 border-gray-300',
            icon: Clock,
            label: 'Pending'
        },
        CONNECTING: {
            color: 'bg-blue-100 text-blue-700 border-blue-300',
            icon: Clock,
            label: 'Connecting'
        },
        CONNECTED: {
            color: 'bg-green-100 text-green-700 border-green-300',
            icon: CheckCircle,
            label: 'Connected'
        },
        READ_ONLY: {
            color: 'bg-yellow-100 text-yellow-700 border-yellow-300',
            icon: Shield,
            label: 'Read-only'
        },
        PARTIALLY_CONNECTED: {
            color: 'bg-orange-100 text-orange-700 border-orange-300',
            icon: AlertCircle,
            label: 'Partial'
        },
        DISCONNECTED: {
            color: 'bg-gray-100 text-gray-600 border-gray-300',
            icon: XCircle,
            label: 'Disconnected'
        },
        ERROR: {
            color: 'bg-red-100 text-red-700 border-red-300',
            icon: XCircle,
            label: 'Error'
        },
        REMOVING: {
            color: 'bg-purple-100 text-purple-700 border-purple-300',
            icon: Trash2,
            label: 'Removing'
        },
        REMOVED: {
            color: 'bg-gray-50 text-gray-500 border-gray-200',
            icon: Trash2,
            label: 'Removed'
        }
    };

    // Mock data for demonstration
    const mockClusters = [
        {
            id: '1',
            name: 'production-cluster',
            status: 'CONNECTED',
            provider: 'AWS EKS',
            region: 'us-east-1',
            nodes: {
                total: 12,
                spot: 8,
                onDemand: 3,
                fallback: 1
            },
            monthlyCost: 2847.50,
            version: '1.28'
        },
        {
            id: '2',
            name: 'staging-cluster',
            status: 'CONNECTED',
            provider: 'GCP GKE',
            region: 'us-central1',
            nodes: {
                total: 6,
                spot: 4,
                onDemand: 2,
                fallback: 0
            },
            monthlyCost: 1245.00,
            version: '1.27'
        },
        {
            id: '3',
            name: 'dev-cluster',
            status: 'READ_ONLY',
            provider: 'Azure AKS',
            region: 'eastus',
            nodes: {
                total: 4,
                spot: 2,
                onDemand: 2,
                fallback: 0
            },
            monthlyCost: 678.25,
            version: '1.27'
        },
        {
            id: '4',
            name: 'ml-workloads',
            status: 'PARTIALLY_CONNECTED',
            provider: 'AWS EKS',
            region: 'us-west-2',
            nodes: {
                total: 8,
                spot: 5,
                onDemand: 3,
                fallback: 0
            },
            monthlyCost: 3456.75,
            version: '1.28'
        },
        {
            id: '5',
            name: 'test-cluster',
            status: 'CONNECTING',
            provider: 'GCP GKE',
            region: 'europe-west1',
            nodes: {
                total: 3,
                spot: 2,
                onDemand: 1,
                fallback: 0
            },
            monthlyCost: 421.50,
            version: '1.28'
        }
    ];

    useEffect(() => {
        // Simulate API call
        setTimeout(() => {
            setClusters(mockClusters);
            setLoading(false);
        }, 500);
    }, []);

    // Calculate summary metrics
    const summary = clusters.reduce((acc, cluster) => ({
        totalCost: acc.totalCost + cluster.monthlyCost,
        totalNodes: acc.totalNodes + cluster.nodes.total,
        spotNodes: acc.spotNodes + cluster.nodes.spot,
        onDemandNodes: acc.onDemandNodes + cluster.nodes.onDemand,
        fallbackNodes: acc.fallbackNodes + cluster.nodes.fallback,
        totalCpu: acc.totalCpu + (cluster.nodes.total * 4), // Assuming 4 vCPU per node
        totalMemory: acc.totalMemory + (cluster.nodes.total * 16) // Assuming 16GB per node
    }), {
        totalCost: 0,
        totalNodes: 0,
        spotNodes: 0,
        onDemandNodes: 0,
        fallbackNodes: 0,
        totalCpu: 0,
        totalMemory: 0
    });

    const handleDisconnect = (cluster) => {
        setDisconnectModal(cluster);
        setConfirmationInput('');
        setDeleteNodes(false);
    };

    const confirmDisconnect = () => {
        if (confirmationInput === disconnectModal.name) {
            console.log('Disconnecting cluster:', disconnectModal.name, 'Delete nodes:', deleteNodes);
            // TODO: API call to disconnect cluster
            setClusters(clusters.filter(c => c.id !== disconnectModal.id));
            setDisconnectModal(null);
            setConfirmationInput('');
            setDeleteNodes(false);
        }
    };

    const cancelDisconnect = () => {
        setDisconnectModal(null);
        setConfirmationInput('');
        setDeleteNodes(false);
    };

    const renderStatusBadge = (status) => {
        const state = clusterStates[status];
        const Icon = state.icon;

        return (
            <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium border ${state.color}`}>
                <Icon className="w-3.5 h-3.5" />
                {state.label}
            </span>
        );
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center h-64">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            {/* Summary Overview Panel */}
            <div className="bg-white rounded-lg border border-gray-200 p-6">
                <h2 className="text-lg font-semibold text-gray-900 mb-4">Clusters Overview</h2>

                <div className="grid grid-cols-4 gap-6">
                    {/* Total Compute Cost */}
                    <div className="space-y-2">
                        <div className="flex items-center gap-2 text-sm text-gray-600">
                            <DollarSign className="w-4 h-4" />
                            <span>Total Compute Cost</span>
                        </div>
                        <div className="text-2xl font-bold text-gray-900">
                            ${summary.totalCost.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                        </div>
                        <div className="text-xs text-gray-500">per month</div>
                    </div>

                    {/* Total Nodes */}
                    <div className="space-y-2">
                        <div className="flex items-center gap-2 text-sm text-gray-600">
                            <Server className="w-4 h-4" />
                            <span>Total Nodes</span>
                        </div>
                        <div className="text-2xl font-bold text-gray-900">{summary.totalNodes}</div>
                        <div className="flex items-center gap-2 text-xs">
                            <span className="px-2 py-0.5 bg-green-100 text-green-700 rounded">
                                {summary.spotNodes} Spot
                            </span>
                            <span className="px-2 py-0.5 bg-blue-100 text-blue-700 rounded">
                                {summary.onDemandNodes} On-Demand
                            </span>
                            {summary.fallbackNodes > 0 && (
                                <span className="px-2 py-0.5 bg-orange-100 text-orange-700 rounded">
                                    {summary.fallbackNodes} Fallback
                                </span>
                            )}
                        </div>
                    </div>

                    {/* Total CPU */}
                    <div className="space-y-2">
                        <div className="flex items-center gap-2 text-sm text-gray-600">
                            <Cpu className="w-4 h-4" />
                            <span>Total CPU</span>
                        </div>
                        <div className="text-2xl font-bold text-gray-900">{summary.totalCpu}</div>
                        <div className="text-xs text-gray-500">vCPU cores</div>
                    </div>

                    {/* Total Memory */}
                    <div className="space-y-2">
                        <div className="flex items-center gap-2 text-sm text-gray-600">
                            <HardDrive className="w-4 h-4" />
                            <span>Total Memory</span>
                        </div>
                        <div className="text-2xl font-bold text-gray-900">{summary.totalMemory} GB</div>
                        <div className="text-xs text-gray-500">RAM</div>
                    </div>
                </div>
            </div>

            {/* Clusters Table */}
            <div className="bg-white rounded-lg border border-gray-200">
                <div className="px-6 py-4 border-b border-gray-200">
                    <div className="flex items-center justify-between">
                        <h2 className="text-lg font-semibold text-gray-900">
                            Clusters ({clusters.length})
                        </h2>
                        <button className="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 transition-colors">
                            Connect Cluster
                        </button>
                    </div>
                </div>

                <div className="overflow-x-auto">
                    <table className="w-full">
                        <thead className="bg-gray-50 border-b border-gray-200">
                            <tr>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                    Cluster Name
                                </th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                    Status
                                </th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                    Provider
                                </th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                    Region
                                </th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                    Nodes
                                </th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                    Monthly Cost
                                </th>
                                <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                                    Actions
                                </th>
                            </tr>
                        </thead>
                        <tbody className="bg-white divide-y divide-gray-200">
                            {clusters.map((cluster) => (
                                <tr key={cluster.id} className="hover:bg-gray-50 transition-colors">
                                    <td className="px-6 py-4 whitespace-nowrap">
                                        <div className="flex items-center gap-2">
                                            <Server className="w-4 h-4 text-gray-400" />
                                            <div>
                                                <div className="text-sm font-medium text-gray-900">
                                                    {cluster.name}
                                                </div>
                                                <div className="text-xs text-gray-500">
                                                    v{cluster.version}
                                                </div>
                                            </div>
                                        </div>
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap">
                                        {renderStatusBadge(cluster.status)}
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                                        {cluster.provider}
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                                        {cluster.region}
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap">
                                        <div className="text-sm text-gray-900">{cluster.nodes.total}</div>
                                        <div className="flex items-center gap-1 text-xs text-gray-500">
                                            <span>{cluster.nodes.spot}S</span>
                                            <span>/</span>
                                            <span>{cluster.nodes.onDemand}OD</span>
                                            {cluster.nodes.fallback > 0 && (
                                                <>
                                                    <span>/</span>
                                                    <span>{cluster.nodes.fallback}FB</span>
                                                </>
                                            )}
                                        </div>
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                                        ${cluster.monthlyCost.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-right text-sm">
                                        <div className="flex items-center justify-end gap-2">
                                            {cluster.status === 'CONNECTED' && (
                                                <button className="px-3 py-1.5 text-blue-600 hover:bg-blue-50 rounded-md transition-colors flex items-center gap-1">
                                                    <Settings className="w-3.5 h-3.5" />
                                                    Adjust costs
                                                </button>
                                            )}
                                            {(cluster.status === 'CONNECTED' || cluster.status === 'READ_ONLY' || cluster.status === 'PARTIALLY_CONNECTED') && (
                                                <button
                                                    onClick={() => handleDisconnect(cluster)}
                                                    className="px-3 py-1.5 text-red-600 hover:bg-red-50 rounded-md transition-colors flex items-center gap-1"
                                                >
                                                    <XCircle className="w-3.5 h-3.5" />
                                                    Disconnect
                                                </button>
                                            )}
                                        </div>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>

                {clusters.length === 0 && (
                    <div className="text-center py-12">
                        <Server className="w-12 h-12 text-gray-400 mx-auto mb-4" />
                        <h3 className="text-sm font-medium text-gray-900 mb-1">No clusters connected</h3>
                        <p className="text-sm text-gray-500 mb-4">Get started by connecting your first Kubernetes cluster</p>
                        <button className="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 transition-colors">
                            Connect Cluster
                        </button>
                    </div>
                )}
            </div>

            {/* Disconnect Modal */}
            {disconnectModal && (
                <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
                    <div className="bg-white rounded-lg shadow-xl max-w-md w-full mx-4">
                        <div className="px-6 py-4 border-b border-gray-200">
                            <h3 className="text-lg font-semibold text-gray-900">
                                Disconnect Cluster
                            </h3>
                        </div>

                        <div className="px-6 py-4 space-y-4">
                            <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
                                <div className="flex gap-3">
                                    <AlertCircle className="w-5 h-5 text-yellow-600 flex-shrink-0 mt-0.5" />
                                    <div className="text-sm text-yellow-800">
                                        <p className="font-medium mb-1">Warning: This action cannot be undone</p>
                                        <p>Disconnecting will stop all optimization and cost-saving features for this cluster.</p>
                                    </div>
                                </div>
                            </div>

                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-2">
                                    Type cluster name to confirm: <span className="font-mono text-gray-900">{disconnectModal.name}</span>
                                </label>
                                <input
                                    type="text"
                                    value={confirmationInput}
                                    onChange={(e) => setConfirmationInput(e.target.value)}
                                    placeholder={disconnectModal.name}
                                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                                />
                            </div>

                            <div className="bg-red-50 border border-red-200 rounded-lg p-4">
                                <label className="flex items-start gap-3 cursor-pointer">
                                    <input
                                        type="checkbox"
                                        checked={deleteNodes}
                                        onChange={(e) => setDeleteNodes(e.target.checked)}
                                        className="mt-1 w-4 h-4 text-red-600 border-gray-300 rounded focus:ring-red-500"
                                    />
                                    <div className="text-sm">
                                        <div className="font-medium text-red-900 mb-1">
                                            Delete all platform-created nodes
                                        </div>
                                        <div className="text-red-700">
                                            This will terminate all nodes created by the platform. Your workloads may be disrupted.
                                        </div>
                                    </div>
                                </label>
                            </div>
                        </div>

                        <div className="px-6 py-4 bg-gray-50 rounded-b-lg flex items-center justify-end gap-3">
                            <button
                                onClick={cancelDisconnect}
                                className="px-4 py-2 text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
                            >
                                Cancel
                            </button>
                            <button
                                onClick={confirmDisconnect}
                                disabled={confirmationInput !== disconnectModal.name}
                                className={`px-4 py-2 rounded-lg transition-colors ${
                                    confirmationInput === disconnectModal.name
                                        ? 'bg-red-600 text-white hover:bg-red-700'
                                        : 'bg-gray-300 text-gray-500 cursor-not-allowed'
                                }`}
                            >
                                Disconnect Cluster
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default ClusterList;
