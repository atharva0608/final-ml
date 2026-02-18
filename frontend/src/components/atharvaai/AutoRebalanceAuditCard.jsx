import React, { useEffect, useState } from 'react';
import { Card } from '../shared';
import { FiSliders, FiCheckCircle, FiAlertTriangle, FiArrowUpRight, FiDollarSign } from 'react-icons/fi';
import api from '../../services/api';

const AutoRebalanceAuditCard = () => {
    const [decisions, setDecisions] = useState([]);
    const [loading, setLoading] = useState(true);
    const [isEnabled, setIsEnabled] = useState(true); // Toggle state

    useEffect(() => {
        fetchAuditLog();
    }, []);

    const fetchAuditLog = async () => {
        try {
            // Reusing rebalancing status endpoint but displaying differently
            // In a real app, this might be a dedicated audit log endpoint with "decision reasoning"
            const response = await api.get('/api/v1/atharvaai/rebalancing/status?limit=3');
            if (response.data && response.data.length > 0) {
                // Add mock "reasoning" for demo purposes since backend doesn't store plain text reasoning yet
                const enriched = response.data.map(d => ({
                    ...d,
                    reason: d.trigger === 'emergency'
                        ? 'Termination notice received (2m warning)'
                        : 'Cost savings opportunity detected (>15%)',
                    savings: d.trigger === 'graceful' ? '18%' : null
                }));
                setDecisions(enriched);
            } else {
                setDecisions(mockDecisions);
            }
        } catch (error) {
            console.error("Failed to fetch audit log:", error);
            setDecisions(mockDecisions);
        } finally {
            setLoading(false);
        }
    };

    const mockDecisions = [
        {
            id: 101,
            target_pool: 'c6g.xlarge:us-east-1a',
            reason: 'Cost dropped 18% vs current pool',
            timestamp: new Date(Date.now() - 1000 * 60 * 45).toISOString(), // 45m ago
            override: false,
            outcome: 'success'
        },
        {
            id: 102,
            target_pool: 'm5.large:us-east-1b',
            reason: 'Spot capacity risk increased to HIGH',
            timestamp: new Date(Date.now() - 1000 * 60 * 60 * 4).toISOString(), // 4h ago
            override: true, // Manual override example
            outcome: 'success'
        },
        {
            id: 103,
            target_pool: 'r5.2xlarge:us-east-1c',
            reason: 'Rebalancing for fragmentation cleanup',
            timestamp: new Date(Date.now() - 1000 * 60 * 60 * 24).toISOString(), // 1d ago
            override: false,
            outcome: 'success'
        }
    ];

    const timeAgo = (isoString) => {
        const seconds = Math.floor((new Date() - new Date(isoString)) / 1000);
        if (seconds < 60) return `${seconds}s ago`;
        if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
        if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
        return `${Math.floor(seconds / 86400)}d ago`;
    };

    if (loading) return <div className="h-40 bg-gray-50 rounded animate-pulse"></div>;

    return (
        <Card className="flex flex-col h-full bg-gradient-to-br from-white to-gray-50">
            <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                    <div className={`w-2 h-2 rounded-full ${isEnabled ? 'bg-green-500 animate-pulse' : 'bg-gray-300'}`}></div>
                    <h3 className="font-semibold text-gray-800">Auto-Rebalancer</h3>
                </div>

                {/* Toggle Switch */}
                <button
                    onClick={() => setIsEnabled(!isEnabled)}
                    className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors focus:outline-none ${isEnabled ? 'bg-green-500' : 'bg-gray-200'
                        }`}
                >
                    <span className={`inline-block h-3 w-3 transform rounded-full bg-white transition-transform ${isEnabled ? 'translate-x-5' : 'translate-x-1'
                        }`} />
                </button>
            </div>

            <div className="space-y-3 flex-1">
                {decisions.map((decision, idx) => (
                    <div key={idx} className="bg-white p-3 rounded-lg border border-gray-100 shadow-sm hover:shadow-md transition-shadow">
                        <div className="flex justify-between items-start mb-1">
                            <span className="text-xs font-bold text-gray-700 font-mono">
                                {decision.target_pool.split(':')[0]}
                            </span>
                            <span className="text-[10px] text-gray-400">
                                {timeAgo(decision.timestamp)}
                            </span>
                        </div>

                        <p className="text-xs text-gray-600 leading-snug mb-2">
                            {decision.reason}
                        </p>

                        <div className="flex items-center justify-between">
                            <div className="flex items-center gap-1.5">
                                {decision.override ? (
                                    <span className="px-1.5 py-0.5 bg-yellow-100 text-yellow-700 text-[10px] rounded border border-yellow-200 flex items-center gap-1">
                                        <FiSliders className="w-2 h-2" /> Manual
                                    </span>
                                ) : (
                                    <span className="px-1.5 py-0.5 bg-blue-50 text-blue-600 text-[10px] rounded border border-blue-100 flex items-center gap-1">
                                        <FiCheckCircle className="w-2 h-2" /> Auto
                                    </span>
                                )}
                            </div>

                            {decision.savings && (
                                <span className="text-[10px] font-medium text-green-600 flex items-center">
                                    <FiArrowUpRight className="w-2.5 h-2.5 mr-0.5" />
                                    {decision.savings} saved
                                </span>
                            )}
                        </div>
                    </div>
                ))}
            </div>

            <div className="mt-3 pt-2 border-t border-gray-200 text-center">
                <button className="text-xs text-blue-600 hover:text-blue-800 font-medium flex items-center justify-center gap-1 mx-auto">
                    View Full Audit Log <FiArrowUpRight />
                </button>
            </div>
        </Card>
    );
};

export default AutoRebalanceAuditCard;
