import React, { useState, useEffect } from 'react';
import { atharvaaiAPI, templateAPI } from '../../services/api';
import './PoolRankings.css';

const PoolRankings = ({ clusterId, initialTemplateId = null }) => {
    const [pools, setPools] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [selectedTemplate, setSelectedTemplate] = useState(null);
    const [availableTemplates, setAvailableTemplates] = useState([]);
    const [templateApplied, setTemplateApplied] = useState(null);
    const [template, setTemplate] = useState({
        architecture: ['amd64'],
        vcpu_min: 2,
        vcpu_max: 16,
        memory_gb_min: 4,
        memory_gb_max: 64,
        allowed_families: ['m5', 'm6i', 'c5', 'c6i', 'r5', 'r6i'],
        allowed_sizes: ['large', 'xlarge', '2xlarge', '4xlarge'],
        allowed_azs: null,
        excluded_instance_types: []
    });
    const [blacklist, setBlacklist] = useState([]);
    const [autoRefresh, setAutoRefresh] = useState(true);

    // Auto-load default template on mount (or use initialTemplateId from query params)
    useEffect(() => {
        const loadTemplates = async () => {
            try {
                const { data } = await templateAPI.list();
                const templates = Array.isArray(data) ? data : (data?.templates || []);
                setAvailableTemplates(templates);

                // If initialTemplateId provided (from query param), use that
                if (initialTemplateId) {
                    const template = templates.find(t => t.id === initialTemplateId);
                    if (template) {
                        setSelectedTemplate(template);
                        return;
                    }
                }

                // Otherwise, load default template
                try {
                    const { data: defaultTemplate } = await templateAPI.getDefault();
                    setSelectedTemplate(defaultTemplate);
                } catch (err) {
                    if (err.response?.status === 404) {
                        console.log('No default template set, showing all pools');
                    } else {
                        console.error('Error loading default template:', err);
                    }
                }
            } catch (err) {
                console.error('Error loading templates:', err);
            }
        };

        loadTemplates();
    }, [initialTemplateId]);

    useEffect(() => {
        if (clusterId) {
            fetchPoolRankings();
            fetchBlacklist();
        }

        // Auto-refresh every 30 seconds
        const interval = setInterval(() => {
            if (autoRefresh && clusterId) {
                fetchPoolRankings();
                fetchBlacklist();
            }
        }, 30000);

        return () => clearInterval(interval);
    }, [autoRefresh, template, clusterId, selectedTemplate]);

    const fetchPoolRankings = async () => {
        if (!clusterId) return;
        try {
            setLoading(true);

            // If a template is selected, use the template-based endpoint
            if (selectedTemplate?.id) {
                const response = await atharvaaiAPI.getRankingsForTemplate(
                    selectedTemplate.id,
                    'ap-south-1',
                    20
                );
                setPools(response.data);
                setTemplateApplied(response.data.template_applied || { id: selectedTemplate.id, name: selectedTemplate.name });
            } else {
                // Fall back to body-based template
                const response = await atharvaaiAPI.getRankings(template, 'ap-south-1', 20, clusterId);
                setPools(response.data);
                setTemplateApplied(null);
            }

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
        fetchPoolRankings();
        fetchBlacklist();
    };

    const getSavingsColor = (savingsPct) => {
        if (savingsPct >= 0.90) return 'text-green-600';
        if (savingsPct >= 0.70) return 'text-yellow-600';
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
        const labels = {
            0: '<5%',
            1: '5-10%',
            2: '10-15%',
            3: '15-20%',
            4: '>20%'
        };
        return labels[rank] || 'Unknown';
    };

    return (
        <div className="pool-rankings-container p-6">
            <div className="flex justify-between items-center mb-6">
                <div>
                    <h1 className="text-3xl font-bold text-gray-800">AtharvaAi Pool Rankings</h1>
                    <p className="text-gray-600 mt-1">ML-driven spot instance pool recommendations</p>
                </div>
                <div className="flex gap-3">
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

            {/* Template Selector */}
            <div className="mb-6 p-4 bg-blue-50 border border-blue-200 rounded-lg">
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-4">
                        <label className="text-sm font-semibold text-gray-700">Filter by Template:</label>
                        <select
                            value={selectedTemplate?.id || ''}
                            onChange={(e) => {
                                const template = availableTemplates.find(t => t.id === e.target.value);
                                setSelectedTemplate(template || null);
                            }}
                            className="px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                        >
                            <option value="">No template filter</option>
                            {availableTemplates.map((t) => (
                                <option key={t.id} value={t.id}>
                                    {t.name} {t.is_default ? '(Default)' : ''}
                                </option>
                            ))}
                        </select>
                    </div>
                    {templateApplied && (
                        <div className="flex items-center gap-2">
                            <span className="px-3 py-1 bg-green-100 text-green-800 rounded-full text-sm font-medium">
                                Template Applied: {templateApplied.name}
                            </span>
                        </div>
                    )}
                </div>
                {selectedTemplate && (
                    <div className="mt-2 text-xs text-gray-600">
                        <span className="font-semibold">Active Constraints:</span> {' '}
                        {selectedTemplate.allowed_families?.length > 0 && (
                            <span>Families: {selectedTemplate.allowed_families.join(', ')}</span>
                        )}
                        {selectedTemplate.vcpu_min && selectedTemplate.vcpu_max && (
                            <span> | vCPU: {selectedTemplate.vcpu_min}-{selectedTemplate.vcpu_max}</span>
                        )}
                        {selectedTemplate.memory_gb_min && selectedTemplate.memory_gb_max && (
                            <span> | Memory: {selectedTemplate.memory_gb_min}-{selectedTemplate.memory_gb_max} GB</span>
                        )}
                    </div>
                )}
            </div>

            {/* Global Blacklist Alert */}
            {blacklist.length > 0 && (
                <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg">
                    <h3 className="text-lg font-semibold text-red-800 mb-2">
                        ⚠️ Globally Flagged Pools ({blacklist.length})
                    </h3>
                    <div className="flex flex-wrap gap-2">
                        {blacklist.map((item, idx) => (
                            <span
                                key={idx}
                                className="px-3 py-1 bg-red-100 text-red-800 rounded-full text-sm"
                            >
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

            {/* Loading State */}
            {loading && pools.length === 0 && (
                <div className="text-center py-12">
                    <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
                    <p className="mt-4 text-gray-600">Loading pool rankings...</p>
                </div>
            )}

            {/* Pool Rankings Table */}
            {!loading && pools.length > 0 && (
                <div className="bg-white shadow-md rounded-lg overflow-hidden">
                    <table className="min-w-full divide-y divide-gray-200">
                        <thead className="bg-gray-50">
                            <tr>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Rank</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Instance Type</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">AZ</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">vCPU / Memory</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Spot Price</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Savings %</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Cost Est.</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Interruption</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">ML Score</th>
                            </tr>
                        </thead>
                        <tbody className="bg-white divide-y divide-gray-200">
                            {pools.map((pool) => (
                                <tr
                                    key={`${pool.instance_type}-${pool.az}`}
                                    className={`hover:bg-gray-50 ${pool.is_flagged ? 'bg-red-50' : ''}`}
                                >
                                    <td className="px-6 py-4 whitespace-nowrap">
                                        <span className={`inline-flex items-center justify-center w-8 h-8 rounded-full ${pool.rank === 1 ? 'bg-yellow-100 text-yellow-800' :
                                                pool.rank <= 3 ? 'bg-green-100 text-green-800' :
                                                    'bg-gray-100 text-gray-800'
                                            } font-bold`}>
                                            {pool.rank}
                                        </span>
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap">
                                        <div className="flex items-center">
                                            <div className="text-sm font-medium text-gray-900">{pool.instance_type}</div>
                                            {pool.is_flagged && (
                                                <span className="ml-2 px-2 py-0.5 text-xs bg-red-100 text-red-800 rounded">Flagged</span>
                                            )}
                                        </div>
                                        <div className="text-sm text-gray-500">{pool.architecture}</div>
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">{pool.az}</td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                                        {pool.vcpu} vCPU / {pool.memory_gb} GB
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                                        ${pool.spot_price.toFixed(4)}/hr
                                        <div className="text-xs text-gray-500">vs ${pool.ondemand_price.toFixed(4)}</div>
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap">
                                        <span className={`text-sm font-semibold ${getSavingsColor(pool.savings_pct)}`}>
                                            {(pool.savings_pct * 100).toFixed(1)}%
                                        </span>
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                                        ${pool.cost_estimate.toFixed(2)}/day
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap">
                                        <span className={`px-2 py-1 inline-flex text-xs leading-5 font-semibold rounded-full ${getInterruptionColor(pool.spot_advisor_rank)}`}>
                                            {getInterruptionLabel(pool.spot_advisor_rank)}
                                        </span>
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap">
                                        <div className="text-sm font-bold text-blue-600">{pool.ml_score.toFixed(2)}</div>
                                        <div className="text-xs text-gray-500">ML Score</div>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}

            {/* Empty State */}
            {!loading && pools.length === 0 && !error && (
                <div className="text-center py-12 bg-white shadow-md rounded-lg">
                    <p className="text-gray-600">No pool rankings available. Adjust your filters and try again.</p>
                </div>
            )}

            {/* Legend */}
            <div className="mt-6 p-4 bg-gray-50 rounded-lg">
                <h3 className="text-sm font-semibold text-gray-700 mb-2">Legend</h3>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
                    <div>
                        <span className="font-semibold">ML Score:</span> Combined savings % and cost (higher = better)
                    </div>
                    <div>
                        <span className="font-semibold">Savings %:</span> Spot vs On-Demand price difference
                    </div>
                    <div>
                        <span className="font-semibold">Interruption:</span> AWS Spot Advisor frequency rating
                    </div>
                </div>
            </div>
        </div>
    );
};

export default PoolRankings;
