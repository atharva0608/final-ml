import React, { useEffect, useState } from 'react';
import { Card } from '../shared';
import { FiGrid, FiInfo, FiAlertCircle } from 'react-icons/fi';
import api from '../../services/api';

const InterruptionHeatmap = () => {
    const [heatmapData, setHeatmapData] = useState([]);
    const [loading, setLoading] = useState(true);
    const [selectedFamily, setSelectedFamily] = useState('ALL');

    useEffect(() => {
        fetchHeatmap();
    }, []);

    const fetchHeatmap = async () => {
        try {
            const response = await api.get('/api/v1/atharvaai/interruption-heatmap?days=30');
            setHeatmapData(response.data || []);
        } catch (error) {
            console.error("Failed to fetch heatmap:", error);
            setHeatmapData([]);
        } finally {
            setLoading(false);
        }
    };

    const getRiskColor = (count) => {
        if (!count) return 'bg-gray-100'; // No data
        if (count >= 5) return 'bg-red-500';
        if (count >= 2) return 'bg-orange-400';
        return 'bg-green-400';
    };

    const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    const hours = Array.from({ length: 24 }, (_, i) => i);

    // Filter logic
    const displayedData = selectedFamily === 'ALL'
        ? heatmapData.flatMap(d => d.heatmap) // Flatten all families? Logic actually complex for heatmap overlay.
        // Better: just show aggregate count for ALL for now.
        : heatmapData.find(d => d.family === selectedFamily)?.heatmap || [];

    // Helper to get count for specific cell
    const getCellData = (d, h) => {
        if (selectedFamily === 'ALL') {
            // Sum aggregations
            let total = 0;
            heatmapData.forEach(fam => {
                const cell = fam.heatmap.find(c => c.day === d && c.hour === h);
                if (cell) total += cell.interruption_count;
            });
            return total;
        } else {
            const cell = displayedData.find(c => c.day === d && c.hour === h);
            return cell ? cell.interruption_count : 0;
        }
    };

    if (loading) return <div className="p-4 text-center text-gray-400">Loading risk heatmap...</div>;

    if (!heatmapData || heatmapData.length === 0) {
        return (
            <Card className="h-full">
                <div className="flex items-center gap-2 mb-4">
                    <FiGrid className="text-purple-600" />
                    <h3 className="font-semibold text-gray-800">Interruption Heatmap (30d)</h3>
                </div>
                <div className="flex flex-col items-center justify-center py-12 text-gray-400">
                    <FiAlertCircle size={48} className="mb-4" />
                    <p className="text-sm font-medium">No interruption data available</p>
                    <p className="text-xs mt-2 text-center max-w-xs">
                        This heatmap will populate once spot interruptions are detected in your AWS account
                    </p>
                </div>
            </Card>
        );
    }

    return (
        <Card className="h-full">
            <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                    <FiGrid className="text-purple-600" />
                    <h3 className="font-semibold text-gray-800">Interruption Heatmap (30d)</h3>
                </div>

                <select
                    className="text-xs border border-gray-300 rounded-md px-2 py-1 bg-white text-gray-700"
                    value={selectedFamily}
                    onChange={(e) => setSelectedFamily(e.target.value)}
                >
                    <option value="ALL">All Families</option>
                    {heatmapData.map(d => (
                        <option key={d.family} value={d.family}>{d.family.toUpperCase()} Family</option>
                    ))}
                </select>
            </div>

            <div className="overflow-x-auto">
                <div className="min-w-[500px]">
                    {/* Header Row (Hours) */}
                    <div className="flex mb-1">
                        <div className="w-10"></div> {/* Row label spacer */}
                        {hours.filter(h => h % 3 === 0).map(h => (
                            // Only show every 3rd label to save space
                            <div key={h} className="flex-1 text-[10px] text-gray-400 text-center border-l border-gray-100">
                                {h}:00
                            </div>
                        ))}
                    </div>

                    {/* Heatmap Grid */}
                    <div className="space-y-1">
                        {days.map((day, dIdx) => (
                            <div key={dIdx} className="flex items-center h-6">
                                <span className="w-10 text-[10px] text-gray-500 font-medium">{day}</span>
                                <div className="flex-1 flex gap-[1px] h-full">
                                    {hours.map((h) => {
                                        const count = getCellData(dIdx, h);
                                        return (
                                            <div
                                                key={h}
                                                className={`flex-1 h-full rounded-sm transition-colors cursor-pointer hover:opacity-80 group relative ${getRiskColor(count)}`}
                                            >
                                                {count > 0 && (
                                                    <div className="opacity-0 group-hover:opacity-100 absolute bottom-full left-1/2 -translate-x-1/2 mb-1 px-2 py-1 bg-gray-900 text-white text-[10px] rounded pointer-events-none whitespace-nowrap z-10 transition-opacity">
                                                        {day} {h}:00 - {count} interruptions
                                                    </div>
                                                )}
                                            </div>
                                        );
                                    })}
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            </div>

            {/* Legend */}
            <div className="flex items-center justify-end gap-4 mt-4 text-[10px] text-gray-500">
                <div className="flex items-center gap-1">
                    <div className="w-2 h-2 rounded-sm bg-gray-100"></div> Safe
                </div>
                <div className="flex items-center gap-1">
                    <div className="w-2 h-2 rounded-sm bg-green-400"></div> Low
                </div>
                <div className="flex items-center gap-1">
                    <div className="w-2 h-2 rounded-sm bg-orange-400"></div> Medium
                </div>
                <div className="flex items-center gap-1">
                    <div className="w-2 h-2 rounded-sm bg-red-500"></div> High
                </div>
            </div>
        </Card>
    );
};

export default InterruptionHeatmap;
