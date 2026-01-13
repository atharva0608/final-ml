import React, { useState, useEffect } from 'react';
import { cleanupAPI, accountsAPI } from '../../services/api';
import StatsCard from '../shared/StatsCard';
import Badge from '../shared/Badge';
import Button from '../shared/Button';
import { FiDollarSign, FiAlertOctagon, FiHardDrive, FiGlobe, FiCheckCircle, FiAlertTriangle, FiTag, FiX, FiAlertCircle } from 'react-icons/fi';
import toast from 'react-hot-toast';

const CleanupDashboard = () => {
    const [loading, setLoading] = useState(false);
    const [accounts, setAccounts] = useState([]);
    const [selectedAccount, setSelectedAccount] = useState('');
    const [scanResult, setScanResult] = useState(null);
    const [activeTab, setActiveTab] = useState('INSTANCE');
    const [selectedItems, setSelectedItems] = useState([]);
    const [actionLoading, setActionLoading] = useState(false);
    const [selectedRegion, setSelectedRegion] = useState('ALL');

    // Feature 1: Dependency Check Modal State
    const [showDependencyModal, setShowDependencyModal] = useState(false);
    const [blockingResources, setBlockingResources] = useState([]);
    const [pendingAction, setPendingAction] = useState(null);
    const [checkingDependencies, setCheckingDependencies] = useState(false);

    // Hardcoded regions list for now (or fetch from backend if available)
    const regionsList = [
        { id: 'ALL', name: 'Global Scan (All Regions)' },
        { id: 'us-east-1', name: 'US East (N. Virginia)' },
        { id: 'us-east-2', name: 'US East (Ohio)' },
        { id: 'us-west-1', name: 'US West (N. California)' },
        { id: 'us-west-2', name: 'US West (Oregon)' },
        { id: 'eu-west-1', name: 'Europe (Ireland)' },
        { id: 'eu-central-1', name: 'Europe (Frankfurt)' },
        { id: 'ap-south-1', name: 'Asia Pacific (Mumbai)' },
        { id: 'ap-northeast-1', name: 'Asia Pacific (Tokyo)' },
        { id: 'ap-southeast-1', name: 'Asia Pacific (Singapore)' },
        { id: 'ap-southeast-2', name: 'Asia Pacific (Sydney)' },
        { id: 'sa-east-1', name: 'South America (São Paulo)' },
    ];

    useEffect(() => {
        fetchAccounts();
    }, []);

    const fetchAccounts = async () => {
        try {
            const res = await accountsAPI.list();
            setAccounts(res.data);
            if (res.data.length > 0) {
                setSelectedAccount(res.data[0].id);
            }
        } catch (err) {
            console.error("Failed to load accounts", err);
        }
    };

    const handleScan = async () => {
        if (!selectedAccount) return;
        setLoading(true);
        try {
            const regionsToScan = selectedRegion === 'ALL' ? ['ALL'] : [selectedRegion];
            const res = await cleanupAPI.scan(selectedAccount, { regions: regionsToScan });
            setScanResult(res.data);
            setSelectedItems([]);
        } catch (err) {
            console.error("Scan failed", err);
            setScanResult({
                total_potential_savings: 0,
                unauthorized_instance_count: 0,
                orphaned_volume_count: 0,
                orphaned_snapshot_count: 0,
                unused_ip_count: 0,
                resources: []
            });
        } finally {
            setLoading(false);
        }
    };

    // Feature 1: Pre-flight Dependency Check before deletion
    const handleCleanupClick = async (actionType) => {
        if (!selectedAccount || selectedItems.length === 0) return;

        // Only check dependencies for destructive actions on snapshots, volumes, security groups
        const needsCheck = ['DELETE', 'TERMINATE'].includes(actionType) &&
            ['SNAPSHOT', 'VOLUME'].includes(activeTab);

        if (!needsCheck) {
            // Safe action, execute directly
            executeCleanupAction(actionType);
            return;
        }

        setCheckingDependencies(true);
        const allBlockers = [];

        try {
            // Check each selected item for dependencies
            for (const resourceId of selectedItems) {
                const resource = scanResult.resources.find(r => r.id === resourceId);
                if (!resource) continue;

                const res = await cleanupAPI.checkDependencies(
                    selectedAccount,
                    resource.type,
                    resourceId,
                    resource.region
                );

                if (!res.data.can_delete && res.data.blocking_resources?.length > 0) {
                    allBlockers.push({
                        resource_id: resourceId,
                        blockers: res.data.blocking_resources
                    });
                }
            }

            if (allBlockers.length > 0) {
                // Show warning modal with blocking resources
                setBlockingResources(allBlockers);
                setPendingAction(actionType);
                setShowDependencyModal(true);
            } else {
                // All clear, execute
                executeCleanupAction(actionType);
            }
        } catch (err) {
            console.error("Dependency check failed", err);
            toast.error("Failed to check dependencies. Proceeding with caution...");
            // Fallback: proceed anyway (user can cancel)
            executeCleanupAction(actionType);
        } finally {
            setCheckingDependencies(false);
        }
    };

    // Actual execution logic (called after dependency check passes or is bypassed)
    const executeCleanupAction = async (actionType) => {
        setActionLoading(true);
        try {
            const itemsByRegion = {};
            selectedItems.forEach(id => {
                const item = scanResult.resources.find(r => r.id === id);
                if (item) {
                    if (!itemsByRegion[item.region]) itemsByRegion[item.region] = [];
                    itemsByRegion[item.region].push(id);
                }
            });

            let pendingRequests = 0;
            for (const region of Object.keys(itemsByRegion)) {
                const response = await cleanupAPI.execute({
                    resource_ids: itemsByRegion[region],
                    action_type: actionType,
                    region: region
                }, selectedAccount);

                if (response.status === 202) {
                    pendingRequests++;
                }
            }

            if (pendingRequests > 0) {
                toast.success(`Request Sent: ${pendingRequests} batch(es) pending approval.`);
            } else {
                toast.success('Cleaned up resources successfully');
            }

            handleScan();
        } catch (err) {
            console.error("Action failed", err);
            toast.error("Failed to execute cleanup action: " + err.message);
        } finally {
            setActionLoading(false);
            setSelectedItems([]);
            setShowDependencyModal(false);
            setPendingAction(null);
        }
    };

    const toggleSelection = (id) => {
        setSelectedItems(prev =>
            prev.includes(id) ? prev.filter(i => i !== id) : [...prev, id]
        );
    };

    const filteredResources = scanResult?.resources.filter(r => r.type === activeTab) || [];

    // Safety Score helper - determines cleanup confidence level
    const getSafetyLevel = (resource) => {
        // HIGH: Explicitly safe items
        if (resource.status === 'SAFE_TO_DELETE') return 'HIGH';

        // HIGH: Orphaned volumes/snapshots are usually safe to delete (Fallback if status is just ORPHANED)
        if (resource.type === 'VOLUME' && resource.status === 'ORPHANED') return 'HIGH';
        if (resource.type === 'SNAPSHOT' && resource.status === 'ORPHANED') return 'HIGH';
        if (resource.type === 'ELASTIC_IP' && resource.status === 'ORPHANED') return 'HIGH';

        // MEDIUM: Unauthorized instances might be dev boxes or manual deployments
        if (resource.type === 'INSTANCE' && resource.status === 'UNAUTHORIZED') return 'MEDIUM';

        return 'LOW';
    };

    // Calculate defaults if no scan result
    const stats = scanResult || {
        total_potential_savings: 0,
        unauthorized_instance_count: 0,
        orphaned_volume_count: 0,
        unused_ip_count: 0
    };

    // Calculate savings for selected items
    const selectedSavings = scanResult?.resources
        .filter(r => selectedItems.includes(r.id))
        .reduce((sum, r) => sum + r.cost_per_month, 0) || 0;

    return (
        <div className="p-6 space-y-6 bg-gray-50 min-h-screen">
            {/* Header */}
            <div className="bg-white p-4 rounded-lg shadow-sm border border-gray-200 flex flex-col md:flex-row justify-between items-center gap-4">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900">Resource Hygiene</h1>
                    <p className="text-sm text-gray-500">Scan and eliminate waste across your AWS infrastructure</p>
                </div>
                <div className="flex flex-wrap gap-3 items-center">
                    <select
                        className="border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-indigo-500 focus:border-indigo-500 bg-white"
                        value={selectedAccount}
                        onChange={(e) => setSelectedAccount(e.target.value)}
                    >
                        {accounts.map(acc => (
                            <option key={acc.id} value={acc.id}>{acc.name || acc.aws_account_id}</option>
                        ))}
                    </select>
                    <select
                        className="border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-indigo-500 focus:border-indigo-500 bg-white"
                        value={selectedRegion}
                        onChange={(e) => setSelectedRegion(e.target.value)}
                    >
                        {regionsList.map(r => (
                            <option key={r.id} value={r.id}>{r.name}</option>
                        ))}
                    </select>
                    <Button onClick={handleScan} disabled={loading || !selectedAccount} className="w-full md:w-auto">
                        {loading ? (
                            <span className="flex items-center gap-2">
                                <svg className="animate-spin h-4 w-4 text-white" fill="none" viewBox="0 0 24 24">
                                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                                </svg>
                                Scanning...
                            </span>
                        ) : 'Start Scan'}
                    </Button>
                </div>
            </div>

            {/* Persistent Stats Cards */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-6 gap-4">
                <StatsCard
                    title="Potential Monthly Savings"
                    value={`$${stats.total_potential_savings.toFixed(2)}`}
                    color="green"
                    icon={FiDollarSign}
                />
                <StatsCard
                    title="Selected Savings"
                    value={`$${selectedSavings.toFixed(2)}`}
                    color="indigo"
                    icon={FiCheckCircle}
                />
                {/* Feature 2: Untagged Waste "Shameback" Card */}
                <StatsCard
                    title="Untagged Waste"
                    value={`$${(stats.untagged_waste_cost || 0).toFixed(2)}`}
                    color="red"
                    icon={FiTag}
                />
                <StatsCard
                    title="Unauthorized Instances"
                    value={stats.unauthorized_instance_count}
                    color="red"
                    icon={FiAlertOctagon}
                />
                <StatsCard
                    title="Orphaned Volumes"
                    value={stats.orphaned_volume_count}
                    color="yellow"
                    icon={FiHardDrive}
                />
                <StatsCard
                    title="Unused IPs"
                    value={stats.unused_ip_count}
                    color="blue"
                    icon={FiGlobe}
                />
            </div>

            {/* Main Content Area */}
            <div className="bg-white shadow-sm rounded-lg border border-gray-200 overflow-hidden min-h-[400px]">
                {/* Tabs */}
                <div className="border-b border-gray-200 bg-gray-50 flex px-4">
                    {['INSTANCE', 'VOLUME', 'SNAPSHOT', 'ELASTIC_IP'].map(type => (
                        <button
                            key={type}
                            className={`px-6 py-4 text-sm font-medium transition-colors border-b-2 ${activeTab === type
                                ? 'border-indigo-600 text-indigo-600 bg-white'
                                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                                }`}
                            onClick={() => setActiveTab(type)}
                        >
                            {type.replace('_', ' ')}s
                            {scanResult && <span className="ml-2 bg-gray-100 text-gray-600 py-0.5 px-2 rounded-full text-xs">
                                {scanResult.resources.filter(r => r.type === type).length}
                            </span>}
                        </button>
                    ))}
                </div>

                {/* Toolbar */}
                <div className="p-4 border-b border-gray-200 flex justify-between items-center bg-white">
                    <div className="text-sm text-gray-600 font-medium">
                        {loading ? 'Scanning resources...' : `${filteredResources.length} resources found`}
                        {selectedItems.length > 0 && <span className="ml-2 text-indigo-600">({selectedItems.length} selected)</span>}
                    </div>
                    <div className="space-x-2">
                        <Button
                            variant="danger"
                            size="sm"
                            disabled={selectedItems.length === 0 || actionLoading || checkingDependencies}
                            onClick={() => handleCleanupClick(activeTab === 'INSTANCE' ? 'TERMINATE' : activeTab === 'ELASTIC_IP' ? 'RELEASE' : 'DELETE')}
                        >
                            {checkingDependencies ? 'Checking...' : actionLoading ? 'Cleanup...' : 'Cleanup Selected'}
                        </Button>
                    </div>
                </div>

                {/* Content */}
                {loading ? (
                    <div className="flex flex-col items-center justify-center h-64">
                        <svg className="animate-spin h-8 w-8 text-indigo-600 mb-4" fill="none" viewBox="0 0 24 24">
                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                        </svg>
                        <p className="text-gray-500">Scanning {selectedRegion}...</p>
                    </div>
                ) : !scanResult ? (
                    <div className="flex flex-col items-center justify-center h-64 text-center">
                        <div className="bg-gray-100 p-4 rounded-full mb-4">
                            <svg className="h-8 w-8 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                            </svg>
                        </div>
                        <h3 className="text-lg font-medium text-gray-900">Ready to Scan</h3>
                        <p className="text-gray-500 max-w-sm mt-1">Select an account and region above, then click "Start Scan" to identify cleanup opportunities.</p>
                    </div>
                ) : filteredResources.length === 0 ? (
                    <div className="flex flex-col items-center justify-center h-64 text-center">
                        <div className="bg-green-50 p-4 rounded-full mb-4">
                            <svg className="h-8 w-8 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                            </svg>
                        </div>
                        <h3 className="text-lg font-medium text-gray-900">All Clean!</h3>
                        <p className="text-gray-500">No orphaned {activeTab.toLowerCase().replace('_', ' ')}s found in this region.</p>
                    </div>
                ) : (
                    <div className="overflow-x-auto">
                        <table className="min-w-full divide-y divide-gray-200">
                            <thead className="bg-gray-50">
                                <tr>
                                    <th className="px-6 py-3 text-left w-12">
                                        <input
                                            type="checkbox"
                                            className="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                                            onChange={(e) => {
                                                if (e.target.checked) setSelectedItems(filteredResources.map(r => r.id));
                                                else setSelectedItems([]);
                                            }}
                                            checked={filteredResources.length > 0 && selectedItems.length === filteredResources.length}
                                        />
                                    </th>
                                    <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">Resource ID</th>
                                    <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">Name</th>
                                    <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">Region</th>
                                    <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">Status</th>
                                    <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">Compliance</th>
                                    <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">Safety</th>
                                    <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">Cost/Mo</th>
                                </tr>
                            </thead>
                            <tbody className="bg-white divide-y divide-gray-200">
                                {filteredResources.map(resource => (
                                    <tr key={resource.id} className={`hover:bg-gray-50 transition-colors ${selectedItems.includes(resource.id) ? 'bg-blue-50' : ''}`}>
                                        <td className="px-6 py-4 whitespace-nowrap">
                                            <div className="relative group">
                                                <input
                                                    type="checkbox"
                                                    disabled={resource.status === 'PENDING_APPROVAL'}
                                                    className="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500 disabled:opacity-50"
                                                    checked={selectedItems.includes(resource.id)}
                                                    onChange={() => toggleSelection(resource.id)}
                                                />
                                                {resource.status === 'PENDING_APPROVAL' && (
                                                    <div className="absolute left-6 top-0 w-32 bg-black text-white text-xs rounded py-1 px-2 opacity-0 group-hover:opacity-100 transition-opacity z-10 pointer-events-none">
                                                        Pending Approval
                                                    </div>
                                                )}
                                            </div>
                                        </td>
                                        <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900 font-mono">{resource.id}</td>
                                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{resource.name}</td>
                                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                                            <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-800">
                                                {resource.region}
                                            </span>
                                        </td>
                                        <td className="px-6 py-4 whitespace-nowrap">
                                            <Badge type={resource.status === 'SAFE_TO_DELETE' ? 'success' : (resource.status === 'ORPHANED' || resource.status === 'UNAUTHORIZED' ? 'warning' : 'neutral')}>
                                                {resource.status.replace(/_/g, ' ')}
                                            </Badge>
                                        </td>
                                        {/* Feature 2: Compliance Column with Tooltip */}
                                        <td className="px-6 py-4 whitespace-nowrap">
                                            {resource.is_compliant !== false ? (
                                                <span className="bg-green-100 text-green-800 text-xs font-bold px-2 py-1 rounded-full flex items-center w-fit">
                                                    <FiCheckCircle className="mr-1" /> Compliant
                                                </span>
                                            ) : (
                                                <div className="relative group">
                                                    <span className="bg-red-100 text-red-800 text-xs font-bold px-2 py-1 rounded-full flex items-center w-fit cursor-help">
                                                        <FiTag className="mr-1" /> Untagged
                                                    </span>
                                                    {resource.missing_tags?.length > 0 && (
                                                        <div className="absolute left-0 top-full mt-1 w-48 bg-gray-900 text-white text-xs rounded py-2 px-3 opacity-0 group-hover:opacity-100 transition-opacity z-20 pointer-events-none shadow-lg">
                                                            <div className="font-bold mb-1">Missing Tags:</div>
                                                            {resource.missing_tags.map((tag, i) => (
                                                                <div key={i} className="text-gray-300">• {tag}</div>
                                                            ))}
                                                        </div>
                                                    )}
                                                </div>
                                            )}
                                        </td>
                                        <td className="px-6 py-4 whitespace-nowrap">
                                            {getSafetyLevel(resource) === 'HIGH' && (
                                                <span className="bg-green-100 text-green-800 text-xs font-bold px-2 py-1 rounded-full flex items-center w-fit">
                                                    <FiCheckCircle className="mr-1" /> Safe to Delete
                                                </span>
                                            )}
                                            {getSafetyLevel(resource) === 'MEDIUM' && (
                                                <span className="bg-yellow-100 text-yellow-800 text-xs font-bold px-2 py-1 rounded-full flex items-center w-fit">
                                                    <FiAlertTriangle className="mr-1" /> Review Needed
                                                </span>
                                            )}
                                            {getSafetyLevel(resource) === 'LOW' && (
                                                <span className="bg-red-100 text-red-800 text-xs font-bold px-2 py-1 rounded-full flex items-center w-fit">
                                                    <FiAlertOctagon className="mr-1" /> Risky
                                                </span>
                                            )}
                                        </td>
                                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 font-medium">${resource.cost_per_month.toFixed(2)}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>

            {/* Feature 1: Dependency Warning Modal */}
            {showDependencyModal && (
                <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
                    <div className="bg-white rounded-lg shadow-xl max-w-lg w-full mx-4 overflow-hidden">
                        <div className="bg-red-50 p-4 border-b border-red-100 flex items-center gap-3">
                            <div className="bg-red-100 p-2 rounded-full">
                                <FiAlertCircle className="text-red-600 w-6 h-6" />
                            </div>
                            <div>
                                <h3 className="text-lg font-bold text-red-900">Cannot Delete Resources</h3>
                                <p className="text-sm text-red-700">Some resources have blocking dependencies</p>
                            </div>
                        </div>
                        <div className="p-4 max-h-64 overflow-y-auto">
                            {blockingResources.map((item, idx) => (
                                <div key={idx} className="mb-4 last:mb-0">
                                    <div className="font-mono text-sm text-gray-900 mb-1">{item.resource_id}</div>
                                    <div className="pl-4 space-y-1">
                                        {item.blockers.map((blocker, i) => (
                                            <div key={i} className="text-sm text-red-600 flex items-center gap-2">
                                                <FiX className="flex-shrink-0" />
                                                <span>Used by {blocker.type}: <span className="font-mono">{blocker.id}</span></span>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            ))}
                        </div>
                        <div className="p-4 bg-gray-50 border-t flex justify-end gap-3">
                            <Button
                                variant="secondary"
                                onClick={() => {
                                    setShowDependencyModal(false);
                                    setBlockingResources([]);
                                    setPendingAction(null);
                                }}
                            >
                                Cancel
                            </Button>
                            <Button
                                variant="danger"
                                onClick={() => {
                                    // Remove blocked items from selection and proceed
                                    const blockedIds = blockingResources.map(b => b.resource_id);
                                    const safeItems = selectedItems.filter(id => !blockedIds.includes(id));
                                    if (safeItems.length > 0) {
                                        setSelectedItems(safeItems);
                                        executeCleanupAction(pendingAction);
                                    } else {
                                        toast.error('All selected items have blocking dependencies');
                                        setShowDependencyModal(false);
                                    }
                                }}
                            >
                                Skip Blocked & Continue
                            </Button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default CleanupDashboard;
