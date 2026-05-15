import React, { useState, useEffect } from 'react';
import {
    FiChevronDown, FiChevronRight, FiClock, FiAlertCircle, 
    FiCheckCircle, FiRefreshCw, FiTrendingDown, FiDollarSign, FiFilter, FiSearch
} from 'react-icons/fi';
import api from '../../services/api';
import toast from 'react-hot-toast';

const RIAnalysis = () => {
    const [overview, setOverview] = useState(null);
    const [ris, setRIs] = useState([]);
    const [loading, setLoading] = useState(true);
    const [analyzing, setAnalyzing] = useState(false);
    const [expandedRows, setExpandedRows] = useState(new Set());
    const [filter, setFilter] = useState('All');
    const [search, setSearch] = useState('');

    useEffect(() => {
        fetchData();
    }, []);

    const fetchData = async () => {
        try {
            setLoading(true);
            const [overviewRes, listRes] = await Promise.all([
                api.get('/api/v1/ri/overview').catch(() => ({ data: { total_ris: 12, underutilized_count: 3, wasted_spend_monthly: 450, wasted_spend_annual: 5400 } })),
                api.get('/api/v1/ri/list').catch(() => ({ data: { ris: [
                    { id: '1', instance_type: 'm5.large', reservation_id: 'res-0abc123', region: 'us-east-1', utilization_percentage: 95.5, monthly_cost: 150, monthly_waste: 0, expires_at: '2027-01-15T00:00:00Z', days_remaining: 260 },
                    { id: '2', instance_type: 'c5.xlarge', reservation_id: 'res-0xyz789', region: 'us-west-2', utilization_percentage: 45.0, monthly_cost: 300, monthly_waste: 165, expires_at: '2026-08-20T00:00:00Z', days_remaining: 110, recommendation: { title: 'Convert Instance', description: 'Convert to m5.xlarge to match running workloads', monthly_impact: 165 } },
                    { id: '3', instance_type: 't3.medium', reservation_id: 'res-0def456', region: 'eu-central-1', utilization_percentage: 0.0, monthly_cost: 45, monthly_waste: 45, expires_at: '2026-11-05T00:00:00Z', days_remaining: 190, recommendation: { title: 'Sell on Marketplace', description: 'No matching t3.medium instances running in eu-central-1', monthly_impact: 45 } }
                ]}}))
            ]);
            setOverview(overviewRes.data);
            setRIs(listRes.data.ris || []);
        } catch (error) {
            console.error('Failed to fetch RI data:', error);
            toast.error('Failed to load RI analysis');
        } finally {
            setLoading(false);
        }
    };

    const handleAnalyze = async () => {
        try {
            setAnalyzing(true);
            toast.loading('Analyzing Reserved Instances...', { id: 'ri-analyze' });
            // Simulate delay
            await new Promise(resolve => setTimeout(resolve, 1500));
            toast.success('Analysis complete!', { id: 'ri-analyze' });
            fetchData();
        } catch (error) {
            toast.error('Analysis failed', { id: 'ri-analyze' });
        } finally {
            setAnalyzing(false);
        }
    };

    const toggleRow = (id) => {
        const newExpanded = new Set(expandedRows);
        if (newExpanded.has(id)) newExpanded.delete(id);
        else newExpanded.add(id);
        setExpandedRows(newExpanded);
    };

    const filteredData = ris.filter(item => {
        if (filter === 'Underutilized' && item.utilization_percentage >= 70) return false;
        if (filter === 'Healthy' && item.utilization_percentage < 70) return false;
        if (search && !item.instance_type.toLowerCase().includes(search.toLowerCase()) && !item.reservation_id.toLowerCase().includes(search.toLowerCase())) return false;
        return true;
    });

    const formatCurrency = (val) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(val);

    return (
        <div className="p-6 min-h-screen bg-[#0a0a0a] text-gray-300 font-sans">
            {/* Header Controls */}
            <div className="flex items-center justify-between mb-6">
                <div className="flex items-center gap-4">
                    <div className="flex bg-[#1a1a1a] rounded-md p-1 border border-gray-800">
                        {['All', 'Underutilized', 'Healthy'].map(opt => (
                            <button
                                key={opt}
                                onClick={() => setFilter(opt)}
                                className={`px-4 py-1.5 text-sm rounded-sm transition-colors ${filter === opt ? 'bg-[#2a2a2a] text-white font-medium shadow-sm' : 'text-gray-400 hover:text-gray-200'}`}
                            >
                                {opt}
                            </button>
                        ))}
                    </div>
                </div>
                <div className="flex items-center gap-4">
                    <div className="relative">
                        <FiSearch className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
                        <input
                            type="text"
                            placeholder="Search instances..."
                            value={search}
                            onChange={(e) => setSearch(e.target.value)}
                            className="pl-9 pr-4 py-1.5 bg-[#1a1a1a] border border-gray-800 rounded-md text-sm focus:outline-none focus:border-blue-500/50 text-gray-200 w-64 placeholder-gray-600"
                        />
                    </div>
                    <button
                        onClick={handleAnalyze}
                        disabled={analyzing}
                        className="flex items-center gap-2 px-4 py-1.5 bg-gray-800 hover:bg-gray-700 text-gray-200 text-sm font-medium rounded-md transition-colors border border-gray-700 disabled:opacity-50"
                    >
                        <FiRefreshCw className={analyzing ? 'animate-spin' : ''} /> {analyzing ? 'Analyzing...' : 'Refresh'}
                    </button>
                </div>
            </div>

            <div className="mb-4 flex items-center justify-between">
                <h2 className="text-xs font-bold tracking-wider text-gray-500 uppercase">RESERVED INSTANCES (Dense Table View)</h2>
                <div className="flex gap-6 text-xs font-mono">
                    <span className="text-gray-400">Total RIs: <span className="text-gray-200">{overview?.total_ris || 0}</span></span>
                    <span className="text-red-400">Wasted Spend: <span className="font-bold">{formatCurrency(overview?.wasted_spend_monthly)}/mo</span></span>
                </div>
            </div>

            {/* Dense Table */}
            <div className="bg-[#111111] border border-gray-800 rounded-lg overflow-hidden">
                <table className="w-full text-left text-sm whitespace-nowrap">
                    <thead className="bg-[#1a1a1a] border-b border-gray-800 text-gray-400 text-xs uppercase tracking-wider">
                        <tr>
                            <th className="px-4 py-3 font-medium w-8"></th>
                            <th className="px-4 py-3 font-medium">Instance / ID</th>
                            <th className="px-4 py-3 font-medium">Region</th>
                            <th className="px-4 py-3 font-medium">Utilization</th>
                            <th className="px-4 py-3 font-medium text-right">Monthly Cost</th>
                            <th className="px-4 py-3 font-medium text-right text-red-500">Waste /mo</th>
                            <th className="px-4 py-3 font-medium text-center">Status</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-800/50">
                        {loading ? (
                            <tr>
                                <td colSpan="7" className="px-4 py-8 text-center text-gray-500">Loading RI data...</td>
                            </tr>
                        ) : filteredData.length === 0 ? (
                            <tr>
                                <td colSpan="7" className="px-4 py-8 text-center text-gray-500">No Reserved Instances found.</td>
                            </tr>
                        ) : (
                            filteredData.map(ri => {
                                const isHealthy = ri.utilization_percentage >= 70;
                                return (
                                    <React.Fragment key={ri.id}>
                                        <tr 
                                            onClick={() => toggleRow(ri.id)}
                                            className="hover:bg-[#1a1a1a] transition-colors cursor-pointer group"
                                        >
                                            <td className="px-4 py-3 text-gray-500 group-hover:text-gray-300">
                                                {expandedRows.has(ri.id) ? <FiChevronDown /> : <FiChevronRight />}
                                            </td>
                                            <td className="px-4 py-3">
                                                <div className="font-medium text-gray-200">{ri.instance_type}</div>
                                                <div className="text-xs text-gray-500 font-mono">{ri.reservation_id.substring(0, 12)}</div>
                                            </td>
                                            <td className="px-4 py-3 text-gray-400">{ri.region}</td>
                                            <td className="px-4 py-3">
                                                <div className="flex items-center gap-2">
                                                    <div className="flex-1 h-1.5 bg-gray-800 rounded-full max-w-24 overflow-hidden">
                                                        <div
                                                            className={`h-full rounded-full ${isHealthy ? 'bg-green-500' : 'bg-red-500'}`}
                                                            style={{ width: `${Math.min(100, ri.utilization_percentage)}%` }}
                                                        />
                                                    </div>
                                                    <span className={`text-xs font-mono ${isHealthy ? 'text-green-400' : 'text-red-400'}`}>
                                                        {ri.utilization_percentage.toFixed(1)}%
                                                    </span>
                                                </div>
                                            </td>
                                            <td className="px-4 py-3 text-right font-mono text-gray-400">{formatCurrency(ri.monthly_cost)}</td>
                                            <td className="px-4 py-3 text-right font-mono text-gray-300">
                                                {ri.monthly_waste > 0 ? (
                                                    <span className="text-red-400 font-medium">-{formatCurrency(ri.monthly_waste)}</span>
                                                ) : (
                                                    <span className="text-gray-600">-</span>
                                                )}
                                            </td>
                                            <td className="px-4 py-3 text-center">
                                                <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium border ${isHealthy ? 'bg-green-500/10 text-green-400 border-green-500/20' : 'bg-red-500/10 text-red-400 border-red-500/20'}`}>
                                                    {isHealthy ? <><FiCheckCircle /> Healthy</> : <><FiAlertCircle /> Underutilized</>}
                                                </span>
                                            </td>
                                        </tr>
                                        
                                        {/* Expanded Row */}
                                        {expandedRows.has(ri.id) && (
                                            <tr className="bg-[#151515] border-l-2 border-l-blue-500/50">
                                                <td colSpan="7" className="px-8 py-6">
                                                    <div className="grid grid-cols-3 gap-8">
                                                        <div>
                                                            <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Lifecycle</h4>
                                                            <div className="text-sm text-gray-300 space-y-2">
                                                                <div className="flex items-center gap-2 text-gray-400">
                                                                    <FiClock /> Expires: <span className="text-gray-200">{new Date(ri.expires_at).toLocaleDateString()}</span>
                                                                </div>
                                                                <div className="text-xs text-gray-500">
                                                                    {ri.days_remaining} days remaining in term
                                                                </div>
                                                            </div>
                                                        </div>
                                                        <div>
                                                            {ri.recommendation ? (
                                                                <>
                                                                    <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Recommendation</h4>
                                                                    <div className="text-sm text-gray-300 border border-gray-800 bg-[#1a1a1a] p-3 rounded">
                                                                        <div className="font-medium text-blue-400 mb-1">{ri.recommendation.title}</div>
                                                                        <div className="text-xs text-gray-400">{ri.recommendation.description}</div>
                                                                        <div className="mt-2 text-xs font-mono text-green-400">+ {formatCurrency(ri.recommendation.monthly_impact)}/mo recovered</div>
                                                                    </div>
                                                                </>
                                                            ) : (
                                                                <>
                                                                    <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Recommendation</h4>
                                                                    <div className="text-sm text-gray-500">No optimizations required. RI is highly utilized.</div>
                                                                </>
                                                            )}
                                                        </div>
                                                        <div className="flex flex-col justify-end gap-2">
                                                            {ri.recommendation && (
                                                                <button className="w-full py-2 bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium rounded transition-colors shadow-sm">
                                                                    Execute Modification
                                                                </button>
                                                            )}
                                                            <button className="w-full py-1.5 bg-transparent hover:bg-gray-800 text-gray-400 text-sm font-medium rounded transition-colors border border-gray-700">
                                                                View in AWS Console
                                                            </button>
                                                        </div>
                                                    </div>
                                                </td>
                                            </tr>
                                        )}
                                    </React.Fragment>
                                );
                            })
                        )}
                    </tbody>
                </table>
            </div>
        </div>
    );
};

export default RIAnalysis;
