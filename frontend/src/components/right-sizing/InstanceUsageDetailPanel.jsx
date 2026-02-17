import React from 'react';
import { Card } from '../shared';
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts';
import { FiCpu, FiServer, FiArrowRight, FiActivity, FiX, FiCheck } from 'react-icons/fi';

const Sparkline = ({ data, color, title, currentVal }) => (
    <div className="h-24 w-full">
        <div className="flex justify-between items-end mb-1 px-1">
            <span className="text-xs text-gray-500 font-medium">{title}</span>
            <span className="text-sm font-bold text-gray-800">{currentVal}%</span>
        </div>
        <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data ? data.map((v, i) => ({ day: i, val: v })) : []}>
                <defs>
                    <linearGradient id={`color${title}`} x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor={color} stopOpacity={0.3} />
                        <stop offset="95%" stopColor={color} stopOpacity={0} />
                    </linearGradient>
                </defs>
                <Tooltip
                    contentStyle={{ borderRadius: '4px', fontSize: '10px', padding: '4px' }}
                    formatter={(val) => [`${val}%`, title]}
                    labelFormatter={() => ''}
                />
                <ReferenceLine y={100} stroke="#eee" />
                <Area type="monotone" dataKey="val" stroke={color} fillOpacity={1} fill={`url(#color${title})`} strokeWidth={2} />
            </AreaChart>
        </ResponsiveContainer>
    </div>
);

const InstanceUsageDetailPanel = ({ instance, onClose, onApply }) => {
    if (!instance) return null;

    const cpuHistory = instance.utilization_history?.cpu || [];
    const memHistory = instance.utilization_history?.memory || [];

    return (
        <div className="fixed inset-y-0 right-0 w-96 bg-white shadow-2xl transform transition-transform duration-300 z-40 border-l border-gray-200 overflow-y-auto">
            <div className="p-6">
                <div className="flex justify-between items-start mb-6">
                    <div>
                        <h2 className="text-lg font-bold text-gray-900">Instance Analysis</h2>
                        <p className="text-xs text-gray-500 font-mono mt-1">{instance.instance_id}</p>
                    </div>
                    <button onClick={onClose} className="text-gray-400 hover:text-gray-600 p-1">
                        <FiX className="w-5 h-5" />
                    </button>
                </div>

                {/* Recommendation Summary */}
                <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6">
                    <div className="flex items-center gap-2 mb-2">
                        <span className="px-2 py-0.5 bg-blue-100 text-blue-700 text-xs font-bold rounded uppercase">
                            Recommendation
                        </span>
                        {instance.confidence && (
                            <span className={`px-2 py-0.5 text-xs font-bold rounded uppercase ${instance.confidence === 'HIGH' ? 'bg-green-100 text-green-700' : 'bg-yellow-100 text-yellow-700'
                                }`}>
                                {instance.confidence} Confidence
                            </span>
                        )}
                    </div>

                    <div className="flex items-center justify-between mt-3">
                        <div className="text-center">
                            <p className="text-xs text-gray-500 mb-1">Current</p>
                            <p className="font-mono font-bold text-gray-800">{instance.instance_type}</p>
                            <p className="text-[10px] text-gray-400">4vCPU / 16GB</p>
                        </div>
                        <FiArrowRight className="text-blue-400 w-5 h-5" />
                        <div className="text-center">
                            <p className="text-xs text-gray-500 mb-1">Optimized</p>
                            <p className="font-mono font-bold text-blue-700">{instance.recommendation?.split('to ')[1] || 'Unknown'}</p>
                            <p className="text-[10px] text-gray-400">2vCPU / 8GB</p>
                        </div>
                    </div>

                    <div className="mt-4 pt-3 border-t border-blue-100 flex justify-between items-center">
                        <span className="text-xs text-blue-800 font-medium">Monthly Savings</span>
                        <span className="text-lg font-bold text-green-600">${instance.potential_savings_monthly}</span>
                    </div>
                </div>

                {/* Utilization Charts */}
                <div className="space-y-6 mb-8">
                    <Sparkline
                        title="CPU Utilization (14 Days)"
                        data={cpuHistory}
                        color="#8884d8"
                        currentVal={instance.utilization_percent?.cpu}
                    />
                    <Sparkline
                        title="Memory Utilization (14 Days)"
                        data={memHistory}
                        color="#82ca9d"
                        currentVal={instance.utilization_percent?.memory}
                    />
                    <div className="text-[10px] text-gray-400 text-center italic">
                        * Peak usage drives recommendation size
                    </div>
                </div>

                {/* Actions */}
                <div className="sticky bottom-0 bg-white pt-4 pb-2 border-t border-gray-100">
                    <p className="text-xs text-gray-500 mb-3 px-1">
                        Wait for next maintenance window or apply immediately?
                    </p>
                    <div className="flex gap-3">
                        <button
                            onClick={onClose}
                            className="flex-1 py-2 border border-gray-300 text-gray-700 rounded-md hover:bg-gray-50 text-sm font-medium"
                        >
                            Ignore
                        </button>
                        <button
                            onClick={() => onApply(instance)}
                            className="flex-1 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 text-sm font-medium flex items-center justify-center gap-2"
                        >
                            <FiCheck className="w-4 h-4" /> Apply Fix
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default InstanceUsageDetailPanel;
