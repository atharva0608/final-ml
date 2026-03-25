import React, { useState, useCallback } from 'react';
import { ascpaiAPI } from '../../services/api';
import { useAdaptivePolling } from '../../hooks/useAdaptivePolling';

const GlobalRankingsCard = () => {
    const [rankings, setRankings] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    const defaultTemplate = {
        architecture: ['amd64', 'arm64'],
        vcpu_min: 1,
        vcpu_max: 128,
        memory_gb_min: 1,
        memory_gb_max: 512,
        allowed_families: null,
        allowed_sizes: null,
        allowed_azs: null,
        excluded_instance_types: [],
    };

    const fetchRankings = useCallback(async () => {
        try {
            // m5.large on-demand as reference baseline for global savings comparison
            const currentNodeContext = {
                instance_type: 'm5.large',
                lifecycle: 'on-demand'
            };
            const res = await ascpaiAPI.getRankings(defaultTemplate, 'ap-south-1', 10, null, currentNodeContext);
            setRankings(res.data?.rankings || []);
            setError(null);
        } catch (err) {
            console.error("Failed to fetch global rankings", err);
            setError("Failed to load global pool rankings.");
        } finally {
            setLoading(false);
        }
    }, []);

    // Poll every 60 s — pool prices change frequently
    useAdaptivePolling({ fetchFn: fetchRankings, isActive: false, slowMs: 60_000 });

    if (loading) return <div className="p-4 bg-white rounded-lg shadow border border-gray-100 animate-pulse h-64"></div>;
    if (error) return <div className="p-4 bg-white rounded-lg shadow border border-red-100 text-red-500 text-sm">{error}</div>;

    return (
        <div className="bg-white rounded-lg shadow border border-gray-100 overflow-hidden">
            <div className="px-5 py-4 border-b border-gray-100 bg-gray-50 flex justify-between items-center">
                <div>
                    <h3 className="text-sm font-semibold text-gray-800">Global ML Pool Rankings</h3>
                    <p className="text-xs text-gray-500 mt-0.5">Top 10 highest Expected Value (EV) spot pools (savings vs m5.large on-demand)</p>
                </div>
                <div className="bg-indigo-100 text-indigo-700 text-xs font-bold px-2.5 py-1 rounded-full">LIVE AI</div>
            </div>

            <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200 text-sm">
                    <thead className="bg-gray-50">
                        <tr>
                            <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">Pool</th>
                            <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wider">Savings</th>
                            <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wider">Risk Prob</th>
                            <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wider">Expected Value</th>
                        </tr>
                    </thead>
                    <tbody className="bg-white divide-y divide-gray-100">
                        {rankings.length === 0 ? (
                            <tr><td colSpan="4" className="px-4 py-8 text-center text-gray-500">No ranking data available</td></tr>
                        ) : rankings.map((row, idx) => (
                            <tr key={idx} className="hover:bg-gray-50">
                                <td className="px-4 py-2.5 font-medium text-gray-800">
                                    {row.instance_type}
                                    <span className="text-gray-400 text-xs ml-1 font-normal">({row.az})</span>
                                </td>
                                <td className="px-4 py-2.5 text-right text-green-600 font-medium whitespace-nowrap">
                                    {row.real_savings_pct !== undefined ? (row.real_savings_pct * 100).toFixed(1) + '%' :
                                     row.predicted_savings ? (row.predicted_savings * 100).toFixed(1) + '%' : '-'}
                                </td>
                                <td className="px-4 py-2.5 text-right text-gray-600">
                                    {row.risk_probability !== undefined ? (
                                        <span className={row.risk_probability > 0.4 ? 'text-orange-500' : 'text-gray-600'}>
                                            {(row.risk_probability * 100).toFixed(1)}%
                                        </span>
                                    ) : '-'}
                                </td>
                                <td className="px-4 py-2.5 text-right font-bold text-indigo-600">
                                    {row.expected_value !== undefined ? row.expected_value.toFixed(4) : '-'}
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
};

export default GlobalRankingsCard;
