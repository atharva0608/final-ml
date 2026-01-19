import React, { useState } from 'react';
import { FiFilter, FiCalendar, FiMapPin, FiDatabase, FiRefreshCw } from 'react-icons/fi';

const FilterPanel = ({
    accounts,
    selectedAccount,
    onAccountChange,
    selectedRegion,
    onRegionChange,
    regionsList,
    onRefresh,
    loading,
    lastScan
}) => {
    const [isExpanded, setIsExpanded] = useState(false);
    const [selectedSafety, setSelectedSafety] = useState([]);

    const toggleSafety = (level) => {
        setSelectedSafety(prev => prev.includes(level)
            ? prev.filter(l => l !== level)
            : [...prev, level]
        );
    };

    return (
        <div className="bg-white border-b border-gray-200">
            <div className="px-6 py-2 flex items-center justify-between text-sm">
                <div className="flex items-center gap-4">
                    {/* Account Selector - Enhanced Styling */}
                    <div className="flex items-center gap-2 bg-gray-50 px-3 py-1.5 rounded-lg border border-gray-200">
                        <FiDatabase className="text-gray-500" />
                        <select
                            className="bg-transparent border-none text-sm font-semibold text-gray-900 focus:ring-0 cursor-pointer p-0 pr-6"
                            value={selectedAccount}
                            onChange={(e) => onAccountChange(e.target.value)}
                        >
                            {(!accounts || accounts.length === 0) && <option>Loading...</option>}
                            {accounts.map(acc => (
                                <option key={acc.id} value={acc.id}>{acc.name || acc.aws_account_id}</option>
                            ))}
                        </select>
                    </div>

                    {/* Region Selector - Enhanced Styling */}
                    <div className="flex items-center gap-2 bg-gray-50 px-3 py-1.5 rounded-lg border border-gray-200">
                        <FiMapPin className="text-gray-500" />
                        <select
                            className="bg-transparent border-none text-sm font-semibold text-gray-900 focus:ring-0 cursor-pointer p-0 pr-6"
                            value={selectedRegion}
                            onChange={(e) => onRegionChange(e.target.value)}
                        >
                            {regionsList.map(r => (
                                <option key={r.id} value={r.id}>{r.name}</option>
                            ))}
                        </select>
                    </div>

                    <div className="h-6 w-px bg-gray-200 mx-2"></div>

                    {/* Filter Trigger */}
                    <button
                        onClick={() => setIsExpanded(!isExpanded)}
                        className={`flex items-center gap-2 font-medium px-3 py-1.5 rounded-lg transition-colors border ${isExpanded
                            ? 'bg-blue-50 border-blue-200 text-blue-700'
                            : 'bg-white border-transparent text-gray-600 hover:bg-gray-50 hover:border-gray-200'
                            }`}
                    >
                        <FiFilter />
                        Filters
                        {selectedSafety.length > 0 && (
                            <span className="bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded text-[10px] font-bold ml-1">
                                {selectedSafety.length}
                            </span>
                        )}
                    </button>
                </div>

                {/* Actions */}
                <div className="flex items-center gap-3">
                    <button
                        onClick={() => onRefresh && onRefresh()}
                        disabled={loading}
                        className="flex items-center gap-2 px-3 py-1.5 bg-white border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 disabled:opacity-50 transition-colors shadow-sm font-medium"
                    >
                        <FiRefreshCw className={loading ? 'animate-spin' : ''} />
                        Refresh
                    </button>
                    <div className="flex items-center text-gray-400 text-xs">
                        <FiCalendar className="mr-1.5" />
                        <span>Last scan: {lastScan ? new Date(lastScan).toLocaleString() : 'Never'}</span>
                    </div>
                </div>
            </div>

            {/* Expanded Filter Area */}
            {isExpanded && (
                <div className="px-6 py-4 bg-gray-50 border-t border-gray-100 animate-fadeIn text-sm">
                    <div className="grid grid-cols-1 md:grid-cols-4 gap-8">
                        <div>
                            <h4 className="text-[10px] font-bold text-gray-400 uppercase tracking-widest mb-3">Safety Level</h4>
                            <div className="flex flex-wrap gap-2">
                                {['Safe', 'Review', 'Risky'].map(level => (
                                    <button
                                        key={level}
                                        onClick={() => toggleSafety(level)}
                                        className={`px-3 py-1 rounded border transition-all ${selectedSafety.includes(level)
                                            ? 'bg-gray-800 border-gray-800 text-white'
                                            : 'bg-white border-gray-200 text-gray-600 hover:border-gray-300'
                                            }`}
                                    >
                                        {level}
                                    </button>
                                ))}
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default FilterPanel;
