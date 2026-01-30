import React, { useMemo } from 'react';
import { FiTrendingUp, FiTrendingDown, FiAlertOctagon, FiAlertTriangle, FiCheckCircle } from 'react-icons/fi';
import GaugeChart from '../../shared/GaugeChart';

const HeroMetricsPanel = ({ scanResult, stats }) => {
    // Column 1: Total Waste Summary - Use real trend data from API
    const wasteTrend = useMemo(() => {
        // Use real trend data from backend if available
        if (stats?.savings_trend_percent !== null && stats?.savings_trend_percent !== undefined) {
            const trendValue = Math.abs(stats.savings_trend_percent);
            const isUp = stats.savings_trend_percent > 0; // Positive = waste increased (bad), Negative = waste decreased (good)
            return { isUp, value: trendValue, diff: stats.savings_trend_percent };
        }
        // Fallback: No historical data yet
        return { isUp: false, value: 0, diff: 0, noData: true };
    }, [stats]);

    // Column 2: Resource Distribution (Mocked for now as we don't have chart lib explicitly mentioned, using CSS donut or simple bars)
    // Actually we can use the same logic as existing but improved visuals.

    // Column 3: Compliance Health
    const complianceScore = useMemo(() => {
        if (!scanResult?.resources?.length) return 100;
        const compliant = scanResult.resources.filter(r => r.is_compliant !== false).length;
        return Math.round((compliant / scanResult.resources.length) * 100);
    }, [scanResult]);

    // Column 4: Safety Assessment
    const safetyCounts = useMemo(() => {
        const counts = { HIGH: 0, MEDIUM: 0, LOW: 0 };
        if (scanResult?.resources) {
            scanResult.resources.forEach(r => {
                // Approximate safety logic from original file
                let level = 'LOW';
                if (r.is_authorized || r.status === 'SAFE_TO_DELETE') level = 'HIGH';
                else if (r.status === 'ORPHANED') level = 'MEDIUM'; // Simplified

                // Better override based on type
                if (r.type === 'INSTANCE' && r.status === 'UNAUTHORIZED') level = 'MEDIUM';

                counts[level]++;
            });
        }
        return counts;
    }, [scanResult]);

    return (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
            {/* Column 1: Total Waste */}
            <div className="bg-white rounded-xl p-5 border border-gray-200 shadow-sm relative overflow-hidden">
                <h3 className="text-sm font-medium text-gray-500 uppercase tracking-wide">Total Potential Savings</h3>
                <div className="mt-2 flex items-baseline gap-2">
                    <span className="text-3xl font-bold text-gray-900">
                        ${stats?.total_potential_savings?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) || '0.00'}
                    </span>
                    <span className="text-sm text-gray-500">/mo</span>
                </div>
                <div className={`mt-2 flex items-center text-sm ${wasteTrend.noData ? 'text-gray-400' : wasteTrend.isUp ? 'text-red-600' : 'text-green-600'}`}>
                    {wasteTrend.noData ? (
                        <span className="text-gray-400 text-xs">First scan - no comparison available</span>
                    ) : (
                        <>
                            {wasteTrend.isUp ? <FiTrendingUp className="mr-1" /> : <FiTrendingDown className="mr-1" />}
                            <span>{wasteTrend.isUp ? '↑' : '↓'} {wasteTrend.value}% from last scan</span>
                        </>
                    )}
                </div>
                {/* Sparkline placeholder */}
                <div className="absolute bottom-0 left-0 right-0 h-1 bg-gradient-to-r from-blue-500 to-purple-500 opacity-20"></div>
            </div>

            {/* Column 2: Resource Distribution */}
            <div className="bg-white rounded-xl p-5 border border-gray-200 shadow-sm">
                <h3 className="text-sm font-medium text-gray-500 uppercase tracking-wide mb-2">Resource Allocation</h3>
                <div className="flex items-center justify-between mt-2">
                    <div className="text-center">
                        <span className="block text-2xl font-bold text-gray-900">{scanResult?.resources?.length || 0}</span>
                        <span className="text-xs text-gray-500">Flagged</span>
                    </div>
                    {/* Simple Segmented Bar instead of Donut for speed */}
                    <div className="h-16 w-16 rounded-full border-4 border-gray-100 flex items-center justify-center border-t-red-500 border-r-blue-500 border-b-green-500">
                        <span className="text-xs font-bold text-gray-400">Dist</span>
                    </div>
                </div>
                <div className="flex flex-wrap gap-2 mt-2">
                    <span className="text-xs flex items-center"><span className="w-2 h-2 rounded-full bg-red-500 mr-1"></span>Compute</span>
                    <span className="text-xs flex items-center"><span className="w-2 h-2 rounded-full bg-blue-500 mr-1"></span>Storage</span>
                </div>
            </div>

            {/* Column 3: Compliance Health */}
            <div className="bg-white rounded-xl p-5 border border-gray-200 shadow-sm flex flex-col justify-between">
                <div className="flex justify-between items-start">
                    <h3 className="text-sm font-medium text-gray-500 uppercase tracking-wide">Tag Health</h3>
                    <span className={`text-sm font-bold ${complianceScore < 80 ? 'text-orange-500' : 'text-green-600'}`}>{complianceScore}%</span>
                </div>

                <div className="w-full bg-gray-200 rounded-full h-2.5 mt-4">
                    <div className="bg-green-600 h-2.5 rounded-full" style={{ width: `${complianceScore}%` }}></div>
                </div>
                <div className="mt-2 text-xs text-gray-500">
                    {(scanResult?.resources?.length || 0) - (scanResult?.resources?.filter(r => r.is_compliant !== false).length || 0)} resources untagged
                </div>
            </div>

            {/* Column 4: Safety Assessment */}
            <div className="bg-white rounded-xl p-5 border border-gray-200 shadow-sm">
                <h3 className="text-sm font-medium text-gray-500 uppercase tracking-wide mb-3">Safety Analysis</h3>
                <div className="space-y-2">
                    <div className="flex items-center justify-between text-xs">
                        <span className="flex items-center text-green-700"><FiCheckCircle className="mr-1" /> Safe</span>
                        <span className="font-bold">{safetyCounts.HIGH}</span>
                    </div>
                    <div className="w-full bg-gray-100 rounded-full h-1.5">
                        <div className="bg-green-500 h-1.5 rounded-full" style={{ width: `${(safetyCounts.HIGH / (scanResult?.resources?.length || 1)) * 100}%` }}></div>
                    </div>

                    <div className="flex items-center justify-between text-xs">
                        <span className="flex items-center text-yellow-700"><FiAlertTriangle className="mr-1" /> Review</span>
                        <span className="font-bold">{safetyCounts.MEDIUM}</span>
                    </div>
                    <div className="w-full bg-gray-100 rounded-full h-1.5">
                        <div className="bg-yellow-400 h-1.5 rounded-full" style={{ width: `${(safetyCounts.MEDIUM / (scanResult?.resources?.length || 1)) * 100}%` }}></div>
                    </div>

                    <div className="flex items-center justify-between text-xs">
                        <span className="flex items-center text-red-700"><FiAlertOctagon className="mr-1" /> Risky</span>
                        <span className="font-bold">{safetyCounts.LOW}</span>
                    </div>
                    <div className="w-full bg-gray-100 rounded-full h-1.5">
                        <div className="bg-red-500 h-1.5 rounded-full" style={{ width: `${(safetyCounts.LOW / (scanResult?.resources?.length || 1)) * 100}%` }}></div>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default HeroMetricsPanel;
