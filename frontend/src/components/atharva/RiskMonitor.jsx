import React from 'react';
import { FiShield, FiAlertCircle, FiClock } from 'react-icons/fi';

const RiskMonitor = ({ history }) => {
    return (
        <div className="bg-white rounded-xl border border-gray-200 p-5 h-full flex flex-col shadow-sm">
            <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-semibold flex items-center gap-2 text-gray-900">
                    <FiShield className="text-green-500" /> Risk Monitor
                </h2>
                <div className="flex items-center gap-1.5">
                    <span className="relative flex h-2 w-2">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                        <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500"></span>
                    </span>
                    <span className="text-xs text-gray-500 font-medium">Live</span>
                </div>
            </div>

            <div className="space-y-3 max-h-[200px] overflow-y-auto custom-scrollbar pr-1">
                {history?.length === 0 && (
                    <div className="text-center py-4 text-gray-400 text-xs">
                        No recent risk events
                    </div>
                )}

                {history?.map((event) => (
                    <div key={event.id} className="flex gap-3 items-start p-2 rounded hover:bg-gray-50 transition-colors border border-transparent hover:border-gray-100">
                        <div className={`mt-1.5 min-w-[8px] h-2 rounded-full ${event.level === 'critical' ? 'bg-red-600 shadow-sm' :
                                event.level === 'high' ? 'bg-orange-500' :
                                    event.level === 'medium' ? 'bg-yellow-500' :
                                        'bg-blue-500'
                            }`} />

                        <div className="flex-1">
                            <div className="flex justify-between items-start">
                                <p className="text-sm font-medium text-gray-800">{event.message}</p>
                                <span className="text-[10px] text-gray-400 whitespace-nowrap flex items-center gap-1 bg-gray-50 px-1.5 py-0.5 rounded">
                                    <FiClock className="w-3 h-3" />
                                    {new Date(event.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                                </span>
                            </div>
                            <div className="flex items-center gap-2 mt-1">
                                <span className="text-[10px] bg-gray-100 border border-gray-200 px-1.5 rounded text-gray-500 font-medium">
                                    {event.source}
                                </span>
                                {event.resolved && (
                                    <span className="text-[10px] text-green-600 flex items-center gap-0.5 font-medium">
                                        <FiAlertCircle className="fill-current w-2 h-2" /> Resolved
                                    </span>
                                )}
                            </div>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
};

export default RiskMonitor;
