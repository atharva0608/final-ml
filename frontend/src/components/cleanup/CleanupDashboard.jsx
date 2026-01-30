import React, { useState, useEffect } from 'react';
import { cleanupAPI, accountsAPI } from '../../services/api';
import toast from 'react-hot-toast';
import {
    FiRefreshCw, FiServer, FiHardDrive, FiCamera, FiGlobe,
    FiShare2, FiLink, FiDatabase, FiUsers, FiFolder,
    FiTrendingUp, FiTrendingDown, FiArchive, FiActivity
} from 'react-icons/fi';

// New Components
import HeroMetricsPanel from './summary/HeroMetricsPanel';
import SavingsGauge from './summary/SavingsGauge';
import ResourceTable from './tables/ResourceTable';
import FilterPanel from './layout/FilterPanel';
import CleanupSidebar from './layout/CleanupSidebar';
import RIWizard from './wizards/RIWizard';
import S3Wizard from './wizards/S3Wizard';
import RDSWizard from './wizards/RDSWizard';
import TagPoliciesManager from '../settings/TagPoliciesManager';
import BulkTagEditor from './BulkTagEditor';
import CleanupPolicies from '../policies/CleanupPolicies';
import { FiCheck, FiX, FiTrash2, FiTag } from 'react-icons/fi';

const CleanupDashboard = () => {
    // -------------------------------------------------------------------------
    // STATE
    // -------------------------------------------------------------------------
    const [loading, setLoading] = useState(false);
    const [accounts, setAccounts] = useState([]);
    const [selectedAccount, setSelectedAccount] = useState('');
    const [scanResult, setScanResult] = useState(null);
    const [activeTab, setActiveTab] = useState('INSTANCE');
    const [selectedItems, setSelectedItems] = useState([]);
    const [actionLoading, setActionLoading] = useState(false);
    const [selectedRegion, setSelectedRegion] = useState('ALL');
    const [showAuthorized, setShowAuthorized] = useState(false);

    // Dependency Modal State
    const [showDependencyModal, setShowDependencyModal] = useState(false);
    const [blockingResources, setBlockingResources] = useState([]);

    // Wizard States
    const [showRIWizard, setShowRIWizard] = useState(false);
    const [showS3Wizard, setShowS3Wizard] = useState(false);
    const [showRDSWizard, setShowRDSWizard] = useState(false);
    const [showBulkTagWizard, setShowBulkTagWizard] = useState(false);

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

    // Note: tabConfig logic moved to Sidebar, but we kept label mapping for header
    const getTabLabel = (type) => {
        const map = {
            'INSTANCE': 'Compute Instances', 'RI_WASTE': 'Reserved Instances', 'RDS_MULTIAZ': 'RDS Multi-AZ',
            'VOLUME': 'EBS Volumes', 'SNAPSHOT': 'Snapshots', 'S3_BUCKET': 'S3 Buckets', 'S3_LIFECYCLE': 'S3 Lifecycle',
            'RDS_DB': 'RDS Databases', 'ELASTIC_IP': 'Elastic IPs', 'LOAD_BALANCER': 'Load Balancers',
            'NETWORK_INTERFACE': 'Network Interfaces', 'DATA_TRANSFER': 'Data Transfer', 'IAM_USER': 'IAM Users'
        };
        return map[type] || 'Resources';
    };

    // -------------------------------------------------------------------------
    // EFFECTS
    // -------------------------------------------------------------------------
    useEffect(() => {
        fetchAccounts();
    }, []);

    useEffect(() => {
        if (selectedAccount) {
            handleScan(false);
        }
    }, [selectedAccount, selectedRegion]);

    // -------------------------------------------------------------------------
    // API HANDLERS
    // -------------------------------------------------------------------------
    const fetchAccounts = async () => {
        try {
            const res = await accountsAPI.list();
            setAccounts(res.data);
            if (res.data.length > 0) setSelectedAccount(res.data[0].id);
        } catch (err) { console.error("Failed to load accounts", err); }
    };

    const handleScan = async (forceRefresh = false) => {
        if (!selectedAccount) return;
        setLoading(true);
        try {
            const res = await cleanupAPI.scan(selectedAccount, {
                regions: selectedRegion === 'ALL' ? ['ALL'] : [selectedRegion],
                force_refresh: forceRefresh
            });
            setScanResult(res.data);
            setSelectedItems([]);
            if (forceRefresh) toast.success("Scan refreshed successfully");
        } catch (err) {
            console.error("Scan failed", err);
            if (!scanResult) setScanResult(null);
        } finally {
            setLoading(false);
        }
    };

    // -------------------------------------------------------------------------
    // HELPER LOGIC
    // -------------------------------------------------------------------------
    const filteredResources = scanResult?.resources?.filter(r =>
        r.type === activeTab && (showAuthorized ? r.is_authorized : !r.is_authorized)
    ) || [];

    const toggleSelection = (id) => {
        setSelectedItems(prev => prev.includes(id) ? prev.filter(i => i !== id) : [...prev, id]);
    };

    // -------------------------------------------------------------------------
    // RENDER
    // -------------------------------------------------------------------------
    const selectedResourceObjects = scanResult?.resources?.filter(r => selectedItems.includes(r.id)) || [];

    return (
        <div className="h-screen bg-gray-50 flex flex-col overflow-hidden font-sans">
            {/* 1. Global Header & Filter Bar */}
            <header className="bg-white border-b border-gray-200 flex-shrink-0 z-20">
                <div className="flex items-center justify-between px-6 py-3 border-b border-gray-100">
                    <div className="flex items-center gap-3">
                        <div className="bg-gray-900 p-1.5 rounded-lg">
                            <FiServer className="text-white w-5 h-5" />
                        </div>
                        <h1 className="text-lg font-bold text-gray-900 tracking-tight">Resource Hygiene</h1>
                    </div>
                    {/* User Profile / Global Actions could go here */}
                </div>
                <div className="bg-white border-b border-gray-100 px-6 py-2 flex items-center justify-between">
                    {/* Left: Bulk Actions (Static) */}
                    <div className="flex items-center gap-3">
                        <button
                            onClick={() => {
                                toast.success(`Authorized ${selectedItems.length} resources`);
                                setSelectedItems([]);
                            }}
                            disabled={selectedItems.length === 0}
                            className="flex items-center gap-2 px-3 py-1.5 bg-white border border-gray-300 text-gray-700 hover:bg-gray-50 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                            <FiCheck className="text-green-600" /> Authorize
                        </button>
                        <button
                            onClick={() => {
                                toast.success(`Unauthorized ${selectedItems.length} resources`);
                                setSelectedItems([]);
                            }}
                            disabled={selectedItems.length === 0}
                            className="flex items-center gap-2 px-3 py-1.5 bg-white border border-gray-300 text-gray-700 hover:bg-gray-50 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                            <FiX className="text-red-500" /> Unauthorize
                        </button>
                        <button
                            onClick={() => setShowBulkTagWizard(true)}
                            disabled={selectedItems.length === 0}
                            className="flex items-center gap-2 px-3 py-1.5 bg-white border border-gray-300 text-gray-700 hover:bg-gray-50 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                            <FiTag className="text-gray-500" /> Tag
                        </button>
                        <div className="h-6 w-px bg-gray-200 mx-2"></div>
                        <button
                            onClick={() => {
                                toast.success(`Cleanup initiated for ${selectedItems.length} resources`);
                                setSelectedItems([]);
                            }}
                            disabled={selectedItems.length === 0}
                            className="flex items-center gap-2 px-3 py-1.5 bg-red-600 hover:bg-red-700 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed shadow-sm"
                        >
                            <FiTrash2 /> Cleanup
                        </button>
                    </div>

                    {/* Right: Live Savings Gauge */}
                    <div className="animate-fadeIn">
                        <SavingsGauge
                            selectedSavings={selectedResourceObjects.reduce((sum, r) => sum + (r.cost_per_month || 0), 0)}
                            totalPotentialSavings={scanResult?.summary?.total_potential_savings || selectedResourceObjects.reduce((sum, r) => sum + (r.cost_per_month || 0), 0)}
                        />
                    </div>
                </div>
                <FilterPanel
                    accounts={accounts}
                    selectedAccount={selectedAccount}
                    onAccountChange={setSelectedAccount}
                    selectedRegion={selectedRegion}
                    onRegionChange={setSelectedRegion}
                    regionsList={regionsList}
                    onRefresh={() => handleScan(true)}
                    loading={loading}
                    lastScan={scanResult?.metadata?.scan_time}
                />
            </header>

            {/* 2. Main Layout (Sidebar + Content) */}
            <div className="flex flex-1 overflow-hidden">
                {/* Sidebar */}
                <CleanupSidebar
                    activeTab={activeTab}
                    onTabChange={setActiveTab}
                    scanResult={scanResult}
                />

                {/* Content Area */}
                <main className="flex-1 overflow-y-auto bg-gray-50 p-8">
                    <div className="max-w-7xl mx-auto space-y-8">
                        {/* Metrics */}
                        <HeroMetricsPanel
                            scanResult={scanResult}
                            stats={scanResult || {}}
                        />

                        {/* Interactive Area Placeholder */}
                        {/* <div className="bg-white rounded-xl border border-gray-200 h-64 flex items-center justify-center text-gray-400 text-sm">
                            Visualization Area for {activeTab}
                        </div> */}

                        {/* Resource Table Section */}
                        <div className="space-y-4">
                            <div className="flex justify-between items-end">
                                <div>
                                    <h2 className="text-xl font-bold text-gray-900">{getTabLabel(activeTab)}</h2>
                                    <p className="text-sm text-gray-500 mt-1">Review and action logical resources.</p>
                                </div>

                                {activeTab !== 'POLICIES' && (
                                    <div className="flex bg-gray-200 rounded-lg p-1 gap-1">
                                        <button
                                            className={`px-4 py-1.5 text-xs font-semibold rounded-md transition-all ${!showAuthorized ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-600 hover:text-gray-900'}`}
                                            onClick={() => setShowAuthorized(false)}
                                        >
                                            Issues
                                        </button>
                                        <button
                                            className={`px-4 py-1.5 text-xs font-semibold rounded-md transition-all ${showAuthorized ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-600 hover:text-gray-900'}`}
                                            onClick={() => setShowAuthorized(true)}
                                        >
                                            Authorized
                                        </button>
                                    </div>
                                )}
                            </div>

                            {activeTab === 'POLICIES' ? (
                                <CleanupPolicies />
                            ) : activeTab === 'TAG_POLICIES' ? (
                                <TagPoliciesManager />
                            ) : (
                                <ResourceTable
                                    resources={filteredResources}
                                    loading={loading}
                                    selectedItems={selectedItems}
                                    toggleSelection={toggleSelection}
                                    setSelectedItems={setSelectedItems}
                                    activeTab={activeTab}
                                    showAuthorized={showAuthorized}
                                />
                            )}
                        </div>
                    </div>
                </main>
            </div>

            {/* Optimization Wizards - Global Modals */}
            <RIWizard
                isOpen={showRIWizard}
                onClose={() => setShowRIWizard(false)}
                selectedResources={selectedResourceObjects}
            />
            <S3Wizard
                isOpen={showS3Wizard}
                onClose={() => setShowS3Wizard(false)}
                selectedResources={selectedResourceObjects}
            />
            <RDSWizard
                isOpen={showRDSWizard}
                onClose={() => setShowRDSWizard(false)}
                selectedResources={selectedResourceObjects}
            />
            {showBulkTagWizard && (
                <BulkTagEditor
                    resources={selectedResourceObjects}
                    onClose={() => setShowBulkTagWizard(false)}
                    onSuccess={() => handleScan(true)}
                />
            )}

            {/* Floating Action Bars for Optimization Tabs */}
            {activeTab === 'RI_WASTE' && (
                <div className="fixed bottom-8 right-8 z-30">
                    <button
                        onClick={() => setShowRIWizard(true)}
                        className="bg-gray-900 text-white px-6 py-3 rounded-lg shadow-lg hover:bg-black font-medium flex items-center gap-2 transition-transform hover:-translate-y-1"
                    >
                        <FiTrendingUp /> Optimize RIs
                    </button>
                </div>
            )}
            {activeTab === 'S3_LIFECYCLE' && (
                <div className="fixed bottom-8 right-8 z-30">
                    <button
                        onClick={() => setShowS3Wizard(true)}
                        className="bg-gray-900 text-white px-6 py-3 rounded-lg shadow-lg hover:bg-black font-medium flex items-center gap-2 transition-transform hover:-translate-y-1"
                    >
                        <FiArchive /> Manage Lifecycles
                    </button>
                </div>
            )}
            {activeTab === 'RDS_MULTIAZ' && (
                <div className="fixed bottom-8 right-8 z-30">
                    <button
                        onClick={() => setShowRDSWizard(true)}
                        className="bg-gray-900 text-white px-6 py-3 rounded-lg shadow-lg hover:bg-black font-medium flex items-center gap-2 transition-transform hover:-translate-y-1"
                    >
                        <FiDatabase /> Review Multi-AZ
                    </button>
                </div>
            )}
        </div>
    );
};

export default CleanupDashboard;
