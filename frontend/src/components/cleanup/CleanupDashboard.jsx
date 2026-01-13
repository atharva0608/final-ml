import React, { useState, useEffect } from 'react';
import { cleanupAPI, accountsAPI } from '../../services/api';
import Badge from '../shared/Badge';
import Button from '../shared/Button';
import GaugeChart from '../shared/GaugeChart';
import { FiDollarSign, FiAlertOctagon, FiHardDrive, FiGlobe, FiCheckCircle, FiAlertTriangle, FiTag, FiX, FiAlertCircle, FiServer, FiCamera, FiRefreshCw, FiShield, FiShare2, FiDatabase, FiUsers, FiFolder, FiLink } from 'react-icons/fi';
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
    const [showAuthorized, setShowAuthorized] = useState(false);

    // Feature 1: Dependency Check Modal State
    const [showDependencyModal, setShowDependencyModal] = useState(false);
    const [blockingResources, setBlockingResources] = useState([]);
    const [pendingAction, setPendingAction] = useState(null);
    const [checkingDependencies, setCheckingDependencies] = useState(false);

    const regionsList = [
        { id: 'ALL', name: 'All Regions (Global)' },
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

    // [NEW] Auto-load scan results from cache when account/region changes
    useEffect(() => {
        if (selectedAccount) {
            handleScan(false); // Try to load from cache
        }
    }, [selectedAccount, selectedRegion]);

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

    const handleScan = async (forceRefresh = false) => {
        if (!selectedAccount) return;
        setLoading(true);
        try {
            const regionsToScan = selectedRegion === 'ALL' ? ['ALL'] : [selectedRegion];
            const res = await cleanupAPI.scan(selectedAccount, {
                regions: regionsToScan,
                force_refresh: forceRefresh
            });
            setScanResult(res.data);
            setSelectedItems([]);
            if (forceRefresh) toast.success("Scan refreshed successfully");
        } catch (err) {
            console.error("Scan failed", err);
            // Don't clear result if just a failed refresh, but maybe show error?
            // If it was an initial load error, we might want to clear.
            if (!scanResult) {
                setScanResult({
                    total_potential_savings: 0,
                    unauthorized_instance_count: 0,
                    orphaned_volume_count: 0,
                    orphaned_snapshot_count: 0,
                    unused_ip_count: 0,
                    resources: []
                });
            }
        } finally {
            setLoading(false);
        }
    };

    const handleCleanupClick = async (actionType) => {
        if (!selectedAccount || selectedItems.length === 0) return;

        // Skip dependency check for authorization actions
        if (actionType === 'AUTHORIZE' || actionType === 'UNAUTHORIZE') {
            executeCleanupAction(actionType);
            return;
        }

        const needsCheck = ['DELETE', 'TERMINATE'].includes(actionType) && ['SNAPSHOT', 'VOLUME'].includes(activeTab);

        if (!needsCheck) {
            executeCleanupAction(actionType);
            return;
        }

        setCheckingDependencies(true);
        const allBlockers = [];

        try {
            for (const itemId of selectedItems) {
                const item = scanResult.resources.find(r => r.id === itemId);
                if (item) {
                    try {
                        const response = await cleanupAPI.checkDependencies(
                            selectedAccount, item.type, item.id, item.region
                        );
                        if (response.data.blocking_resources?.length > 0) {
                            allBlockers.push({
                                resource: item,
                                blockers: response.data.blocking_resources
                            });
                        }
                    } catch (e) { console.error("Dep check failed for", itemId, e); }
                }
            }

            if (allBlockers.length > 0) {
                setBlockingResources(allBlockers);
                setShowDependencyModal(true);
                setPendingAction(actionType);
            } else {
                executeCleanupAction(actionType);
            }
        } catch (err) {
            console.error("Dependency check error", err);
            executeCleanupAction(actionType);
        } finally {
            setCheckingDependencies(false);
        }
    };

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
                if (actionType === 'AUTHORIZE') toast.success('Resources authorized successfully');
                else if (actionType === 'UNAUTHORIZE') toast.success('Resources unauthorized successfully');
                else toast.success('Cleaned up resources successfully');
            }

            handleScan(true);
        } catch (err) {
            console.error("Action failed", err);
            toast.error("Failed to execute action: " + err.message);
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

    const filteredResources = scanResult?.resources.filter(r =>
        r.type === activeTab && (showAuthorized ? r.is_authorized : !r.is_authorized)
    ) || [];

    const getSafetyLevel = (resource) => {
        if (resource.is_authorized) return 'HIGH'; // Authorized is explicitly safe
        if (resource.status === 'SAFE_TO_DELETE') return 'HIGH';
        if (resource.type === 'VOLUME' && resource.status === 'ORPHANED') return 'HIGH';
        if (resource.type === 'SNAPSHOT' && resource.status === 'ORPHANED') return 'HIGH';
        if (resource.type === 'ELASTIC_IP' && resource.status === 'ORPHANED') return 'HIGH';
        if (resource.type === 'LOAD_BALANCER' && resource.status === 'ORPHANED') return 'HIGH';
        if (resource.type === 'IAM_USER' && resource.status === 'SAFE_TO_DELETE') return 'HIGH';
        if (resource.type === 'RDS_DB' && resource.status === 'LEGACY_UPGRADE') return 'MEDIUM';
        if (resource.type === 'INSTANCE' && resource.status === 'UNAUTHORIZED') return 'MEDIUM';
        return 'LOW';
    };

    const stats = scanResult || {
        total_potential_savings: 0,
        unauthorized_instance_count: 0,
        orphaned_volume_count: 0,
        orphaned_snapshot_count: 0,
        unused_ip_count: 0,
        idle_lb_count: 0,
        idle_rds_count: 0,
        dormant_user_count: 0,
        untagged_waste_cost: 0
    };

    const selectedSavings = scanResult?.resources
        .filter(r => selectedItems.includes(r.id))
        .reduce((sum, r) => sum + r.cost_per_month, 0) || 0;

    const totalResources = scanResult?.resources?.length || 0;

    const tabConfig = [
        { type: 'INSTANCE', label: 'Instances', icon: FiServer, action: 'TERMINATE' },
        { type: 'VOLUME', label: 'Volumes', icon: FiHardDrive, action: 'DELETE' },
        { type: 'SNAPSHOT', label: 'Snapshots', icon: FiCamera, action: 'DELETE' },
        { type: 'ELASTIC_IP', label: 'Elastic IPs', icon: FiGlobe, action: 'RELEASE' },
        { type: 'LOAD_BALANCER', label: 'Load Balancers', icon: FiShare2, action: 'DELETE' },
        { type: 'NETWORK_INTERFACE', label: 'Network Interfaces', icon: FiLink, action: 'DELETE' },
        { type: 'RDS_DB', label: 'Databases', icon: FiDatabase, action: 'SNAPSHOT_STOP' },
        { type: 'IAM_USER', label: 'Identity', icon: FiUsers, action: 'DISABLE' },
        { type: 'S3_BUCKET', label: 'Storage', icon: FiFolder, action: 'DELETE' },
    ];

    return (
        <div className="p-6 space-y-6 bg-gray-50 min-h-screen">
            {/* Header Card */}
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
                <div className="flex flex-col lg:flex-row justify-between items-start lg:items-center gap-4">
                    <div>
                        <h1 className="text-2xl font-bold text-gray-900">Resource Hygiene</h1>
                        <p className="text-sm text-gray-500 mt-1">Scan and eliminate waste across your AWS infrastructure</p>
                    </div>
                    <div className="flex flex-wrap items-center gap-3">
                        <div className="flex items-center gap-2 px-3 py-2 bg-green-50 border border-green-200 rounded-lg">
                            <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></span>
                            <span className="text-sm font-medium text-green-700">Connected</span>
                        </div>
                        <select
                            className="border border-gray-200 rounded-lg px-4 py-2 text-sm bg-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                            value={selectedAccount}
                            onChange={(e) => setSelectedAccount(e.target.value)}
                        >
                            {accounts.map(acc => (
                                <option key={acc.id} value={acc.id}>{acc.name || acc.aws_account_id}</option>
                            ))}
                        </select>
                        <select
                            className="border border-gray-200 rounded-lg px-4 py-2 text-sm bg-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                            value={selectedRegion}
                            onChange={(e) => setSelectedRegion(e.target.value)}
                        >
                            {regionsList.map(r => (
                                <option key={r.id} value={r.id}>{r.name}</option>
                            ))}
                        </select>
                        <button
                            onClick={() => handleScan(true)}
                            disabled={loading || !selectedAccount}
                            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                        >
                            {loading ? (
                                <>
                                    <FiRefreshCw className="animate-spin" />
                                    Scanning...
                                </>
                            ) : (
                                <>
                                    <FiRefreshCw />
                                    {scanResult ? 'Refresh Scan' : 'Start Scan'}
                                </>
                            )}
                        </button>
                    </div>
                </div>
            </div>

            {/* Two Column Layout */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Left Column - Details & Stats */}
                <div className="lg:col-span-2 space-y-6">
                    {/* Scan Details Card */}
                    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
                        <h2 className="text-lg font-semibold text-gray-900 mb-4">Scan Details</h2>
                        <div className="grid grid-cols-2 md:grid-cols-3 gap-4 text-sm">
                            <div>
                                <span className="text-gray-500 uppercase text-xs tracking-wide">SCAN STATUS:</span>
                                <div className="mt-1 flex items-center gap-2">
                                    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${scanResult ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-600'}`}>
                                        {scanResult ? '● Completed' : '○ Not Started'}
                                    </span>
                                </div>
                            </div>
                            <div>
                                <span className="text-gray-500 uppercase text-xs tracking-wide">REGION:</span>
                                <p className="text-gray-900 font-medium mt-1">{selectedRegion === 'ALL' ? 'Global' : selectedRegion}</p>
                            </div>
                            <div>
                                <span className="text-gray-500 uppercase text-xs tracking-wide">TOTAL RESOURCES:</span>
                                <p className="text-gray-900 font-medium mt-1">{totalResources}</p>
                            </div>
                            <div>
                                <span className="text-gray-500 uppercase text-xs tracking-wide">POTENTIAL SAVINGS:</span>
                                <p className="text-green-600 font-bold mt-1 text-lg">${stats.total_potential_savings.toFixed(2)}/mo</p>
                            </div>
                            <div>
                                <span className="text-gray-500 uppercase text-xs tracking-wide">SELECTED SAVINGS:</span>
                                <p className="text-blue-600 font-bold mt-1 text-lg">${selectedSavings.toFixed(2)}/mo</p>
                            </div>
                            <div>
                                <span className="text-gray-500 uppercase text-xs tracking-wide">UNTAGGED WASTE:</span>
                                <p className="text-red-600 font-bold mt-1 text-lg">${(stats.untagged_waste_cost || 0).toFixed(2)}/mo</p>
                            </div>
                        </div>
                    </div>

                    {/* Resource Type Cards */}
                    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
                        <div className="flex items-center justify-between mb-4">
                            <h2 className="text-lg font-semibold text-gray-900">Resource Breakdown</h2>
                            <span className="text-xs text-gray-500 uppercase tracking-wide">By Type</span>
                        </div>
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                            {tabConfig.map(tab => {
                                const count = scanResult?.resources?.filter(r => r.type === tab.type && !r.is_authorized).length || 0;
                                const isActive = activeTab === tab.type;
                                return (
                                    <button
                                        key={tab.type}
                                        onClick={() => setActiveTab(tab.type)}
                                        className={`p-4 rounded-xl border-2 transition-all ${isActive
                                            ? 'border-blue-500 bg-blue-50'
                                            : 'border-gray-200 bg-white hover:border-gray-300'
                                            }`}
                                    >
                                        <div className="flex items-center justify-between mb-3">
                                            <tab.icon className={`w-5 h-5 ${isActive ? 'text-blue-600' : 'text-gray-400'}`} />
                                            <span className={`text-2xl font-bold ${isActive ? 'text-blue-600' : 'text-gray-900'}`}>
                                                {count}
                                            </span>
                                        </div>
                                        <p className={`text-sm font-medium ${isActive ? 'text-blue-600' : 'text-gray-600'}`}>
                                            {tab.label}
                                        </p>
                                    </button>
                                );
                            })}
                        </div>
                    </div>
                </div>

                {/* Right Column - Gauge Charts */}
                <div className="space-y-6">
                    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
                        <h2 className="text-lg font-semibold text-gray-900 mb-6">Resource Metrics</h2>
                        <div className="grid grid-cols-2 gap-6">
                            <GaugeChart
                                value={stats.unauthorized_instance_count}
                                maxValue={Math.max(stats.unauthorized_instance_count, 10)}
                                label="Instances"
                                unit="Unauthorized"
                                color="red"
                            />
                            <GaugeChart
                                value={stats.orphaned_volume_count}
                                maxValue={Math.max(stats.orphaned_volume_count, 10)}
                                label="Volumes"
                                unit="Orphaned"
                                color="yellow"
                            />
                            <GaugeChart
                                value={stats.orphaned_snapshot_count || 0}
                                maxValue={Math.max(stats.orphaned_snapshot_count || 0, 10)}
                                label="Snapshots"
                                unit="Orphaned"
                                color="blue"
                            />
                            <GaugeChart
                                value={stats.unused_ip_count}
                                maxValue={Math.max(stats.unused_ip_count, 10)}
                                label="Elastic IPs"
                                unit="Unused"
                                color="indigo"
                            />
                            <GaugeChart
                                value={stats.idle_lb_count || 0}
                                maxValue={Math.max(stats.idle_lb_count || 0, 10)}
                                label="Load Balancers"
                                unit="Idle"
                                color="purple"
                            />
                            <GaugeChart
                                value={stats.idle_rds_count || 0}
                                maxValue={Math.max(stats.idle_rds_count || 0, 10)}
                                label="Databases"
                                unit="Idle/Legacy"
                                color="orange"
                            />
                            <GaugeChart
                                value={stats.dormant_user_count || 0}
                                maxValue={Math.max(stats.dormant_user_count || 0, 10)}
                                label="IAM Users"
                                unit="Dormant"
                                color="pink"
                            />
                        </div>
                    </div>

                    {/* Quick Actions Card */}
                    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
                        <div className="flex items-center justify-between mb-3">
                            <h2 className="text-sm font-semibold text-gray-900 uppercase tracking-wide">Quick Actions</h2>
                            <span className="text-xs text-gray-400">{selectedItems.length} selected</span>
                        </div>
                        <div className="space-y-3">
                            {showAuthorized ? (
                                <button
                                    onClick={() => handleCleanupClick('UNAUTHORIZE')}
                                    disabled={selectedItems.length === 0 || actionLoading}
                                    className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-gray-600 text-white rounded-lg font-medium hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                                >
                                    {actionLoading ? 'Processing...' : `Unauthorize Selected`}
                                </button>
                            ) : (
                                <button
                                    onClick={() => handleCleanupClick('AUTHORIZE')}
                                    disabled={selectedItems.length === 0 || actionLoading}
                                    className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-indigo-600 text-white rounded-lg font-medium hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                                >
                                    {actionLoading ? 'Processing...' : `Authorize Selected`}
                                </button>
                            )}

                            <button
                                onClick={() => handleCleanupClick(tabConfig.find(t => t.type === activeTab)?.action || 'DELETE')}
                                disabled={selectedItems.length === 0 || actionLoading || checkingDependencies}
                                className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-red-600 text-white rounded-lg font-medium hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                            >
                                {checkingDependencies ? 'Checking...' : actionLoading ? 'Processing...' : `Cleanup ${selectedItems.length} Selected`}
                            </button>
                        </div>
                    </div>
                </div>
            </div>

            {/* Resources Table */}
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
                {/* Table Header */}
                <div className="p-4 border-b border-gray-200 flex justify-between items-center">
                    <div className="flex items-center gap-4">
                        <h2 className="text-lg font-semibold text-gray-900">
                            {tabConfig.find(t => t.type === activeTab)?.label || 'Resources'}
                        </h2>
                        <span className="text-sm text-gray-500">
                            {filteredResources.length} found
                            {selectedItems.length > 0 && (
                                <span className="ml-2 text-blue-600">• {selectedItems.length} selected</span>
                            )}
                        </span>
                    </div>

                    {/* Filter Toggles */}
                    <div className="flex items-center p-1 bg-gray-100 rounded-lg">
                        <button
                            onClick={() => { setShowAuthorized(false); setSelectedItems([]); }}
                            className={`px-3 py-1.5 text-xs font-medium rounded-md transition-all ${!showAuthorized
                                ? 'bg-white text-gray-900 shadow-sm'
                                : 'text-gray-500 hover:text-gray-700'
                                }`}
                        >
                            To Review
                        </button>
                        <button
                            onClick={() => { setShowAuthorized(true); setSelectedItems([]); }}
                            className={`px-3 py-1.5 text-xs font-medium rounded-md transition-all ${showAuthorized
                                ? 'bg-white text-indigo-600 shadow-sm'
                                : 'text-gray-500 hover:text-gray-700'
                                }`}
                        >
                            Authorized
                        </button>
                    </div>
                </div>

                {/* Content */}
                {loading ? (
                    <div className="flex flex-col items-center justify-center h-64">
                        <FiRefreshCw className="animate-spin h-8 w-8 text-blue-600 mb-4" />
                        <p className="text-gray-500">Scanning {selectedRegion === 'ALL' ? 'all regions' : selectedRegion}...</p>
                    </div>
                ) : !scanResult ? (
                    <div className="flex flex-col items-center justify-center h-64 text-center px-4">
                        <div className="bg-blue-50 p-4 rounded-full mb-4">
                            <FiRefreshCw className="h-8 w-8 text-blue-400" />
                        </div>
                        <h3 className="text-lg font-medium text-gray-900">Ready to Scan</h3>
                        <p className="text-gray-500 max-w-sm mt-1">Select an account and region, then click "Start Scan" to identify cleanup opportunities.</p>
                    </div>
                ) : filteredResources.length === 0 ? (
                    <div className="flex flex-col items-center justify-center h-64 text-center">
                        <div className="bg-green-50 p-4 rounded-full mb-4">
                            <FiCheckCircle className="h-8 w-8 text-green-500" />
                        </div>
                        <h3 className="text-lg font-medium text-gray-900">All Clean!</h3>
                        <p className="text-gray-500">No {showAuthorized ? 'authorized' : 'orphaned'} {activeTab.toLowerCase().replace('_', ' ')}s found.</p>
                    </div>
                ) : (
                    <div className="overflow-x-auto">
                        <table className="min-w-full divide-y divide-gray-200">
                            <thead className="bg-gray-50">
                                <tr>
                                    <th className="px-6 py-3 text-left w-12">
                                        <input
                                            type="checkbox"
                                            className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                                            onChange={(e) => {
                                                if (e.target.checked) setSelectedItems(filteredResources.map(r => r.id));
                                                else setSelectedItems([]);
                                            }}
                                            checked={filteredResources.length > 0 && selectedItems.length === filteredResources.length}
                                        />
                                    </th>
                                    <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">Resource ID</th>
                                    <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">Name</th>
                                    <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">Reason</th>
                                    <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">Region</th>
                                    <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">Status</th>
                                    <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">Compliance</th>
                                    <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">Safety</th>
                                    <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">Cost</th>
                                </tr>
                            </thead>
                            <tbody className="bg-white divide-y divide-gray-200">
                                {filteredResources.map(resource => (
                                    <tr key={resource.id} className={`hover:bg-gray-50 transition-colors ${selectedItems.includes(resource.id) ? 'bg-blue-50' : ''}`}>
                                        <td className="px-6 py-4 whitespace-nowrap">
                                            <input
                                                type="checkbox"
                                                disabled={resource.status === 'PENDING_APPROVAL'}
                                                className="rounded border-gray-300 text-blue-600 focus:ring-blue-500 disabled:opacity-50"
                                                checked={selectedItems.includes(resource.id)}
                                                onChange={() => toggleSelection(resource.id)}
                                            />
                                        </td>
                                        <td className="px-6 py-4 whitespace-nowrap text-sm font-mono text-gray-900">{resource.id}</td>
                                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600">{resource.name || '-'}</td>
                                        <td className="px-6 py-4 text-sm text-gray-500 max-w-xs truncate" title={resource.reason}>
                                            {resource.reason || '-'}
                                        </td>
                                        <td className="px-6 py-4 whitespace-nowrap">
                                            <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-700">
                                                {resource.region}
                                            </span>
                                        </td>
                                        <td className="px-6 py-4 whitespace-nowrap">
                                            {resource.is_authorized ? (
                                                <Badge type="info">AUTHORIZED</Badge>
                                            ) : (
                                                <Badge type={resource.status === 'SAFE_TO_DELETE' ? 'success' : (resource.status === 'ORPHANED' || resource.status === 'UNAUTHORIZED' ? 'warning' : 'neutral')}>
                                                    {resource.status.replace(/_/g, ' ')}
                                                </Badge>
                                            )}

                                            {resource.type === 'INSTANCE' && resource.metadata?.State && (
                                                <span className={`ml-2 inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${resource.metadata.State === 'running' ? 'bg-green-100 text-green-800' :
                                                    resource.metadata.State === 'stopped' ? 'bg-gray-100 text-gray-800' :
                                                        'bg-yellow-100 text-yellow-800'
                                                    }`}>
                                                    {resource.metadata.State.toUpperCase()}
                                                </span>
                                            )}
                                            {resource.type === 'LOAD_BALANCER' && (
                                                <div className="text-xs text-gray-500 mt-1">
                                                    {resource.metadata?.DNS} (Type: {resource.metadata?.Type})
                                                </div>
                                            )}
                                            {resource.type === 'RDS_DB' && (
                                                <div className="text-xs text-gray-500 mt-1">
                                                    {resource.metadata?.Engine} ({resource.metadata?.Class})
                                                </div>
                                            )}
                                            {resource.type === 'S3_BUCKET' && resource.metadata?.IncompleteUploads > 0 && (
                                                <div className="text-xs text-red-500 mt-1">
                                                    {resource.metadata?.IncompleteUploads} Incomplete Uploads
                                                </div>
                                            )}
                                            {resource.type === 'IAM_USER' && (
                                                <div className="text-xs text-gray-500 mt-1">
                                                    Last Used: {resource.metadata?.LastUsed}
                                                </div>
                                            )}
                                        </td>
                                        <td className="px-6 py-4 whitespace-nowrap">
                                            {resource.is_compliant !== false ? (
                                                <span className="bg-green-100 text-green-800 text-xs font-medium px-2 py-1 rounded-full flex items-center w-fit">
                                                    <FiCheckCircle className="mr-1" /> Compliant
                                                </span>
                                            ) : (
                                                <div className="relative group">
                                                    <span className="bg-red-100 text-red-800 text-xs font-medium px-2 py-1 rounded-full flex items-center w-fit cursor-help">
                                                        <FiTag className="mr-1" /> Untagged
                                                    </span>
                                                    {resource.missing_tags?.length > 0 && (
                                                        <div className="absolute left-0 top-full mt-1 w-48 bg-gray-900 text-white text-xs rounded py-2 px-3 opacity-0 group-hover:opacity-100 transition-opacity z-20 shadow-lg">
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
                                                <span className="bg-green-100 text-green-800 text-xs font-medium px-2 py-1 rounded-full flex items-center w-fit">
                                                    <FiShield className="mr-1" /> Safe
                                                </span>
                                            )}
                                            {getSafetyLevel(resource) === 'MEDIUM' && (
                                                <span className="bg-yellow-100 text-yellow-800 text-xs font-medium px-2 py-1 rounded-full flex items-center w-fit">
                                                    <FiAlertTriangle className="mr-1" /> Review
                                                </span>
                                            )}
                                            {getSafetyLevel(resource) === 'LOW' && (
                                                <span className="bg-red-100 text-red-800 text-xs font-medium px-2 py-1 rounded-full flex items-center w-fit">
                                                    <FiAlertOctagon className="mr-1" /> Risky
                                                </span>
                                            )}
                                        </td>
                                        <td className="px-6 py-4 whitespace-nowrap">
                                            <div className="text-sm font-medium text-gray-900">${resource.cost_per_month.toFixed(2)}/mo</div>
                                            <div className="text-xs text-gray-500">${(resource.cost_per_month / 30).toFixed(2)}/day</div>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>

            {/* Dependency Warning Modal */}
            {showDependencyModal && (
                <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
                    <div className="bg-white rounded-xl shadow-xl max-w-lg w-full mx-4 overflow-hidden">
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
                                <div key={idx} className="mb-3 p-3 bg-gray-50 rounded-lg">
                                    <p className="font-medium text-gray-900">{item.resource.id}</p>
                                    <p className="text-sm text-gray-500">Blocked by:</p>
                                    <ul className="mt-1 text-sm text-gray-600">
                                        {item.blockers.map((b, i) => (
                                            <li key={i} className="ml-4 list-disc">{b.type}: {b.id}</li>
                                        ))}
                                    </ul>
                                </div>
                            ))}
                        </div>
                        <div className="p-4 bg-gray-50 border-t border-gray-200 flex justify-end gap-3">
                            <button
                                onClick={() => {
                                    setShowDependencyModal(false);
                                    setBlockingResources([]);
                                    setPendingAction(null);
                                }}
                                className="px-4 py-2 text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50"
                            >
                                Cancel
                            </button>
                            <button
                                onClick={() => {
                                    setShowDependencyModal(false);
                                    executeCleanupAction(pendingAction);
                                }}
                                className="px-4 py-2 text-white bg-red-600 rounded-lg hover:bg-red-700"
                            >
                                Force Delete Anyway
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default CleanupDashboard;
