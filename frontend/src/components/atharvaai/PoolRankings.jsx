import React, { useState, useEffect } from 'react';
import { FiGlobe, FiServer, FiPieChart, FiInfo, FiLock, FiAlertTriangle, FiCheckCircle } from 'react-icons/fi';
import { atharvaaiAPI, clusterAPI, nodeTemplateAPI } from '../../services/api';
import './PoolRankings.css';

/**
 * Derive instance family from full type string.
 * e.g. 't3.medium' → 't3', 'm5.large' → 'm5', 'c6g.xlarge' → 'c6g'
 */
const getInstanceFamily = (instanceType) => {
    if (!instanceType) return null;
    const match = instanceType.match(/^([a-z]+\d*[a-z]*)/);
    return match ? match[1] : null;
};

const buildTemplate = (primaryInstanceType) => {
    return {
        architecture: ['amd64', 'arm64'],   // include Graviton
        vcpu_min: 1,
        vcpu_max: 128,
        memory_gb_min: 1,
        memory_gb_max: 512,
        allowed_families: null, // Allow backend or actual cluster config to dictate families
        allowed_sizes: null,
        allowed_azs: null,
        excluded_instance_types: [],
    };
};

const PoolRankings = ({ clusterId, initialTemplateId = null }) => {
    const [pools, setPools] = useState([]);
    const [loading, setLoading] = useState(!!clusterId);
    const [error, setError] = useState(null);
    const [blacklist, setBlacklist] = useState([]);
    const [activeTab, setActiveTab] = useState('market'); // 'market', 'node', 'cluster'
    const [autoRefresh, setAutoRefresh] = useState(false);
    const [nodeRecommendations, setNodeRecommendations] = useState([]);
    const [eligiblePoolsCount, setEligiblePoolsCount] = useState(0);
    const [clusterImpact, setClusterImpact] = useState(null);
    const [nodeViewLoading, setNodeViewLoading] = useState(false);
    const [clusterViewLoading, setClusterViewLoading] = useState(false);
    const [effectiveConfig, setEffectiveConfig] = useState(null);
    const [clusterInfo, setClusterInfo] = useState({
        region: 'us-east-1',
        primaryInstanceType: null,   // e.g. 't3.medium'
        primaryLifecycle: 'on-demand',
        templateName: null,          // name of the active node template (for display)
    });

    useEffect(() => {
        if (clusterId) {
            loadData();
            fetchBlacklist();
        }

        const interval = setInterval(() => {
            if (autoRefresh && clusterId) {
                loadData();
                fetchBlacklist();
            }
        }, 30000);

        return () => clearInterval(interval);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [autoRefresh, clusterId]);

    /**
     * Full data load:
     * 1. Fetch cluster region + primary instance type from nodes/detailed
     * 2. Fetch cluster's assigned node template constraints (if any)
     *    — uses min_vcpu/max_vcpu/min_memory/max_memory/architectures/allowed_families
     *    — falls back to broad defaults if no template assigned
     * 3. Use the actual instance type as the on-demand savings baseline
     * 4. Fetch pool rankings
     */
    const loadData = async () => {
        if (!clusterId) return;
        setLoading(true);

        let region = 'us-east-1';
        let primaryInstanceType = null;
        let primaryLifecycle = 'on-demand';
        let templateName = null;

        // ── Step 1: Cluster info ────────────────────────────────────────
        try {
            const clusterRes = await clusterAPI.getCluster(clusterId);
            region = clusterRes.data?.region || 'us-east-1';

            const nodesRes = await clusterAPI.getNodesDetailed(clusterId);
            const nodes = nodesRes.data?.nodes || [];

            // Prefer on-demand nodes as the current-cost baseline
            const onDemandNode = nodes.find(n => {
                const lc = (n.lifecycle || '').toLowerCase();
                return lc === 'on-demand' || lc === 'on_demand' || lc === 'ondemand';
            });
            const primaryNode = onDemandNode || nodes[0];

            if (primaryNode?.instance_type && primaryNode.instance_type !== 'unknown') {
                primaryInstanceType = primaryNode.instance_type;
                primaryLifecycle = primaryNode.lifecycle || 'on-demand';
            }
        } catch (err) {
            console.error('Failed to fetch cluster info for pool rankings:', err);
        }

        // ── Step 2: Build template from cluster's assigned node template ─
        // Start with the broad default, then override with the cluster's
        // actual node template constraints so vCPU/memory/family bounds are respected.
        let template = buildTemplate(primaryInstanceType);

        try {
            const mappingRes = await nodeTemplateAPI.getActiveMapping(clusterId);
            const c = mappingRes.data?.version?.constraints_json;
            if (c) {
                const base = buildTemplate(primaryInstanceType);
                templateName = mappingRes.data?.version?.name || null;
                template = {
                    // architectures field from schema: list of strings like ['amd64','arm64']
                    architecture: (c.architectures && c.architectures.length > 0)
                        ? c.architectures
                        : base.architecture,
                    // vCPU bounds from schema: min_vcpu / max_vcpu
                    vcpu_min: c.min_vcpu ?? base.vcpu_min,
                    vcpu_max: c.max_vcpu ?? base.vcpu_max,
                    // Memory bounds from schema: min_memory / max_memory (in GB)
                    memory_gb_min: c.min_memory ?? base.memory_gb_min,
                    memory_gb_max: c.max_memory ?? base.memory_gb_max,
                    // Family allowlist from schema: allowed_families (list of strings)
                    allowed_families: (c.allowed_families && c.allowed_families.length > 0)
                        ? c.allowed_families
                        : base.allowed_families,
                    allowed_sizes: base.allowed_sizes,
                    // Zone allowlist from schema: allowed_zones (optional)
                    allowed_azs: (c.allowed_zones && c.allowed_zones.length > 0)
                        ? c.allowed_zones
                        : null,
                    excluded_instance_types: c.excluded_instance_types || [],
                };
            }
        } catch (err) {
            // No active template assigned — fall back to broad defaults (already set above)
            console.debug('No active node template for cluster, using default filter:', err?.message);
        }

        setClusterInfo({ region, primaryInstanceType, primaryLifecycle, templateName });

        // ── Step 3: Savings baseline = actual current instance type ─────
        const currentNodeContext = {
            instance_type: primaryInstanceType || 'm5.large',
            lifecycle: 'on-demand',
        };

        // ── Step 4: Fetch rankings ──────────────────────────────────────
        try {
            const response = await atharvaaiAPI.getRankings(
                template,
                region,
                25,
                clusterId,
                currentNodeContext
            );

            const rankings = response.data.rankings || response.data.pools || response.data;
            const primaryInstancePrice = response.data.current_node_context?.price || null;

            const configResponse = await atharvaaiAPI.getEffectiveConfiguration(clusterId);
            setEffectiveConfig(configResponse.data);

            // Fetch Node-Specific Recommendations (Non-blocking)
            try {
                setNodeViewLoading(true);
                const nodeRes = await atharvaaiAPI.getNodeRecommendations(clusterId);
                const nodeData = nodeRes.data || {};
                // Backend now returns { recommendations: [...], eligible_pools_count: N }
                const recs = Array.isArray(nodeData) ? nodeData : (nodeData.recommendations || []);
                setNodeRecommendations(recs);
                setEligiblePoolsCount(nodeData.eligible_pools_count ?? recs.length);
            } catch (err) {
                console.debug('Node recommendations endpoint pending:', err.message);
                setNodeRecommendations([]);
                setEligiblePoolsCount(0);
            } finally {
                setNodeViewLoading(false);
            }

            // Fetch Cluster Impact Measurements (Non-blocking)
            try {
                setClusterViewLoading(true);
                const impactRes = await atharvaaiAPI.getClusterImpact(clusterId);
                setClusterImpact(impactRes.data || null);
            } catch (err) {
                console.debug('Cluster impact endpoint pending:', err.message);
                setClusterImpact(null);
            } finally {
                setClusterViewLoading(false);
            }

            setClusterInfo(prev => ({ ...prev, primaryInstancePrice }));
            setPools(Array.isArray(rankings) ? rankings : []);
            setError(null);
        } catch (err) {
            setError(err.response?.data?.detail || 'Failed to fetch pool rankings');
            console.error('Error fetching pool rankings:', err);
        } finally {
            setLoading(false);
        }
    };

    const fetchBlacklist = async () => {
        try {
            const response = await atharvaaiAPI.getBlacklist();
            setBlacklist(response.data);
        } catch (err) {
            console.error('Error fetching blacklist:', err);
        }
    };

    const handleRefresh = () => {
        loadData();
        fetchBlacklist();
    };

    const getSavingsColor = (savingsPct) => {
        if (savingsPct >= 0.60) return 'text-green-600';
        if (savingsPct >= 0.30) return 'text-yellow-600';
        return 'text-red-600';
    };

    const getInterruptionColor = (rank) => {
        if (rank === 0) return 'bg-green-100 text-green-800';
        if (rank === 1) return 'bg-blue-100 text-blue-800';
        if (rank === 2) return 'bg-yellow-100 text-yellow-800';
        if (rank === 3) return 'bg-orange-100 text-orange-800';
        return 'bg-red-100 text-red-800';
    };

    const getInterruptionLabel = (rank) => {
        const labels = { 0: '<5%', 1: '5-10%', 2: '10-15%', 3: '15-20%', 4: '>20%', 5: '>20%' };
        return labels[rank] || 'Unknown';
    };

    const getHealthBadge = (isFlagged) => {
        if (isFlagged) {
            return <span className="px-2 py-0.5 inline-flex text-xs font-semibold rounded-full bg-red-100 text-red-800">Unstable</span>;
        }
        return <span className="px-2 py-0.5 inline-flex text-xs font-semibold rounded-full bg-green-100 text-green-800">Healthy</span>;
    };

    // Build a human-readable baseline label for the legend
    const baselineLabel = clusterInfo.primaryInstanceType
        ? `${clusterInfo.primaryInstanceType} on-demand`
        : 'm5.large on-demand (fallback)';

    return (
        <div className="pool-rankings-container p-6">
            <div className="flex justify-between items-start mb-6">
                <div>
                    <h1 className="text-3xl font-bold text-gray-800">ASCP.ai Pool Rankings</h1>

                    <div className="flex items-center gap-4 mt-3 mb-2">
                        {effectiveConfig && effectiveConfig.optimization_strategy && (
                            <div className="inline-flex items-center bg-indigo-50 border border-indigo-100 rounded-md px-3 py-1.5 text-xs text-indigo-800 shadow-sm">
                                <span className="font-semibold mr-2 border-r border-indigo-200 pr-2">
                                    Active Strategy: {effectiveConfig.optimization_mode || 'BALANCED'}
                                </span>
                                <span className="mr-2 border-r border-indigo-200 pr-2">
                                    Risk Ceiling: {effectiveConfig.optimization_strategy.risk_ceiling_percent}%
                                </span>
                                <span>
                                    Min Savings: {effectiveConfig.optimization_strategy.min_savings_percent}%
                                </span>
                            </div>
                        )}
                    </div>

                    <p className="text-gray-600 mt-1 flex items-center">
                        ML-driven spot instance pool recommendations
                        {clusterInfo.region && (
                            <span className="ml-2 text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded">
                                {clusterInfo.region}
                            </span>
                        )}
                    </p>
                    <p className="text-sm text-gray-500 mt-1 flex items-center">
                        <FiInfo className="mr-1 text-indigo-500" />
                        Savings vs. <strong className="ml-1">{baselineLabel}</strong>
                        {clusterInfo.primaryInstanceType && (
                            <span className="ml-1 text-xs text-indigo-600">
                                (detected from cluster nodes)
                            </span>
                        )}
                    </p>
                    {clusterInfo.templateName && (
                        <p className="text-xs text-green-700 mt-1 flex items-center">
                            <FiLock className="mr-1" />
                            Filtered by node template: <strong className="ml-1">{clusterInfo.templateName}</strong>
                        </p>
                    )}
                </div>
                <div className="flex gap-3 items-center">
                    <button
                        onClick={handleRefresh}
                        disabled={loading}
                        className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
                    >
                        {loading ? 'Refreshing...' : 'Refresh'}
                    </button>
                    <label className="flex items-center">
                        <input
                            type="checkbox"
                            checked={autoRefresh}
                            onChange={(e) => setAutoRefresh(e.target.checked)}
                            className="mr-2"
                        />
                        <span className="text-sm text-gray-700">Auto-refresh (30s)</span>
                    </label>
                </div>
            </div>

            {/* TAB NAVIGATION */}
            <div className="border-b border-gray-200 mb-6">
                <nav className="-mb-px flex space-x-8">
                    <button
                        onClick={() => setActiveTab('market')}
                        className={`${activeTab === 'market' ? 'border-indigo-500 text-indigo-600' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'} whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm flex items-center`}
                    >
                        <FiGlobe className="mr-2" />
                        Market View
                    </button>
                    <button
                        onClick={() => setActiveTab('node')}
                        className={`${activeTab === 'node' ? 'border-indigo-500 text-indigo-600' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'} whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm flex items-center`}
                    >
                        <FiServer className="mr-2" />
                        Node-Specific View
                    </button>
                    <button
                        onClick={() => setActiveTab('cluster')}
                        className={`${activeTab === 'cluster' ? 'border-indigo-500 text-indigo-600' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'} whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm flex items-center`}
                    >
                        <FiPieChart className="mr-2" />
                        Cluster Impact View
                    </button>
                </nav>
            </div>

            {/* Execution Safety Banner (Mocked trigger) */}
            <div className="mb-6 p-4 bg-orange-50 border border-orange-200 rounded-lg flex items-center hidden">
                <FiAlertTriangle className="mr-3 text-orange-600 h-5 w-5" />
                <div>
                    <h3 className="text-sm font-semibold text-orange-800">Regional Spot Instability Detected – Conservative mode active.</h3>
                    <p className="text-xs text-orange-700 mt-0.5">Automated node substitutions will strictly favor high-availability pools temporarily.</p>
                </div>
            </div>

            {/* Global Blacklist Alert */}
            {blacklist.length > 0 && (
                <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg">
                    <h3 className="text-lg font-semibold text-red-800 mb-2 flex items-center">
                        <FiAlertTriangle className="mr-2" />
                        Globally Flagged Pools ({blacklist.length})
                    </h3>
                    <div className="flex flex-wrap gap-2">
                        {blacklist.map((item, idx) => (
                            <span key={idx} className="px-3 py-1 bg-red-100 text-red-800 rounded-full text-sm">
                                {item.instance_type}:{item.az}
                                <span className="text-xs ml-1">({Math.floor(item.ttl_remaining_seconds / 3600)}h left)</span>
                            </span>
                        ))}
                    </div>
                </div>
            )}

            {/* Error Alert */}
            {error && (
                <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg">
                    <p className="text-red-800">{error}</p>
                </div>
            )}

            {/* No cluster selected */}
            {!clusterId && (
                <div className="text-center py-12 text-gray-500">
                    <p className="text-lg font-medium">Select a cluster to view pool rankings</p>
                    <p className="text-sm mt-1">Choose a cluster from the dropdown above</p>
                </div>
            )}

            {/* Loading State */}
            {clusterId && loading && pools.length === 0 && (
                <div className="text-center py-12">
                    <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
                    <p className="mt-4 text-gray-600">Loading pool rankings...</p>
                </div>
            )}

            {/* Pool Rankings Table (Market View) */}
            {!loading && pools.length > 0 && activeTab === 'market' && (
                <div className="bg-white shadow-md rounded-lg overflow-x-auto">
                    <table className="w-full min-w-[800px] divide-y divide-gray-200 text-sm">
                        <thead className="bg-gray-50">
                            <tr>
                                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-14">Rank</th>
                                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Instance Type</th>
                                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">AZ</th>
                                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">vCPU / Mem</th>
                                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Spot Price</th>
                                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Interruption</th>
                                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">ML Score</th>
                                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Health</th>
                                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Blacklist</th>
                                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Signal</th>

                            </tr>
                        </thead>
                        <tbody className="bg-white divide-y divide-gray-200">
                            {pools.map((pool) => (
                                <tr
                                    key={`${pool.instance_type}-${pool.az}`}
                                    className={`hover:bg-gray-50 ${pool.is_flagged ? 'bg-red-50' : ''}`}
                                >
                                    <td className="px-4 py-3 whitespace-nowrap">
                                        <span className={`inline-flex items-center justify-center w-7 h-7 rounded-full text-sm ${pool.rank === 1 ? 'bg-yellow-100 text-yellow-800' :
                                            pool.rank <= 3 ? 'bg-green-100 text-green-800' :
                                                'bg-gray-100 text-gray-700'
                                            } font-bold`}>
                                            {pool.rank}
                                        </span>
                                    </td>
                                    <td className="px-4 py-3 whitespace-nowrap">
                                        <div className="font-medium text-gray-900 flex items-center gap-1">
                                            {pool.instance_type}
                                            {pool.is_flagged && (
                                                <FiAlertTriangle className="text-red-600" size={14} />
                                            )}
                                            <FiCheckCircle className="text-blue-500 ml-1" title="Capacity Validated" size={14} />
                                        </div>
                                        <div className="text-xs text-gray-400">{pool.architecture}</div>
                                    </td>
                                    <td className="px-4 py-3 whitespace-nowrap text-gray-700">{pool.az}</td>
                                    <td className="px-4 py-3 whitespace-nowrap text-gray-700">
                                        {pool.vcpu}c / {pool.memory_gb}GB
                                    </td>
                                    <td className="px-4 py-3 whitespace-nowrap">
                                        <div className="font-medium text-gray-900">${pool.spot_price.toFixed(4)}/hr</div>
                                        <div className="text-xs text-gray-400">OD: ${pool.ondemand_price.toFixed(4)}</div>
                                    </td>
                                    <td className="px-4 py-3 whitespace-nowrap">
                                        <span className={`px-2 py-0.5 inline-flex text-xs font-semibold rounded-full ${getInterruptionColor(pool.spot_advisor_rank)}`}>
                                            {getInterruptionLabel(pool.spot_advisor_rank)}
                                        </span>
                                    </td>
                                    <td className="px-4 py-3 whitespace-nowrap">
                                        <span className="text-base font-bold text-blue-600">{pool.ml_score.toFixed(3)}</span>
                                    </td>
                                    <td className="px-4 py-3 whitespace-nowrap">
                                        {getHealthBadge(pool.is_flagged)}
                                    </td>
                                    <td className="px-4 py-3 whitespace-nowrap">
                                        {pool.blacklisted ? (
                                            <span className="inline-flex items-center gap-1">
                                                <span className="w-2.5 h-2.5 rounded-full bg-red-500 inline-block"></span>
                                                <span className="text-xs text-red-600 font-semibold">Blacklisted</span>
                                            </span>
                                        ) : (
                                            <span className="text-xs text-gray-400">—</span>
                                        )}
                                    </td>
                                    <td className="px-4 py-3 whitespace-nowrap">
                                        {pool.price_shock ? (
                                            <span className="text-base" title="Price shock detected">&#9889;</span>
                                        ) : (
                                            <span className="text-xs text-gray-400">—</span>
                                        )}
                                    </td>

                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}

            {/* Empty State */}
            {!loading && pools.length === 0 && !error && clusterId && activeTab === 'market' && (
                <div className="text-center py-12 bg-white shadow-md rounded-lg">
                    <p className="text-gray-600">No pool rankings available. Adjust your filters and try again.</p>
                </div>
            )}

            {/* Node-Specific View */}
            {activeTab === 'node' && (
                <div className="space-y-6">
                    {/* Top Summary Cards — computed from nodeRecommendations */}
                    {(() => {
                        const totalNodes = nodeRecommendations.length;
                        const statelessNodes = nodeRecommendations.filter(r => r.workload_type === 'stateless').length;
                        const atRiskNodes = nodeRecommendations.filter(r => r.risk_score > 0.60).length;
                        // Projected monthly savings: hourly cost × savings% × 720 hours
                        const projSavings = nodeRecommendations
                            .reduce((sum, r) => sum + (r.current_cost || 0) * ((r.projected_savings_pct || 0) / 100) * 720, 0);
                        return (
                            <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
                                <div className="bg-white p-4 rounded-lg shadow-sm border border-gray-200">
                                    <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Total Nodes</h4>
                                    <p className="mt-2 text-2xl font-bold text-gray-900">
                                        {nodeViewLoading ? '\u2026' : totalNodes > 0 ? totalNodes : '0'}
                                    </p>
                                </div>
                                <div className="bg-white p-4 rounded-lg shadow-sm border border-gray-200">
                                    <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Stateless</h4>
                                    <p className="mt-2 text-2xl font-bold text-gray-900">
                                        {nodeViewLoading ? '\u2026' : statelessNodes}
                                    </p>
                                </div>
                                <div className="bg-white p-4 rounded-lg shadow-sm border border-gray-200">
                                    <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Total Pools</h4>
                                    <p className="mt-2 text-2xl font-bold text-indigo-600">
                                        {nodeViewLoading ? '\u2026' : eligiblePoolsCount}
                                    </p>
                                    <p className="text-xs text-gray-400 mt-1">after node filter</p>
                                </div>
                                <div className="bg-white p-4 rounded-lg shadow-sm border border-gray-200">
                                    <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">At Risk</h4>
                                    <p className="mt-2 text-2xl font-bold text-orange-500">
                                        {nodeViewLoading ? '\u2026' : atRiskNodes}
                                    </p>
                                    <p className="text-xs text-gray-400 mt-1">risk &gt; 60%</p>
                                </div>
                                <div className="bg-white p-4 rounded-lg shadow-sm border border-gray-200">
                                    <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Proj. Savings</h4>
                                    <p className="mt-2 text-2xl font-bold text-green-600">
                                        {nodeViewLoading ? '$\u2026' : projSavings > 0 ? `$${Math.round(projSavings)}/mo` : '$0/mo'}
                                    </p>
                                </div>
                            </div>
                        );
                    })()}

                    {/* Table */}
                    <div className="bg-white shadow-md rounded-lg overflow-x-auto">
                        <table className="w-full min-w-[900px] divide-y divide-gray-200 text-sm">
                            <thead className="bg-gray-50">
                                <tr>
                                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Node Name</th>
                                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Current Type</th>
                                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Current Cost</th>
                                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Target Pool</th>
                                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Proj. Savings</th>
                                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Risk Score</th>
                                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Interruption Rate</th>
                                </tr>
                            </thead>
                            <tbody className="bg-white divide-y divide-gray-200">
                                {nodeRecommendations && nodeRecommendations.length > 0 ? (
                                    nodeRecommendations.map((rec, idx) => (
                                        <tr key={idx} className="hover:bg-gray-50">
                                            <td className="px-4 py-3 font-medium text-gray-900">{rec.node_name}</td>
                                            <td className="px-4 py-3 text-gray-500">{rec.current_type}</td>
                                            <td className="px-4 py-3 text-gray-500">${rec.current_cost}/hr</td>
                                            <td className="px-4 py-3">
                                                <div className="font-medium text-gray-900">{rec.target_type}</div>
                                                <div className="text-xs text-gray-400">{rec.target_az}</div>
                                            </td>
                                            <td className="px-4 py-3 text-green-600 font-semibold">{rec.projected_savings_pct}%</td>
                                            <td className="px-4 py-3 text-blue-600 font-bold">{rec.risk_score}</td>
                                            <td className="px-4 py-3">
                                                <span className={`px-2 py-0.5 inline-flex text-xs font-semibold rounded-full ${rec.interruption_rate === '<5%' ? 'bg-green-100 text-green-800' :
                                                        rec.interruption_rate === '5–10%' ? 'bg-blue-100 text-blue-800' :
                                                            rec.interruption_rate === '10–15%' ? 'bg-yellow-100 text-yellow-800' :
                                                                rec.interruption_rate === '15–20%' ? 'bg-orange-100 text-orange-800' :
                                                                    'bg-red-100 text-red-800'
                                                    }`}>
                                                    {rec.interruption_rate || '—'}
                                                </span>
                                            </td>
                                        </tr>
                                    ))
                                ) : (
                                    <tr>
                                        <td colSpan="7" className="px-4 py-12 text-center text-gray-500">
                                            {nodeViewLoading ? (
                                                <div className="flex flex-col items-center">
                                                    <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600 mb-4"></div>
                                                    <p>Gathering node telemetry...</p>
                                                </div>
                                            ) : (
                                                <div className="flex flex-col items-center">
                                                    <FiServer className="h-10 w-10 text-gray-300 mb-3" />
                                                    <p>No actionable node recommendations available.</p>
                                                    <p className="text-xs text-gray-400 mt-1">Optimization API may be disabled or pending data.</p>
                                                </div>
                                            )}
                                        </td>
                                    </tr>
                                )}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}

            {/* Cluster Impact View */}
            {activeTab === 'cluster' && (
                <div className="space-y-6">
                    {/* Top Summary Cards — computed from nodeRecommendations (per-node hourly cost × 720) */}
                    {(() => {
                        const totalCurrentMonthly = nodeRecommendations.reduce(
                            (sum, r) => sum + (r.current_cost || 0) * 720, 0
                        );
                        const totalProjMonthly = nodeRecommendations.reduce((sum, r) => {
                            const savPct = r.status === 'ELIGIBLE' ? (r.projected_savings_pct || 0) : 0;
                            return sum + (r.current_cost || 0) * (1 - savPct / 100) * 720;
                        }, 0);
                        const savingsAmt = totalCurrentMonthly - totalProjMonthly;
                        const savingsPct = totalCurrentMonthly > 0
                            ? Math.round(savingsAmt / totalCurrentMonthly * 100) : 0;
                        const eligibleCount = nodeRecommendations.filter(r => r.status === 'ELIGIBLE').length;
                        // Spot Adoption: use real AWS-synced ratio from cluster impact API.
                        // Do NOT use eligible/total — that measures unmigrated nodes, not current spot state.
                        const spotAdoptionPct = clusterImpact?.spot_ratio != null
                            ? clusterImpact.spot_ratio
                            : (nodeRecommendations.length > 0 ? Math.round(nodeRecommendations.filter(r => r.status === 'SPOT').length / nodeRecommendations.length * 100) : 0);
                        const isLoading = clusterViewLoading || nodeViewLoading;
                        const alreadyOptimized = eligibleCount === 0 && spotAdoptionPct >= 100;
                        return (
                            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                                <div className="bg-white p-4 rounded-lg shadow-sm border border-gray-200">
                                    <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Current Cost</h4>
                                    <p className="mt-2 text-2xl font-bold text-gray-900">
                                        {isLoading ? '$…' : totalCurrentMonthly > 0 ? `$${Math.round(totalCurrentMonthly)}/mo` : '$0/mo'}
                                    </p>
                                </div>
                                <div className="bg-white p-4 rounded-lg shadow-sm border border-gray-200">
                                    <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Projected Cost</h4>
                                    <p className="mt-2 text-2xl font-bold text-green-600">
                                        {isLoading ? '$…' : totalProjMonthly > 0 ? `$${Math.round(totalProjMonthly)}/mo` : '$0/mo'}
                                    </p>
                                </div>
                                <div className="bg-white p-4 rounded-lg shadow-sm border border-gray-200">
                                    <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
                                        {alreadyOptimized ? 'Additional Savings' : 'Estimated Savings'}
                                    </h4>
                                    <p className="mt-2 text-2xl font-bold text-green-600">
                                        {isLoading ? '…%' : alreadyOptimized ? '✓ Fully Optimized' : `${savingsPct}%`}
                                    </p>
                                    {alreadyOptimized && !isLoading && (
                                        <p className="text-xs text-gray-400 mt-1">All nodes on spot</p>
                                    )}
                                </div>
                                <div className="bg-white p-4 rounded-lg shadow-sm border border-gray-200">
                                    <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Spot Adoption</h4>
                                    <p className="mt-2 text-2xl font-bold text-indigo-600">
                                        {isLoading ? '…%' : `${spotAdoptionPct}%`}
                                    </p>
                                    <p className="text-xs text-gray-400 mt-1">
                                        {clusterImpact ? `${clusterImpact.spot_count ?? 0} spot / ${clusterImpact.on_demand_count ?? 0} on-demand` : ''}
                                    </p>
                                </div>
                            </div>
                        );
                    })()}

                    {/* Chart Panels — driven by clusterImpact data */}
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                        {/* AZ Distribution */}
                        <div className="bg-white p-4 rounded-lg shadow-sm border border-gray-200 h-64 flex flex-col">
                            <h4 className="text-sm font-semibold text-gray-700 mb-3">AZ Distribution</h4>
                            {clusterImpact?.az_distribution?.length > 0 ? (
                                <div className="flex-1 flex flex-col justify-center gap-2 overflow-y-auto">
                                    {clusterImpact.az_distribution.map((item, i) => {
                                        const total = clusterImpact.total_nodes || 1;
                                        const pct = Math.round(item.count / total * 100);
                                        const colors = ['bg-indigo-500', 'bg-blue-400', 'bg-sky-400', 'bg-cyan-400'];
                                        return (
                                            <div key={i}>
                                                <div className="flex justify-between text-xs text-gray-600 mb-1">
                                                    <span className="font-mono">{item.az}</span>
                                                    <span className="font-semibold">{item.count} node{item.count !== 1 ? 's' : ''} ({pct}%)</span>
                                                </div>
                                                <div className="w-full bg-gray-100 rounded-full h-3">
                                                    <div className={`${colors[i % colors.length]} h-3 rounded-full transition-all`} style={{ width: `${pct}%` }} />
                                                </div>
                                            </div>
                                        );
                                    })}
                                </div>
                            ) : (
                                <div className="flex-1 flex items-center justify-center bg-gray-50 rounded border border-dashed border-gray-300">
                                    <span className="text-gray-400 text-sm">No data</span>
                                </div>
                            )}
                        </div>

                        {/* Instance Family Distribution */}
                        <div className="bg-white p-4 rounded-lg shadow-sm border border-gray-200 h-64 flex flex-col">
                            <h4 className="text-sm font-semibold text-gray-700 mb-3">Instance Family Distribution</h4>
                            {clusterImpact?.family_distribution?.length > 0 ? (
                                <div className="flex-1 flex flex-col justify-center gap-2 overflow-y-auto">
                                    {clusterImpact.family_distribution.map((item, i) => {
                                        const total = clusterImpact.total_nodes || 1;
                                        const pct = Math.round(item.count / total * 100);
                                        const colors = ['bg-purple-500', 'bg-violet-400', 'bg-fuchsia-400', 'bg-pink-400', 'bg-rose-400'];
                                        return (
                                            <div key={i}>
                                                <div className="flex justify-between text-xs text-gray-600 mb-1">
                                                    <span className="font-mono font-semibold">{item.family}.*</span>
                                                    <span>{item.count} node{item.count !== 1 ? 's' : ''} ({pct}%)</span>
                                                </div>
                                                <div className="w-full bg-gray-100 rounded-full h-3">
                                                    <div className={`${colors[i % colors.length]} h-3 rounded-full transition-all`} style={{ width: `${pct}%` }} />
                                                </div>
                                            </div>
                                        );
                                    })}
                                </div>
                            ) : (
                                <div className="flex-1 flex items-center justify-center bg-gray-50 rounded border border-dashed border-gray-300">
                                    <span className="text-gray-400 text-sm">No data</span>
                                </div>
                            )}
                        </div>

                        {/* Spot vs On-Demand Ratio */}
                        <div className="bg-white p-4 rounded-lg shadow-sm border border-gray-200 h-64 flex flex-col">
                            <h4 className="text-sm font-semibold text-gray-700 mb-3">Spot vs On-Demand Ratio</h4>
                            {clusterImpact?.total_nodes > 0 ? (() => {
                                const spotPct = clusterImpact.spot_ratio ?? 0;
                                const odPct = 100 - spotPct;
                                return (
                                    <div className="flex-1 flex flex-col justify-center gap-4">
                                        {/* Gauge arc approximation */}
                                        <div className="flex justify-center">
                                            <div className="relative w-32 h-16 overflow-hidden">
                                                <div className="absolute inset-0 rounded-t-full bg-gray-200" />
                                                <div
                                                    className="absolute inset-0 rounded-t-full bg-gradient-to-r from-green-400 to-green-600 origin-bottom"
                                                    style={{ transform: `rotate(${(spotPct / 100) * 180 - 90}deg)`, clipPath: 'polygon(50% 100%,0 0,100% 0)' }}
                                                />
                                                <div className="absolute inset-x-4 bottom-0 flex items-end justify-center pb-1">
                                                    <span className="text-2xl font-bold text-gray-900">{spotPct}%</span>
                                                </div>
                                            </div>
                                        </div>
                                        <div className="text-center text-xs text-gray-500 -mt-2">Spot Ratio</div>
                                        {/* Legend */}
                                        <div className="flex justify-center gap-6 text-sm">
                                            <div className="flex items-center gap-1.5">
                                                <div className="w-3 h-3 rounded-full bg-green-500" />
                                                <span className="text-gray-700">Spot <strong>{clusterImpact.spot_count}</strong></span>
                                            </div>
                                            <div className="flex items-center gap-1.5">
                                                <div className="w-3 h-3 rounded-full bg-blue-400" />
                                                <span className="text-gray-700">On-Demand <strong>{clusterImpact.on_demand_count}</strong></span>
                                            </div>
                                        </div>
                                        {/* Stacked bar */}
                                        <div className="flex h-4 rounded-full overflow-hidden mx-4">
                                            <div className="bg-green-500 transition-all" style={{ width: `${spotPct}%` }} />
                                            <div className="bg-blue-400 transition-all" style={{ width: `${odPct}%` }} />
                                        </div>
                                    </div>
                                );
                            })() : (
                                <div className="flex-1 flex items-center justify-center bg-gray-50 rounded border border-dashed border-gray-300">
                                    <span className="text-gray-400 text-sm">No data</span>
                                </div>
                            )}
                        </div>
                    </div>

                    {/* Table */}
                    <div className="bg-white shadow-md rounded-lg overflow-x-auto">
                        <table className="w-full min-w-[1000px] divide-y divide-gray-200 text-sm">
                            <thead className="bg-gray-50">
                                <tr>
                                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Target Pool</th>
                                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Eligible Nodes</th>
                                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Avg Savings</th>
                                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Total Savings</th>
                                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Avg Risk</th>
                                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Health</th>
                                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Cluster Usage</th>
                                </tr>
                            </thead>
                            <tbody className="bg-white divide-y divide-gray-200">
                                {clusterImpact && clusterImpact.pools && clusterImpact.pools.length > 0 ? (
                                    clusterImpact.pools.map((pool, idx) => (
                                        <tr key={idx} className="hover:bg-gray-50">
                                            <td className="px-4 py-3 font-medium text-gray-900">{pool.target_pool}</td>
                                            <td className="px-4 py-3 text-gray-500">{pool.eligible_nodes}</td>
                                            <td className="px-4 py-3 text-green-600 font-medium">${pool.avg_savings}/mo</td>
                                            <td className="px-4 py-3 text-green-600 font-bold">${pool.total_savings}/mo</td>
                                            <td className="px-4 py-3 text-blue-600">{pool.avg_risk}</td>
                                            <td className="px-4 py-3">{getHealthBadge(pool.is_flagged)}</td>
                                            <td className="px-4 py-3 text-gray-500">{pool.cluster_usage_pct}%</td>
                                        </tr>
                                    ))
                                ) : (
                                    <tr>
                                        <td colSpan="7" className="px-4 py-12 text-center text-gray-500">
                                            {clusterViewLoading ? (
                                                <div className="flex flex-col items-center">
                                                    <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600 mb-4"></div>
                                                    <p>Gathering cluster metrics...</p>
                                                </div>
                                            ) : (
                                                <div className="flex flex-col items-center">
                                                    <FiPieChart className="h-10 w-10 text-gray-300 mb-3" />
                                                    <p>No aggregated cluster impact data available.</p>
                                                    <p className="text-xs text-gray-400 mt-1">Optimization API may be disabled or pending data.</p>
                                                </div>
                                            )}
                                        </td>
                                    </tr>
                                )}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}

            {/* Legend - Only show on Market */}
            {activeTab === 'market' && (
                <div className="mt-6 p-4 bg-gray-50 rounded-lg border border-gray-200">
                    <h3 className="text-sm font-semibold text-gray-700 mb-2">Market Data Legend</h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 text-sm">
                        <div>
                            <span className="font-semibold text-gray-800">ML Score:</span> Market theoretical value
                        </div>
                        <div>
                            <span className="font-semibold text-gray-800">Interruption:</span> Spot Advisor frequency
                        </div>
                        <div className="flex items-center">
                            <FiCheckCircle className="text-blue-500 inline mr-1" />
                            <span className="font-semibold text-gray-800 mr-1">Validated:</span> Capacity confirmed
                        </div>
                    </div>
                    {clusterInfo.primaryInstanceType && (
                        <div className="mt-3 text-xs text-indigo-700 flex items-start">
                            <FiInfo className="mr-1 mt-0.5 shrink-0" />
                            <span>
                                Savings baseline: <strong>{clusterInfo.primaryInstanceType}</strong> ({clusterInfo.primaryLifecycle}) in <strong>{clusterInfo.region}</strong>. Rankings show best spot pools including same-family and Graviton alternatives.
                            </span>
                        </div>
                    )}
                    {clusterInfo.templateName && (
                        <div className="mt-1 text-xs text-green-700 flex items-center">
                            <FiLock className="mr-1 shrink-0" />
                            <span>
                                Active node template <strong>{clusterInfo.templateName}</strong> — vCPU, memory, architecture and family bounds enforced.
                            </span>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
};

export default PoolRankings;
