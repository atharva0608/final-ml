import React, { useState, useEffect } from 'react';
import { FiGlobe, FiServer, FiPieChart, FiInfo, FiLock, FiAlertTriangle, FiCheckCircle } from 'react-icons/fi';
import { ascpaiAPI, clusterAPI, nodeTemplateAPI } from '../../services/api';
import './PoolRankings.css';

/**
 * Derive instance family from full type string.
 * e.g. 't3.medium' -> 't3', 'm5.large' -> 'm5', 'c6g.xlarge' -> 'c6g'
 */
const getInstanceFamily = (instanceType) => {
    if (!instanceType) return null;
    const match = instanceType.match(/^([a-z]+\d*[a-z]*)/);
    return match ? match[1] : null;
};

const buildSavingsChartPaths = (pts) => {
    if (!pts || pts.length === 0) return { pathData: '', fillPathData: '' };
    const maxAmt = Math.max(...pts.map(p => p.amount), 1);
    const stepX = 100 / (pts.length > 1 ? (pts.length - 1) : 1);
    const pathData = pts.map((pt, i) => {
        const x = i * stepX;
        const y = 40 - (pt.amount / maxAmt * 35);
        return `${i === 0 ? 'M' : 'L'} ${x} ${y}`;
    }).join(' ');
    const fillPathData = pts.length > 1 ? `${pathData} L 100 40 L 0 40 Z` : '';
    return { pathData, fillPathData };
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
    const [autoRefresh, setAutoRefresh] = useState(true);
    const [nodeRecommendations, setNodeRecommendations] = useState([]);
    const [eligiblePoolsCount, setEligiblePoolsCount] = useState(0);
    const [familyDistribution, setFamilyDistribution] = useState({});
    const [diversifyEnabled, setDiversifyEnabled] = useState(false);
    const [clusterImpact, setClusterImpact] = useState(null);
    const [nodeViewLoading, setNodeViewLoading] = useState(false);
    const [clusterViewLoading, setClusterViewLoading] = useState(false);
    // Per-node coverage (changes.md Cluster Impact View)
    const [coverageData, setCoverageData] = useState(null);
    const [coverageLoading, setCoverageLoading] = useState(false);
    // Pool audit / funnel data (Task 4.3/4.4)
    const [poolAuditData, setPoolAuditData] = useState(null);
    // Market View — full pool list from cache_builder (not filtered by template)
    const [marketViewPools, setMarketViewPools] = useState([]);
    const [marketViewLoading, setMarketViewLoading] = useState(false);
    const [marketViewPage, setMarketViewPage] = useState(1);
    const [marketViewPageSize] = useState(20);
    const [marketViewTotal, setMarketViewTotal] = useState(0);
    const [marketViewTotalPages, setMarketViewTotalPages] = useState(1);
    const [marketViewTotalEvaluated, setMarketViewTotalEvaluated] = useState(0);
    const [marketViewGatesEliminated, setMarketViewGatesEliminated] = useState(0);
    const [marketViewSortBy, setMarketViewSortBy] = useState('final_score');
    const [marketViewSortOrder, setMarketViewSortOrder] = useState('desc');
    const [marketViewIsLive, setMarketViewIsLive] = useState(null);
    // Dry Run capacity states
    const [showUnavailablePools, setShowUnavailablePools] = useState(false);
    const [capacitySummary, setCapacitySummary] = useState(null);
    const [ttlCounters, setTtlCounters] = useState({});  // pool_key -> remaining seconds
    // Node-Specific View — selected node + alternatives
    const [selectedNodeId, setSelectedNodeId] = useState(null);
    const [nodeAlternatives, setNodeAlternatives] = useState(null);
    const [nodeAltLoading, setNodeAltLoading] = useState(false);
    const [nodeAltPage, setNodeAltPage] = useState(1);
    const [savingsVelocityData, setSavingsVelocityData] = useState(null);
    const [savingsVelocityLoading, setSavingsVelocityLoading] = useState(false);
    const [effectiveConfig, setEffectiveConfig] = useState(null);
    const [rebalancingActions, setRebalancingActions] = useState([]);
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

    // TTL countdown: tick every second for unavailable pools
    useEffect(() => {
        const hasUnavailable = Object.keys(ttlCounters).length > 0;
        if (!hasUnavailable) return;
        const tick = setInterval(() => {
            setTtlCounters(prev => {
                const updated = {};
                let anyLeft = false;
                Object.entries(prev).forEach(([key, secs]) => {
                    const newVal = Math.max(0, secs - 1);
                    updated[key] = newVal;
                    if (newVal > 0) anyLeft = true;
                });
                return anyLeft ? updated : {};
            });
        }, 1000);
        return () => clearInterval(tick);
    }, [ttlCounters]);

    // 5s polling when unverified pools exist in market view (capacity results arrive async)
    useEffect(() => {
        if (activeTab !== 'market' || !clusterId) return;
        const hasUnverified = marketViewPools.some(p => p.capacity_status === 'unverified');
        if (!hasUnverified) return;
        const poll = setInterval(() => {
            fetchMarketViewPage(marketViewPage, marketViewSortBy, marketViewSortOrder, showUnavailablePools);
        }, 5000);
        return () => clearInterval(poll);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [activeTab, clusterId, marketViewPools, marketViewPage, marketViewSortBy, marketViewSortOrder, showUnavailablePools]);

    // Fetch node alternatives + pool audit when selectedNodeId changes
    useEffect(() => {
        if (!clusterId || !selectedNodeId) return;
        setNodeAltLoading(true);
        setNodeAltPage(1);
        ascpaiAPI.getNodeAlternatives(clusterId, selectedNodeId, 1, 20)
            .then(res => setNodeAlternatives(res.data || null))
            .catch(err => { console.debug('Node alternatives error:', err.message); setNodeAlternatives(null); })
            .finally(() => setNodeAltLoading(false));
        // Fetch pool audit for funnel visualization (Task 4.3/4.4)
        ascpaiAPI.getPoolAudit(clusterId, selectedNodeId)
            .then(res => setPoolAuditData(res.data || null))
            .catch(() => setPoolAuditData(null));
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [clusterId, selectedNodeId]);

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
            const response = await ascpaiAPI.getRankings(
                template,
                region,
                25,
                clusterId,
                currentNodeContext
            );

            const rankings = response.data.rankings || response.data.pools || response.data;
            const primaryInstancePrice = response.data.current_node_context?.price || null;

            try {
                const configResponse = await ascpaiAPI.getEffectiveConfiguration(clusterId);
                setEffectiveConfig(configResponse.data);
            } catch (cfgErr) {
                console.debug('Effective configuration fetch failed (non-fatal):', cfgErr?.message);
            }

            // Fetch Node-Specific Recommendations (Non-blocking)
            try {
                setNodeViewLoading(true);
                const nodeRes = await ascpaiAPI.getNodeRecommendations(clusterId);
                const nodeData = nodeRes.data || {};
                // Backend now returns { recommendations: [...], eligible_pools_count: N }
                const recs = Array.isArray(nodeData) ? nodeData : (nodeData.recommendations || []);
                setNodeRecommendations(recs);
                setEligiblePoolsCount(nodeData.eligible_pools_count ?? recs.length);
                // Build distribution from recs grouped by lifecycle + instance_type
                // (ignore target AZ — we want "what types are running", not "what pools are targeted")
                const _distMap = {};
                recs.forEach(rec => {
                    const _lc = rec.lifecycle === 'spot' ? 'SPOT' : 'OD';
                    const _key = `${rec.current_type} (${_lc})`;
                    if (!_distMap[_key]) _distMap[_key] = { count: 0, pct: 0 };
                    _distMap[_key].count++;
                });
                const _distTotal = Object.values(_distMap).reduce((s, v) => s + v.count, 0);
                Object.keys(_distMap).forEach(k => {
                    _distMap[k].pct = _distTotal > 0 ? Math.round((_distMap[k].count / _distTotal) * 100) : 0;
                });
                setFamilyDistribution(_distMap);
                setDiversifyEnabled(nodeData.diversify_enabled || false);

                // Fetch live rebalancing actions to drive real STATUS column
                try {
                    const rebRes = await ascpaiAPI.getRebalancingStatus(clusterId, 20);
                    setRebalancingActions(Array.isArray(rebRes.data) ? rebRes.data : []);
                } catch (_rebErr) {
                    // non-fatal — status column falls back to lifecycle-based logic
                }
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
                const impactRes = await ascpaiAPI.getClusterImpact(clusterId);
                setClusterImpact(impactRes.data || null);
            } catch (err) {
                console.debug('Cluster impact endpoint pending:', err.message);
                setClusterImpact(null);
            } finally {
                setClusterViewLoading(false);
            }

            // Fetch Per-Node Coverage Report (changes.md Part 8)
            try {
                setCoverageLoading(true);
                const covRes = await ascpaiAPI.getClusterCoverage(clusterId);
                setCoverageData(covRes.data || null);
                // Pre-select first node if none selected
                const nodes = covRes.data?.per_node_summary || [];
                if (nodes.length > 0 && !selectedNodeId) {
                    setSelectedNodeId(nodes[0].node_id);
                }
            } catch (err) {
                console.debug('Coverage endpoint pending:', err.message);
                setCoverageData(null);
            } finally {
                setCoverageLoading(false);
            }

            // Fetch Savings Velocity (Non-blocking)
            try {
                setSavingsVelocityLoading(true);
                const svRes = await ascpaiAPI.getSavingsVelocity(clusterId, 30);
                setSavingsVelocityData(svRes.data || null);
            } catch (err) {
                console.debug('Savings velocity endpoint pending or failed:', err.message);
                setSavingsVelocityData(null);
            } finally {
                setSavingsVelocityLoading(false);
            }

            setClusterInfo(prev => ({ ...prev, primaryInstancePrice }));
            setPools(Array.isArray(rankings) ? rankings : []);
            setError(null);

            // ── Step 5: Fetch full Market View from cache_builder endpoint ──
            try {
                setMarketViewLoading(true);
                const mvRes = await ascpaiAPI.getMarketView(
                    clusterId, 1, marketViewPageSize, 'final_score', 'desc', showUnavailablePools
                );
                const mvData = mvRes.data || {};
                let mvPools = mvData.pools || [];
                // If market-view returned empty but getRankings had results, use rankings as fallback
                // (this happens on cold start before cache_builder has run)
                if (mvPools.length === 0 && Array.isArray(rankings) && rankings.length > 0) {
                    mvPools = rankings;
                }
                const pg = mvData.pagination || {};
                setMarketViewPools(mvPools);
                setMarketViewTotal(pg.total_valid_pools || mvPools.length);
                setMarketViewTotalPages(pg.total_pages || 1);
                setMarketViewTotalEvaluated(pg.total_evaluated || 0);
                setMarketViewGatesEliminated(pg.gates_eliminated || 0);
                setCapacitySummary(mvData.capacity_summary || null);
                setMarketViewPage(1);
                // Determine live/stale from first pool's data_age_minutes
                const firstAge = mvPools[0]?.data_age_minutes;
                setMarketViewIsLive(firstAge != null ? firstAge < 90 : null);

                // Seed TTL counters for unavailable pools
                const newTtl = {};
                mvPools.forEach(p => {
                    if (p.capacity_status === 'unavailable' && p.dry_run_ttl_remaining != null) {
                        newTtl[`${p.instance_type}:${p.az}`] = p.dry_run_ttl_remaining;
                    }
                });
                if (Object.keys(newTtl).length > 0) setTtlCounters(prev => ({ ...prev, ...newTtl }));

                // Trigger dry run check for top 20 unverified pools
                const unverifiedKeys = mvPools
                    .filter(p => p.capacity_status === 'unverified')
                    .slice(0, 20)
                    .map(p => `${p.instance_type}:${p.az}`);
                if (unverifiedKeys.length > 0) {
                    ascpaiAPI.triggerDryRunCheck(clusterId, unverifiedKeys).catch(() => {});
                }
            } catch (mvErr) {
                console.debug('Market view endpoint not yet available:', mvErr.message);
                setMarketViewPools(Array.isArray(rankings) ? rankings : []);
                setMarketViewTotal(Array.isArray(rankings) ? rankings.length : 0);
                setMarketViewTotalPages(1);
                setMarketViewIsLive(null);
            } finally {
                setMarketViewLoading(false);
            }
        } catch (err) {
            setError(err.response?.data?.detail || 'Failed to fetch pool rankings');
            console.error('Error fetching pool rankings:', err);
        } finally {
            setLoading(false);
        }
    };

    const fetchMarketViewPage = async (page, sortBy = marketViewSortBy, sortOrder = marketViewSortOrder, includeUnavailable = showUnavailablePools) => {
        if (!clusterId) return;
        try {
            setMarketViewLoading(true);
            const mvRes = await ascpaiAPI.getMarketView(
                clusterId, page, marketViewPageSize, sortBy, sortOrder, includeUnavailable
            );
            const mvData = mvRes.data || {};
            const mvPools = mvData.pools || [];
            const pg = mvData.pagination || {};
            setMarketViewPools(mvPools);
            setMarketViewPage(page);
            setMarketViewTotal(pg.total_valid_pools || mvPools.length);
            setMarketViewTotalPages(pg.total_pages || 1);
            setMarketViewTotalEvaluated(pg.total_evaluated || 0);
            setMarketViewGatesEliminated(pg.gates_eliminated || 0);
            setCapacitySummary(mvData.capacity_summary || null);
            const firstAge = mvPools[0]?.data_age_minutes;
            setMarketViewIsLive(firstAge != null ? firstAge < 90 : null);

            // Seed TTL counters for unavailable pools
            const newTtl = {};
            mvPools.forEach(p => {
                if (p.capacity_status === 'unavailable' && p.dry_run_ttl_remaining != null) {
                    newTtl[`${p.instance_type}:${p.az}`] = p.dry_run_ttl_remaining;
                }
            });
            if (Object.keys(newTtl).length > 0) setTtlCounters(prev => ({ ...prev, ...newTtl }));

            // Trigger background dry run check for top 20 unverified pools
            const unverifiedKeys = mvPools
                .filter(p => p.capacity_status === 'unverified')
                .slice(0, 20)
                .map(p => `${p.instance_type}:${p.az}`);
            if (unverifiedKeys.length > 0) {
                ascpaiAPI.triggerDryRunCheck(clusterId, unverifiedKeys).catch(() => {});
            }
        } catch (err) {
            console.error('Market view page fetch error:', err);
        } finally {
            setMarketViewLoading(false);
        }
    };

    const handleMarketViewSort = (col) => {
        const newOrder = marketViewSortBy === col && marketViewSortOrder === 'desc' ? 'asc' : 'desc';
        setMarketViewSortBy(col);
        setMarketViewSortOrder(newOrder);
        fetchMarketViewPage(1, col, newOrder);
    };

    const fetchBlacklist = async () => {
        try {
            const response = await ascpaiAPI.getBlacklist();
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
                        {marketViewTotal > 0 && (
                            <span className="ml-2 inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-indigo-100 text-indigo-700">
                                {marketViewTotal}
                            </span>
                        )}
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
            {!loading && activeTab === 'market' && (
                <>
                    {/* Live/Stale indicator + stats bar */}
                    <div className="flex items-center justify-between mb-2 px-1">
                        <div className="flex items-center gap-4 text-xs text-gray-500">
                            {marketViewTotalEvaluated > 0 && (
                                <span>{marketViewTotalEvaluated.toLocaleString()} evaluated · {marketViewGatesEliminated.toLocaleString()} eliminated · <span className="font-semibold text-gray-700">{marketViewTotal.toLocaleString()} valid</span></span>
                            )}
                            {capacitySummary && (
                                <span className="flex items-center gap-2 ml-2">
                                    {(capacitySummary.verified ?? 0) > 0 && <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-green-500 inline-block"></span>{capacitySummary.verified} verified</span>}
                                    {(capacitySummary.unverified ?? 0) > 0 && <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-gray-400 inline-block"></span>{capacitySummary.unverified} unverified</span>}
                                    {(capacitySummary.unavailable ?? 0) > 0 && <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-red-400 inline-block"></span>{capacitySummary.unavailable} unavailable</span>}
                                </span>
                            )}
                        </div>
                        <div className="flex items-center gap-3">
                            <label className="flex items-center gap-1.5 text-xs text-gray-500 cursor-pointer select-none">
                                <input
                                    type="checkbox"
                                    checked={showUnavailablePools}
                                    onChange={e => {
                                        setShowUnavailablePools(e.target.checked);
                                        fetchMarketViewPage(1, marketViewSortBy, marketViewSortOrder, e.target.checked);
                                    }}
                                    className="rounded border-gray-300 text-blue-600"
                                />
                                Show unavailable pools
                            </label>
                            {marketViewIsLive === true && (
                                <span className="flex items-center gap-1 text-xs text-green-600 font-medium">
                                    <span className="w-2 h-2 rounded-full bg-green-500 inline-block animate-pulse"></span> Live
                                </span>
                            )}
                            {marketViewIsLive === false && (
                                <span className="flex items-center gap-1 text-xs text-yellow-600 font-medium">
                                    <span className="w-2 h-2 rounded-full bg-yellow-500 inline-block"></span> Stale
                                </span>
                            )}
                            {marketViewLoading && <span className="text-xs text-gray-400">Loading…</span>}
                        </div>
                    </div>

                    {!marketViewLoading && marketViewPools.length > 0 && (
                        <div className="bg-white shadow-md rounded-lg overflow-x-auto">
                            <table className="w-full min-w-[900px] divide-y divide-gray-200 text-sm">
                                <thead className="bg-gray-50">
                                    <tr>
                                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-14">Rank</th>
                                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:text-gray-700" onClick={() => handleMarketViewSort('instance_type')}>Instance Type</th>
                                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">AZ</th>
                                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">vCPU / Mem</th>
                                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:text-gray-700" onClick={() => handleMarketViewSort('spot_price')}>Spot Price</th>
                                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:text-gray-700" onClick={() => handleMarketViewSort('intrinsic_savings_pct')} title="How good is this pool in the spot market">Pool Saving</th>
                                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:text-gray-700" onClick={() => handleMarketViewSort('customer_savings_pct')} title="What you actually save vs current OD price">Your Saving</th>
                                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:text-gray-700" onClick={() => handleMarketViewSort('interruption_rate_pct')}>Interruption</th>
                                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:text-gray-700" onClick={() => handleMarketViewSort('ml_score_final')}>ML</th>
                                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:text-gray-700" onClick={() => handleMarketViewSort('final_score')}>Score</th>
                                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider" title="AWS real-time capacity check result">Capacity</th>
                                    </tr>
                                </thead>
                                <tbody className="bg-white divide-y divide-gray-200">
                                    {marketViewPools.map((pool) => {
                                        const spotPrice = pool.spot_price ?? pool.spot_price_hr ?? 0;
                                        const odPrice = pool.od_price ?? pool.ondemand_price ?? pool.od_price_hr ?? 0;
                                        const intrinsicPct = pool.intrinsic_savings_pct ?? (odPrice > 0 ? ((odPrice - spotPrice) / odPrice * 100) : 0);
                                        const customerPct = pool.customer_savings_pct ?? intrinsicPct;
                                        const mlTier = pool.ml_tier ?? 3;
                                        const mlTierLabel = mlTier === 1 ? 'T1' : mlTier === 2 ? 'T2' : 'T3';
                                        const mlTierColor = mlTier === 1 ? 'bg-green-100 text-green-700' : mlTier === 2 ? 'bg-blue-100 text-blue-700' : 'bg-gray-100 text-gray-500';
                                        const irrRate = pool.interruption_rate_pct ?? pool.interruption_rate ?? pool.az_interruption_rate ?? null;
                                        const irrLabel = irrRate != null ? `${irrRate}%` : getInterruptionLabel(pool.spot_advisor_rank ?? 0);
                                        const irrColor = irrRate != null
                                            ? (irrRate <= 5 ? 'bg-green-100 text-green-800' : irrRate <= 10 ? 'bg-yellow-100 text-yellow-800' : irrRate <= 15 ? 'bg-orange-100 text-orange-800' : 'bg-red-100 text-red-800')
                                            : getInterruptionColor(pool.spot_advisor_rank ?? 0);
                                        const poolKey = `${pool.instance_type}:${pool.az}`;
                                        const capStatus = pool.capacity_status || 'unverified';
                                        const ttlLeft = ttlCounters[poolKey];
                                        const ttlStr = ttlLeft != null && ttlLeft > 0
                                            ? `${Math.floor(ttlLeft / 60)}:${String(ttlLeft % 60).padStart(2, '0')}`
                                            : null;
                                        return (
                                            <tr
                                                key={`${pool.instance_type}-${pool.az}-${pool.rank}`}
                                                className={`hover:bg-gray-50 ${pool.is_flagged ? 'bg-red-50' : ''} ${capStatus === 'unavailable' ? 'opacity-60' : ''}`}
                                            >
                                                <td className="px-4 py-3 whitespace-nowrap">
                                                    <span className={`inline-flex items-center justify-center w-7 h-7 rounded-full text-sm ${pool.rank === 1 ? 'bg-yellow-100 text-yellow-800' : pool.rank <= 3 ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-700'} font-bold`}>
                                                        {pool.rank}
                                                    </span>
                                                </td>
                                                <td className="px-4 py-3 whitespace-nowrap">
                                                    <div className="font-medium text-gray-900 flex items-center gap-1">
                                                        {pool.instance_type}
                                                        {pool.soft_penalty_applied && (
                                                            <span className="ml-1 text-orange-500 text-xs" title="Recent launch failures — soft penalty applied">⚠</span>
                                                        )}
                                                        {pool.blacklisted && (
                                                            <span className="ml-1 w-2 h-2 rounded-full bg-red-500 inline-block" title="Blacklisted"></span>
                                                        )}
                                                    </div>
                                                    <div className="text-xs text-gray-400">{pool.architecture}</div>
                                                </td>
                                                <td className="px-4 py-3 whitespace-nowrap text-gray-700">{pool.az}</td>
                                                <td className="px-4 py-3 whitespace-nowrap text-gray-700">
                                                    {pool.vcpu}c / {pool.memory_gb}GB
                                                </td>
                                                <td className="px-4 py-3 whitespace-nowrap">
                                                    <div className="font-medium text-gray-900">${(spotPrice || 0).toFixed(4)}/hr</div>
                                                    <div className="text-xs text-gray-400">OD: ${(odPrice || 0).toFixed(4)}</div>
                                                </td>
                                                <td className="px-4 py-3 whitespace-nowrap">
                                                    <span className="font-semibold text-emerald-600">{intrinsicPct.toFixed(1)}%</span>
                                                    <div className="text-xs text-gray-400">pool quality</div>
                                                </td>
                                                <td className="px-4 py-3 whitespace-nowrap">
                                                    <span className="font-semibold text-blue-600">{customerPct.toFixed(1)}%</span>
                                                    <div className="text-xs text-gray-400">vs your OD</div>
                                                </td>
                                                <td className="px-4 py-3 whitespace-nowrap">
                                                    <span className={`px-2 py-0.5 inline-flex text-xs font-semibold rounded-full ${irrColor}`}>
                                                        {irrLabel}
                                                    </span>
                                                </td>
                                                <td className="px-4 py-3 whitespace-nowrap">
                                                    <div className="flex items-center gap-1.5">
                                                        <span className="text-sm font-bold text-blue-600">{(pool.ml_score_final ?? pool.ml_score ?? 0).toFixed(2)}</span>
                                                        <span className={`px-1 py-0.5 rounded text-xs font-semibold ${mlTierColor}`}>{mlTierLabel}</span>
                                                    </div>
                                                </td>
                                                <td className="px-4 py-3 whitespace-nowrap">
                                                    <span className="text-sm font-bold text-gray-800">{(pool.final_score ?? 0).toFixed(3)}</span>
                                                    {pool.data_age_minutes != null && (
                                                        <div className="text-xs text-gray-400">{pool.data_age_minutes.toFixed(0)}m old</div>
                                                    )}
                                                </td>
                                                <td className="px-4 py-3 whitespace-nowrap">
                                                    {capStatus === 'verified' && (
                                                        <span className="flex items-center gap-1 text-xs text-green-700 font-medium">
                                                            <span className="w-2 h-2 rounded-full bg-green-500 inline-block"></span>Verified
                                                        </span>
                                                    )}
                                                    {capStatus === 'unverified' && (
                                                        <span className="flex items-center gap-1 text-xs text-gray-500">
                                                            <span className="w-2 h-2 rounded-full bg-gray-400 inline-block animate-pulse"></span>Checking…
                                                        </span>
                                                    )}
                                                    {capStatus === 'unavailable' && (
                                                        <span className="flex items-center gap-1 text-xs text-red-600 font-medium">
                                                            <span className="w-2 h-2 rounded-full bg-red-500 inline-block"></span>
                                                            <span>
                                                                Unavailable
                                                                {ttlStr && <div className="text-xs text-gray-400 font-normal">Recheck in {ttlStr}</div>}
                                                            </span>
                                                        </span>
                                                    )}
                                                </td>
                                            </tr>
                                        );
                                    })}
                                </tbody>
                            </table>
                        </div>
                    )}

                    {/* Pagination controls */}
                    {marketViewTotalPages > 1 && (
                        <div className="flex items-center justify-center gap-2 mt-3">
                            <button
                                onClick={() => fetchMarketViewPage(marketViewPage - 1)}
                                disabled={marketViewPage <= 1 || marketViewLoading}
                                className="px-3 py-1 text-sm rounded border border-gray-300 hover:bg-gray-50 disabled:opacity-40"
                            >
                                ←
                            </button>
                            {Array.from({ length: Math.min(7, marketViewTotalPages) }, (_, i) => {
                                const p = i + 1;
                                return (
                                    <button
                                        key={p}
                                        onClick={() => fetchMarketViewPage(p)}
                                        disabled={marketViewLoading}
                                        className={`px-3 py-1 text-sm rounded border ${marketViewPage === p ? 'bg-blue-600 text-white border-blue-600' : 'border-gray-300 hover:bg-gray-50'}`}
                                    >
                                        {p}
                                    </button>
                                );
                            })}
                            {marketViewTotalPages > 7 && <span className="text-gray-400">…</span>}
                            {marketViewTotalPages > 7 && (
                                <button
                                    onClick={() => fetchMarketViewPage(marketViewTotalPages)}
                                    disabled={marketViewLoading}
                                    className={`px-3 py-1 text-sm rounded border ${marketViewPage === marketViewTotalPages ? 'bg-blue-600 text-white border-blue-600' : 'border-gray-300 hover:bg-gray-50'}`}
                                >
                                    {marketViewTotalPages}
                                </button>
                            )}
                            <button
                                onClick={() => fetchMarketViewPage(marketViewPage + 1)}
                                disabled={marketViewPage >= marketViewTotalPages || marketViewLoading}
                                className="px-3 py-1 text-sm rounded border border-gray-300 hover:bg-gray-50 disabled:opacity-40"
                            >
                                →
                            </button>
                            <span className="text-xs text-gray-500 ml-2">
                                Page {marketViewPage} of {marketViewTotalPages} ({marketViewTotal} pools)
                            </span>
                        </div>
                    )}
                </>
            )}

            {/* Empty State */}
            {!loading && !marketViewLoading && marketViewPools.length === 0 && !error && clusterId && activeTab === 'market' && (
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
                        const projSavings = nodeRecommendations
                            .reduce((sum, r) => sum + (r.current_cost || 0) * ((r.projected_savings_pct || 0) / 100) * 720, 0);
                        const spotNodes = nodeRecommendations.filter(r => r.lifecycle === 'spot').length;
                        const s2sCandidates = nodeRecommendations.filter(r => r.s2s_candidate).length;
                        // Compute projected savings including OD→Spot fallback estimate
                        // For OD nodes where backend returns 0% savings (same-type spot move),
                        // estimate ~65% spot discount as a floor so the savings column is never blank.
                        const estimatedProjSavings = nodeRecommendations.reduce((sum, r) => {
                            if ((r.projected_savings_pct || 0) > 0) {
                                return sum + (r.current_cost || 0) * (r.projected_savings_pct / 100) * 720;
                            }
                            if ((r.lifecycle || '').toLowerCase().includes('demand')) {
                                // On-demand → spot: use 65% discount estimate
                                return sum + (r.current_cost || 0) * 0.65 * 720;
                            }
                            return sum;
                        }, 0);

                        return (
                            <div>
                                {/* ── Top summary row ── */}
                                <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 mb-6">
                                    {/* Savings Velocity */}
                                    <div className="bg-white p-4 rounded-lg shadow-sm border border-gray-200 col-span-2 sm:col-span-3 lg:col-span-2 relative overflow-hidden">
                                        <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Savings Velocity (Last 30 Days)</h4>
                                        <p className="mt-1 text-2xl font-bold text-green-600">
                                            {savingsVelocityLoading ? '…' : (savingsVelocityData?.last_30_days_total > 0 ? `$${savingsVelocityData.last_30_days_total}` : `$${Math.round(estimatedProjSavings)}`)}
                                        </p>
                                        <p className="text-xs text-gray-400 mt-0.5">
                                            {savingsVelocityData?.last_30_days_total > 0 ? 'Realized savings' : 'Projected monthly'}
                                        </p>
                                        {savingsVelocityData?.data_points?.length > 0 && (
                                            <div className="absolute -bottom-2 -right-2 -left-2 h-16 opacity-30 pointer-events-none">
                                                <svg viewBox="0 0 100 40" preserveAspectRatio="none" className="w-full h-full">
                                                    <defs>
                                                        <linearGradient id="gradSV" x1="0" x2="0" y1="0" y2="1">
                                                            <stop offset="0%" stopColor="#10b981" stopOpacity="0.8" />
                                                            <stop offset="100%" stopColor="#10b981" stopOpacity="0" />
                                                        </linearGradient>
                                                    </defs>
                                                    {buildSavingsChartPaths(savingsVelocityData.data_points).pathData && (
                                                        <g>
                                                            <path d={buildSavingsChartPaths(savingsVelocityData.data_points).fillPathData} fill="url(#gradSV)" />
                                                            <path d={buildSavingsChartPaths(savingsVelocityData.data_points).pathData} fill="none" stroke="#10b981" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                                                        </g>
                                                    )}
                                                </svg>
                                            </div>
                                        )}
                                    </div>
                                    {/* Total Nodes */}
                                    <div className="bg-white p-4 rounded-lg shadow-sm border border-gray-200 text-center">
                                        <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Total Nodes</h4>
                                        <p className="mt-2 text-2xl font-bold text-gray-900">{nodeViewLoading ? '…' : totalNodes}</p>
                                        {!nodeViewLoading && spotNodes > 0 && <p className="text-xs text-green-600 mt-0.5 font-medium">{spotNodes} spot</p>}
                                    </div>
                                    {/* Eligible Pools */}
                                    <div className="bg-white p-4 rounded-lg shadow-sm border border-gray-200 text-center">
                                        <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Eligible Pools</h4>
                                        <p className="mt-2 text-2xl font-bold text-indigo-600">{nodeViewLoading ? '…' : eligiblePoolsCount}</p>
                                        <p className="text-xs text-gray-400 mt-0.5">after filter</p>
                                    </div>
                                    {/* At Risk */}
                                    <div className="bg-white p-4 rounded-lg shadow-sm border border-gray-200 text-center">
                                        <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">At Risk</h4>
                                        <p className={`mt-2 text-2xl font-bold ${atRiskNodes > 0 ? 'text-orange-500' : 'text-gray-400'}`}>{nodeViewLoading ? '…' : atRiskNodes}</p>
                                        <p className="text-xs text-gray-400 mt-0.5">risk &gt; 60%</p>
                                    </div>
                                    {/* Proj. Savings */}
                                    <div className="bg-white p-4 rounded-lg shadow-sm border border-gray-200 text-center">
                                        <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Proj. Savings</h4>
                                        <p className="mt-2 text-2xl font-bold text-green-600">
                                            {nodeViewLoading ? '$…' : estimatedProjSavings > 0 ? `$${Math.round(estimatedProjSavings)}/mo` : '$0/mo'}
                                        </p>
                                        <p className="text-xs text-gray-400 mt-0.5">{s2sCandidates > 0 ? `${s2sCandidates} S2S ready` : 'all optimal'}</p>
                                    </div>
                                </div>
                            </div>
                        );
                    })()}

                    {/* Savings Velocity — real data chart */}
                    <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 mb-6 mt-4">
                        <div className="flex justify-between items-center mb-4">
                            <h4 className="text-[14px] font-extrabold text-slate-800">Savings Velocity (Last 30 Days)</h4>
                            {savingsVelocityData?.last_30_days_total > 0 && (
                                <div className="bg-green-50 text-green-700 px-3 py-1 rounded text-[11px] font-bold border border-green-100">
                                    Total: ${savingsVelocityData.last_30_days_total} saved
                                </div>
                            )}
                        </div>
                        {savingsVelocityLoading ? (
                            <div className="h-40 flex items-center justify-center text-slate-400 text-sm">Loading...</div>
                        ) : savingsVelocityData?.data_points?.length > 0 ? (
                            <div className="relative h-40 w-full">
                                <svg className="w-full h-full" viewBox="0 0 1000 160" preserveAspectRatio="none">
                                    <defs>
                                        <linearGradient id="svFill" x1="0" x2="0" y1="0" y2="1">
                                            <stop offset="0%" stopColor="#3b82f6" stopOpacity="0.15" />
                                            <stop offset="100%" stopColor="#3b82f6" stopOpacity="0" />
                                        </linearGradient>
                                    </defs>
                                    {(() => {
                                        const pts = savingsVelocityData.data_points;
                                        const maxAmt = Math.max(...pts.map(p => p.amount), 1);
                                        const step = 1000 / (pts.length > 1 ? pts.length - 1 : 1);
                                        const coords = pts.map((p, i) => ({
                                            x: i * step,
                                            y: 140 - (p.amount / maxAmt) * 120,
                                            label: p.date ? new Date(p.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : '',
                                            amount: p.amount,
                                        }));
                                        const line = coords.map((c, i) => `${i === 0 ? 'M' : 'L'} ${c.x} ${c.y}`).join(' ');
                                        const fill = `${line} L 1000 140 L 0 140 Z`;
                                        return (
                                            <g>
                                                <path d={fill} fill="url(#svFill)" />
                                                <path d={line} fill="none" stroke="#3b82f6" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
                                                {coords.map((c, i) => (
                                                    <circle key={i} cx={c.x} cy={c.y} r="3.5" fill="#3b82f6" />
                                                ))}
                                            </g>
                                        );
                                    })()}
                                </svg>
                                <div className="absolute bottom-0 left-0 w-full flex justify-between text-[10px] font-bold text-slate-400 border-t border-slate-100 pt-2">
                                    {(() => {
                                        const pts = savingsVelocityData.data_points;
                                        const step = Math.max(1, Math.floor(pts.length / 5));
                                        return [0, step, step*2, step*3, pts.length-1].map((i, k) => {
                                            const p = pts[Math.min(i, pts.length-1)];
                                            return <span key={k}>{p?.date ? new Date(p.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }).toUpperCase() : ''}</span>;
                                        });
                                    })()}
                                </div>
                            </div>
                        ) : (
                            <div className="h-40 flex flex-col items-center justify-center text-slate-400">
                                <svg className="w-10 h-10 mb-2 text-slate-300" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" /></svg>
                                <p className="text-sm font-medium">No realized savings data yet</p>
                                <p className="text-xs mt-1 text-slate-300">Data accumulates as rebalancing completes</p>
                            </div>
                        )}
                    </div>

                    {/* Instance Pool Distribution */}
                    {!nodeViewLoading && Object.keys(familyDistribution).length > 0 && (
                        <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm mb-6">
                            <div className="flex items-center justify-between mb-4">
                                <h4 className="text-[11px] font-extrabold text-slate-400 uppercase tracking-widest">Instance Pool Distribution</h4>
                                {diversifyEnabled && (
                                    <span className="text-[10px] font-bold text-indigo-600 bg-indigo-50 border border-indigo-200 px-2 py-0.5 rounded-full">
                                        Diversify ON — 1 node max per pool
                                    </span>
                                )}
                            </div>
                            <div className="h-20 w-full flex rounded-lg overflow-hidden mb-4">
                                {(() => {
                                    const entries = Object.entries(familyDistribution).sort((a,b) => b[1].count - a[1].count);
                                    const colors = ['#3b82f6','#22c55e','#f59e0b','#a855f7','#06b6d4','#f97316','#10b981','#a855f7'];
                                    return entries.map(([label, info], idx) => {
                                        // label is "t3.medium (OD)" or "t3.medium (SPOT)"
                                        const isSpotLabel = label.includes('(SPOT)');
                                        const bg = isSpotLabel ? '#22c55e' : colors[idx % colors.length];
                                        return (
                                            <div
                                                key={label}
                                                className="flex flex-col justify-center px-4 border-r border-white/20 last:border-0 transition-all"
                                                style={{ width: `${info.pct}%`, backgroundColor: bg }}
                                            >
                                                <div className="text-[12px] font-extrabold text-white truncate">{label}</div>
                                                <div className="text-[10px] font-bold text-white mt-0.5">{info.count} node{info.count !== 1 ? 's' : ''} · {info.pct}%</div>
                                            </div>
                                        );
                                    });
                                })()}
                            </div>
                            {/* Legend */}
                            <div className="flex flex-wrap gap-2">
                                {Object.entries(familyDistribution).sort((a,b) => b[1].count - a[1].count).map(([label, info], idx) => {
                                    const colors = ['#3b82f6','#22c55e','#f59e0b','#a855f7','#06b6d4','#f97316','#10b981','#a855f7'];
                                    const isSpotLabel = label.includes('(SPOT)');
                                    const color = isSpotLabel ? '#22c55e' : colors[idx % colors.length];
                                    return (
                                        <span key={label} className="flex items-center gap-1 text-[11px] text-slate-600">
                                            <span className="w-2.5 h-2.5 rounded-sm inline-block shrink-0" style={{ backgroundColor: color }} />
                                            {label}
                                            <span className="text-slate-400">({info.count} node{info.count !== 1 ? 's' : ''})</span>
                                        </span>
                                    );
                                })}
                            </div>
                        </div>
                    )}

                    {/* Table */}
                    <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
                        <table className="w-full text-left">
                            <thead className="bg-white border-b border-slate-100">
                                <tr>
                                    <th className="px-6 py-5 text-[10px] font-bold text-slate-400 uppercase tracking-widest">Node</th>
                                    <th className="px-6 py-5 text-[10px] font-bold text-slate-400 uppercase tracking-widest">Current Type</th>
                                    <th className="px-6 py-5 text-[10px] font-bold text-slate-400 uppercase tracking-widest">Target Pool</th>
                                    <th className="px-6 py-5 text-[10px] font-bold text-slate-400 uppercase tracking-widest">Status</th>
                                    <th className="px-6 py-5 text-[10px] font-bold text-slate-400 uppercase tracking-widest">Cost/Hr</th>
                                    <th className="px-6 py-5 text-[10px] font-bold text-slate-400 uppercase tracking-widest text-center">Cost Trend</th>
                                    <th className="px-6 py-5 text-[10px] font-bold text-slate-400 uppercase tracking-widest">Action</th>
                                    <th className="px-6 py-5 text-[10px] font-bold text-slate-400 uppercase tracking-widest text-right">Savings</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-100">
                                {nodeRecommendations && nodeRecommendations.length > 0 ? (
                                    nodeRecommendations.map((rec, idx) => {
                                        const isSpot = rec.lifecycle === 'spot';
                                        const isS2S = rec.s2s_candidate;
                                        // If backend returns 0% savings for an OD node (same-type spot move),
                                        // estimate ~65% spot discount as a realistic floor value.
                                        let savingsPct = rec.projected_savings_pct || 0;
                                        if (savingsPct === 0 && !isSpot && rec.current_cost > 0) {
                                            savingsPct = 65; // standard spot discount estimate
                                        }
                                        const savingsMo = ((rec.current_cost || 0) * (savingsPct / 100) * 720).toFixed(2);

                                        // ── Real status from live rebalancing actions ──────────────
                                        // Match this node to an in-flight action by EC2 instance_id
                                        // or by source_pool (instance_type:az) as fallback.
                                        const _activeAction = rebalancingActions.find(a => {
                                            if (!['in_progress', 'waiting_agent'].includes(a.status)) return false;
                                            if (rec.instance_id && a.instance_id && a.instance_id === rec.instance_id) return true;
                                            // fallback: source_pool starts with current instance type AND same AZ
                                            if (a.source_pool && rec.current_type && rec.az) {
                                                const _spParts = (a.source_pool || '').split(':');
                                                return _spParts[0] === rec.current_type && _spParts[1] === rec.az;
                                            }
                                            return false;
                                        });
                                        // Check if this SPOT node is the replacement being provisioned
                                        // for an active migration — show MIGRATING instead of OPTIMIZED
                                        // until the old OD node is terminated (action completes).
                                        const _isMigratingReplacement = isSpot && rebalancingActions.some(a => {
                                            if (!['in_progress', 'waiting_agent'].includes(a.status)) return false;
                                            return (
                                                (rec.instance_id && a.replacement_spot_instance_id &&
                                                 a.replacement_spot_instance_id.startsWith(rec.instance_id?.substring(0, 12))) ||
                                                (rec.instance_id && a.replacement_spot_instance_id &&
                                                 rec.instance_id.startsWith(a.replacement_spot_instance_id?.substring(0, 12)))
                                            );
                                        });
                                        const isProcessing = !!_activeAction;

                                        // ── Determine Status and UI elements ──────────────────────
                                        let statusText = '';
                                        let statusIcon = null;
                                        let actionBtn = null;
                                        let trendLine = null;

                                        if (isProcessing) {
                                            // Node actively being rebalanced right now
                                            statusText = 'Processing';
                                            statusIcon = (
                                                <div className="flex items-center space-x-2">
                                                    <div className="w-5 h-5 flex items-center justify-center">
                                                        <svg className="w-4 h-4 text-blue-500 animate-spin-slow" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path></svg>
                                                    </div>
                                                    <span className="text-[10px] font-bold text-blue-500 uppercase">Processing</span>
                                                </div>
                                            );
                                            actionBtn = (
                                                <button className="px-3 py-1.5 bg-blue-50 text-blue-700 text-[10px] font-bold rounded-md border border-blue-100 uppercase cursor-not-allowed opacity-60">
                                                    {isSpot ? 'SPOT→SPOT' : 'OD→SPOT'}
                                                </button>
                                            );
                                            trendLine = (
                                                <div className="flex justify-center">
                                                    <svg className="h-6 w-16 text-blue-500" viewBox="0 0 100 40">
                                                        <path d="M0 10 L20 15 L40 12 L60 25 L80 30 L100 35" fill="none" stroke="currentColor" strokeLinecap="round" strokeWidth="2.5"></path>
                                                    </svg>
                                                </div>
                                            );
                                        } else if (_isMigratingReplacement) {
                                            // This spot node is the replacement for an OD node currently
                                            // being migrated — don't show OPTIMIZED until old node is gone.
                                            statusText = 'Migrating';
                                            statusIcon = (
                                                <div className="flex items-center space-x-2">
                                                    <div className="w-5 h-5 flex items-center justify-center">
                                                        <svg className="w-4 h-4 text-indigo-500 animate-spin-slow" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path></svg>
                                                    </div>
                                                    <span className="text-[10px] font-bold text-indigo-500 uppercase">Migrating</span>
                                                </div>
                                            );
                                            actionBtn = (
                                                <button className="px-3 py-1.5 bg-indigo-50 text-indigo-600 text-[10px] font-bold rounded-md border border-indigo-100 uppercase cursor-not-allowed opacity-60">New Spot</button>
                                            );
                                            trendLine = (
                                                <div className="flex justify-center">
                                                    <svg className="h-6 w-16 text-indigo-400" viewBox="0 0 100 40">
                                                        <path d="M0 35 L25 28 L50 20 L75 12 L100 5" fill="none" stroke="currentColor" strokeLinecap="round" strokeWidth="2.5"></path>
                                                    </svg>
                                                </div>
                                            );
                                        } else if (isSpot && !isS2S) {
                                            // Already on spot and no better pool available — fully optimized
                                            statusText = 'Optimized';
                                            statusIcon = (
                                                <div className="flex items-center space-x-2">
                                                    <div className="w-5 h-5 flex items-center justify-center text-emerald-600">
                                                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 15a4 4 0 004 4h9a5 5 0 10-.1-9.999 5.002 5.002 0 10-9.78 2.096A4.001 4.001 0 003 15z"></path><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 13l2 2 4-4"></path></svg>
                                                    </div>
                                                    <span className="text-[10px] font-bold text-emerald-600 uppercase">Optimized</span>
                                                </div>
                                            );
                                            actionBtn = (
                                                <button className="px-3 py-1.5 bg-slate-100 text-slate-400 text-[10px] font-bold rounded-md border border-slate-200 uppercase cursor-not-allowed">Active</button>
                                            );
                                            trendLine = (
                                                <div className="flex justify-center">
                                                    <svg className="h-6 w-16 text-emerald-500" viewBox="0 0 100 40">
                                                        <path d="M0 35 L20 32 L40 38 L60 35 L80 37 L100 35" fill="none" stroke="currentColor" strokeLinecap="round" strokeWidth="2.5"></path>
                                                    </svg>
                                                </div>
                                            );
                                        } else {
                                            // OD node not yet in flight, OR spot node ready for S2S upgrade
                                            statusText = 'Ready';
                                            statusIcon = (
                                                <div className="flex items-center space-x-2">
                                                    <div className="w-5 h-5 flex items-center justify-center">
                                                        <div className="w-2 h-2 bg-amber-500 rounded-full animate-blink shadow-[0_0_8px_rgba(245,158,11,0.6)]"></div>
                                                    </div>
                                                    <span className="text-[10px] font-bold text-amber-600 uppercase">Ready</span>
                                                </div>
                                            );
                                            actionBtn = (
                                                <button className="px-3 py-1.5 bg-blue-50 text-blue-700 text-[10px] font-bold rounded-md border border-blue-100 uppercase hover:bg-blue-100">
                                                    {isS2S ? 'SPOT→SPOT' : 'OD→SPOT'}
                                                </button>
                                            );
                                            trendLine = (
                                                <div className="flex justify-center">
                                                    <svg className="h-6 w-16 text-amber-400" viewBox="0 0 100 40">
                                                        <path d="M0 25 L25 20 L50 15 L75 10 L100 8" fill="none" stroke="currentColor" strokeLinecap="round" strokeWidth="2.5"></path>
                                                    </svg>
                                                </div>
                                            );
                                        }

                                        return (
                                            <tr key={idx} className="hover:bg-slate-50/50 transition-colors">
                                                <td className="px-6 py-5">
                                                    <div className="flex flex-col">
                                                        <span className="text-sm font-bold text-slate-900">{rec.node_name}</span>
                                                        <span className={`text-[10px] font-bold uppercase tracking-tight ${isSpot ? 'text-emerald-600' : 'text-blue-600'}`}>
                                                            {isSpot ? 'SPOT' : 'ON-DEMAND'}
                                                        </span>
                                                    </div>
                                                </td>
                                                <td className="px-6 py-5">
                                                    <div className="flex flex-col">
                                                        <span className="text-sm font-medium text-slate-700">{rec.current_type}</span>
                                                        <span className="text-[10px] text-slate-400">{rec.instance_family ? `${rec.instance_family} family` : ''}</span>
                                                    </div>
                                                </td>
                                                <td className="px-6 py-5">
                                                    {(isSpot && !isS2S) ? (
                                                        <span className="text-sm font-medium text-slate-400">—</span>
                                                    ) : (
                                                        <div className="flex flex-col">
                                                            <span className="text-sm font-medium text-slate-700">{rec.target_type}</span>
                                                            <span className="text-[10px] text-slate-400">{rec.target_az}</span>
                                                        </div>
                                                    )}
                                                </td>
                                                <td className="px-6 py-5">
                                                    {statusIcon}
                                                </td>
                                                <td className="px-6 py-5 text-sm font-semibold text-slate-600">
                                                    ${rec.current_cost}/hr
                                                </td>
                                                <td className="px-6 py-5">
                                                    {trendLine}
                                                </td>
                                                <td className="px-6 py-5">
                                                    {actionBtn}
                                                </td>
                                                <td className="px-6 py-5 text-right">
                                                    <span className={`text-sm font-bold ${savingsPct > 0 ? 'text-emerald-600' : 'text-slate-400'}`}>
                                                        {savingsPct > 0 ? `$${savingsMo}/mo` : '—'}
                                                    </span>
                                                </td>
                                            </tr>
                                        );
                                    })
                                ) : (
                                    <tr>
                                        <td colSpan="8" className="px-6 py-12 text-center text-slate-500">
                                            {nodeViewLoading ? (
                                                <div className="flex flex-col items-center">
                                                    <div className="w-8 h-8 flex items-center justify-center mb-4">
                                                        <svg className="w-6 h-6 text-blue-500 animate-spin-slow" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path></svg>
                                                    </div>
                                                    <p>Gathering node telemetry...</p>
                                                </div>
                                            ) : (
                                                <div className="flex flex-col items-center">
                                                    <p>No actionable node recommendations available.</p>
                                                </div>
                                            )}
                                        </td>
                                    </tr>
                                )}
                            </tbody>
                        </table>
                    </div>

                    {/* Per-Node Alternatives Panel (changes.md Node-Specific View) */}
                    {coverageData?.per_node_summary?.length > 0 && (
                        <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
                            <div className="px-5 py-4 border-b border-gray-100 flex items-center justify-between">
                                <div>
                                    <h3 className="text-sm font-bold text-gray-800">Per-Node Alternative Pools</h3>
                                    <p className="text-xs text-gray-500 mt-0.5">Select a node to see its ranked spot replacement options</p>
                                </div>
                                <select
                                    value={selectedNodeId || ''}
                                    onChange={e => { setSelectedNodeId(e.target.value); setNodeAltPage(1); }}
                                    className="px-3 py-1.5 text-sm border border-gray-200 rounded-lg bg-white text-gray-700 font-mono focus:outline-none focus:ring-2 focus:ring-indigo-400"
                                >
                                    {coverageData.per_node_summary.map(n => (
                                        <option key={n.node_id} value={n.node_id}>
                                            {n.instance_type} — {n.node_name || n.instance_id} ({n.status})
                                        </option>
                                    ))}
                                </select>
                            </div>

                            {nodeAltLoading ? (
                                <div className="py-10 text-center">
                                    <div className="inline-block animate-spin rounded-full h-7 w-7 border-b-2 border-indigo-500 mb-3" />
                                    <p className="text-sm text-gray-500">Loading alternatives...</p>
                                </div>
                            ) : nodeAlternatives?.alternatives?.length > 0 ? (
                                <>
                                    <div className="px-5 py-3 bg-gray-50 border-b border-gray-100 flex items-center gap-4 text-xs text-gray-500">
                                        <span><strong className="text-gray-700">{nodeAlternatives.total_alternatives}</strong> valid alternatives for {nodeAlternatives.instance_type} in {nodeAlternatives.az}</span>
                                        <span className="text-gray-300">|</span>
                                        <span>Arch: <strong className="text-gray-700">{nodeAlternatives.architecture}</strong></span>
                                    </div>
                                    <table className="w-full text-sm divide-y divide-gray-100">
                                        <thead className="bg-gray-50 text-xs font-medium text-gray-500 uppercase tracking-wider">
                                            <tr>
                                                <th className="px-4 py-2 text-left">Rank</th>
                                                <th className="px-4 py-2 text-left">Type</th>
                                                <th className="px-4 py-2 text-left">AZ</th>
                                                <th className="px-4 py-2 text-left">Arch</th>
                                                <th className="px-4 py-2 text-right">Spot/hr</th>
                                                <th className="px-4 py-2 text-right">Saving</th>
                                                <th className="px-4 py-2 text-center">Risk</th>
                                                <th className="px-4 py-2 text-right">ML Score</th>
                                            </tr>
                                        </thead>
                                        <tbody className="bg-white divide-y divide-gray-100">
                                            {nodeAlternatives.alternatives.map((alt, i) => {
                                                const riskLabel = alt.spot_advisor_rank === 0 ? '<5%' : alt.spot_advisor_rank === 1 ? '5-10%' : alt.spot_advisor_rank === 2 ? '10-15%' : alt.spot_advisor_rank === 3 ? '15-20%' : '>20%';
                                                const riskColor = alt.spot_advisor_rank <= 1 ? 'bg-green-50 text-green-700' : alt.spot_advisor_rank <= 2 ? 'bg-amber-50 text-amber-700' : 'bg-red-50 text-red-700';
                                                return (
                                                    <tr key={i} className="hover:bg-gray-50">
                                                        <td className="px-4 py-2.5 font-bold text-gray-400">{alt.rank}</td>
                                                        <td className="px-4 py-2.5 font-medium text-gray-900 font-mono">{alt.instance_type}</td>
                                                        <td className="px-4 py-2.5 font-mono text-xs text-gray-500">{alt.az}</td>
                                                        <td className="px-4 py-2.5 text-xs text-gray-500">{alt.architecture || '—'}</td>
                                                        <td className="px-4 py-2.5 text-right font-mono text-gray-700">${(alt.spot_price || 0).toFixed(4)}</td>
                                                        <td className="px-4 py-2.5 text-right font-semibold text-green-600">{alt.saving_pct != null ? `${alt.saving_pct}%` : '—'}</td>
                                                        <td className="px-4 py-2.5 text-center"><span className={`px-2 py-0.5 rounded text-xs font-semibold ${riskColor}`}>{riskLabel}</span></td>
                                                        <td className="px-4 py-2.5 text-right font-bold text-indigo-600">{(alt.ml_score || 0).toFixed(3)}</td>
                                                    </tr>
                                                );
                                            })}
                                        </tbody>
                                    </table>
                                    {/* Pagination */}
                                    {nodeAlternatives.total_pages > 1 && (
                                        <div className="px-5 py-3 border-t border-gray-100 flex items-center justify-between text-xs text-gray-500">
                                            <span>Page {nodeAlternatives.page} of {nodeAlternatives.total_pages} ({nodeAlternatives.total_alternatives} total)</span>
                                            <div className="flex gap-2">
                                                <button
                                                    disabled={nodeAlternatives.page <= 1}
                                                    onClick={() => {
                                                        const p = nodeAltPage - 1;
                                                        setNodeAltPage(p);
                                                        setNodeAltLoading(true);
                                                        ascpaiAPI.getNodeAlternatives(clusterId, selectedNodeId, p, 20)
                                                            .then(r => setNodeAlternatives(r.data))
                                                            .finally(() => setNodeAltLoading(false));
                                                    }}
                                                    className="px-3 py-1 rounded border border-gray-200 bg-white disabled:opacity-40 hover:bg-gray-50"
                                                >← Prev</button>
                                                <button
                                                    disabled={nodeAlternatives.page >= nodeAlternatives.total_pages}
                                                    onClick={() => {
                                                        const p = nodeAltPage + 1;
                                                        setNodeAltPage(p);
                                                        setNodeAltLoading(true);
                                                        ascpaiAPI.getNodeAlternatives(clusterId, selectedNodeId, p, 20)
                                                            .then(r => setNodeAlternatives(r.data))
                                                            .finally(() => setNodeAltLoading(false));
                                                    }}
                                                    className="px-3 py-1 rounded border border-gray-200 bg-white disabled:opacity-40 hover:bg-gray-50"
                                                >Next →</button>
                                            </div>
                                        </div>
                                    )}
                                </>
                            ) : (
                                <div className="py-10 text-center text-gray-500 text-sm">
                                    {selectedNodeId ? 'No valid alternatives found for this node.' : 'Select a node above.'}
                                </div>
                            )}
                        </div>
                    )}
                </div>
            )}

            {/* Cluster Impact View — Per-Node Coverage Report */}
            {activeTab === 'cluster' && (
                <div className="space-y-5">
                    {/* Coverage summary bar */}
                    {coverageData && (
                        <div className="bg-white p-4 rounded-lg shadow-sm border border-gray-200">
                            <div className="flex items-center justify-between mb-3">
                                <div>
                                    <span className="text-sm font-bold text-gray-800">Cluster Coverage</span>
                                    <span className="ml-2 text-xs text-gray-500">— how many nodes have valid spot fallback options</span>
                                </div>
                                <span className="text-xl font-bold text-indigo-600">{coverageData.cluster_coverage_pct ?? 0}%</span>
                            </div>
                            <div className="w-full bg-gray-100 rounded-full h-3 mb-3">
                                <div
                                    className="h-3 rounded-full bg-indigo-500 transition-all"
                                    style={{ width: `${coverageData.cluster_coverage_pct ?? 0}%` }}
                                />
                            </div>
                            <div className="flex gap-6 text-xs text-gray-500">
                                <span><span className="inline-block w-2 h-2 rounded-full bg-green-500 mr-1" />{coverageData.covered_nodes} Covered</span>
                                <span><span className="inline-block w-2 h-2 rounded-full bg-amber-400 mr-1" />{coverageData.at_risk_nodes} At Risk</span>
                                <span><span className="inline-block w-2 h-2 rounded-full bg-red-500 mr-1" />{coverageData.stranded_nodes} Stranded</span>
                                {coverageData.immovable_nodes > 0 && <span><span className="inline-block w-2 h-2 rounded-full bg-gray-400 mr-1" />{coverageData.immovable_nodes} Immovable</span>}
                                <span className="ml-auto text-gray-400">Last computed: {coverageData.computed_at ? new Date(coverageData.computed_at).toLocaleTimeString() : '—'}</span>
                            </div>
                        </div>
                    )}

                    {/* Pool Eligibility Funnel — Task 4.4 */}
                    {poolAuditData && poolAuditData.raw_pool_count > 0 && (
                        <div className="bg-white p-4 rounded-lg shadow-sm border border-gray-200">
                            <div className="flex items-center justify-between mb-3">
                                <span className="text-sm font-bold text-gray-800">Pool Eligibility Funnel</span>
                                <span className="text-xs text-gray-400">
                                    node: {selectedNodeId?.slice(-12)}
                                    {poolAuditData.computed_at ? ` · ${new Date(poolAuditData.computed_at).toLocaleTimeString()}` : ''}
                                </span>
                            </div>
                            <div className="space-y-1 font-mono text-xs text-gray-700">
                                <div className="flex justify-between">
                                    <span className="text-gray-500">Raw pool universe</span>
                                    <span className="font-semibold">{poolAuditData.raw_pool_count.toLocaleString()}</span>
                                </div>
                                {Object.entries(poolAuditData.rejection_reasons || {}).map(([reason, count]) => count > 0 && (
                                    <div key={reason} className="flex justify-between pl-4 text-red-600">
                                        <span>↓ {reason.replace(/_/g, ' ')}</span>
                                        <span>-{count}</span>
                                    </div>
                                ))}
                                <div className="border-t border-gray-200 pt-1 flex justify-between font-semibold text-green-700">
                                    <span>✅ Eligible pools</span>
                                    <span>{poolAuditData.eligible_count.toLocaleString()}</span>
                                </div>
                            </div>
                        </div>
                    )}

                    {/* Per-Node Coverage Table */}
                    <div className="bg-white shadow-sm rounded-lg overflow-x-auto border border-gray-200">
                        <table className="w-full min-w-[860px] divide-y divide-gray-200 text-sm">
                            <thead className="bg-gray-50">
                                <tr>
                                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Node</th>
                                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Current Type</th>
                                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">AZ</th>
                                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Lifecycle</th>
                                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Status</th>
                                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Alternatives</th>
                                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Best Option</th>
                                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Saving</th>
                                </tr>
                            </thead>
                            <tbody className="bg-white divide-y divide-gray-200">
                                {coverageLoading ? (
                                    <tr>
                                        <td colSpan="8" className="px-4 py-12 text-center">
                                            <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600 mb-3" />
                                            <p className="text-gray-500 text-sm">Computing coverage...</p>
                                        </td>
                                    </tr>
                                ) : coverageData?.per_node_summary?.length > 0 ? (
                                    coverageData.per_node_summary.map((node, idx) => {
                                        const statusBadge = {
                                            COVERED: <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-green-50 text-green-700 border border-green-200">✅ {node.alternative_count}</span>,
                                            AT_RISK: <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-amber-50 text-amber-700 border border-amber-200">⚠️ {node.alternative_count}</span>,
                                            STRANDED: <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-red-50 text-red-700 border border-red-200">🔴 None</span>,
                                            IMMOVABLE: <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-gray-100 text-gray-600 border border-gray-200">🔒 Locked</span>,
                                        }[node.status] || <span className="text-gray-400 text-xs">—</span>;

                                        return (
                                            <tr key={idx} className={`hover:bg-gray-50 ${selectedNodeId === node.node_id ? 'bg-indigo-50' : ''}`}>
                                                <td className="px-4 py-3 font-mono text-xs text-gray-700 max-w-[140px] truncate">{node.node_name || node.instance_id}</td>
                                                <td className="px-4 py-3 font-medium text-gray-900">{node.instance_type}</td>
                                                <td className="px-4 py-3 font-mono text-xs text-gray-500">{node.az}</td>
                                                <td className="px-4 py-3">
                                                    <span className={`px-2 py-0.5 rounded text-xs font-semibold ${node.lifecycle === 'spot' ? 'bg-green-50 text-green-700' : 'bg-blue-50 text-blue-700'}`}>
                                                        {node.lifecycle === 'spot' ? 'Spot' : 'OD'}
                                                    </span>
                                                </td>
                                                <td className="px-4 py-3">{statusBadge}</td>
                                                <td className="px-4 py-3 text-center text-sm font-medium text-gray-700">{node.alternative_count ?? 0}</td>
                                                <td className="px-4 py-3 font-mono text-xs text-gray-600">{node.best_pool ? node.best_pool.split(':')[0] : '—'}</td>
                                                <td className="px-4 py-3 font-semibold text-green-600 text-sm">
                                                    {node.best_saving_pct != null ? `${node.best_saving_pct}%` : '—'}
                                                </td>
                                            </tr>
                                        );
                                    })
                                ) : (
                                    <tr>
                                        <td colSpan="8" className="px-4 py-12 text-center text-gray-500">
                                            <FiPieChart className="h-10 w-10 text-gray-300 mb-3 mx-auto" />
                                            <p>No coverage data yet.</p>
                                            <p className="text-xs text-gray-400 mt-1">Coverage is computed every 5 minutes by the reconciliation worker.</p>
                                        </td>
                                    </tr>
                                )}
                            </tbody>
                        </table>
                    </div>

                    {/* Warnings for at-risk / stranded nodes */}
                    {coverageData?.per_node_summary?.filter(n => n.status === 'AT_RISK').length > 0 && (
                        <div className="p-3 bg-amber-50 border border-amber-200 rounded-lg text-sm text-amber-800">
                            ⚠️ {coverageData.per_node_summary.filter(n => n.status === 'AT_RISK').length} node(s) have limited fallback options (1-2 alternatives). Consider enabling more instance families or relaxing the risk ceiling.
                        </div>
                    )}
                    {coverageData?.per_node_summary?.filter(n => n.status === 'STRANDED').length > 0 && (
                        <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-800">
                            🔴 {coverageData.per_node_summary.filter(n => n.status === 'STRANDED').length} node(s) have no valid spot alternatives. All pools either cost more than OD or exceed the risk ceiling. Consider switching to COST_FIRST profile.
                        </div>
                    )}
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
