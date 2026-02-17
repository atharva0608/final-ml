import React from 'react';
import { FiDollarSign, FiCpu, FiServer, FiLayers } from 'react-icons/fi';

const ImpactSummary = ({ stats }) => {
    // Expect stats = { potential_savings: 123.45, instance_count: 5, vcpu_reduction: 12, memory_reduction: 32 }

    return (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
            <div className="bg-white p-4 rounded-lg border border-gray-200 shadow-sm flex items-center justify-between">
                <div>
                    <p className="text-xs text-gray-500 font-medium uppercase tracking-wider">Potential Savings</p>
                    <p className="text-xl font-bold text-green-600 mt-1">
                        ${stats?.potential_savings?.toFixed(2) || '0.00'}/mo
                    </p>
                </div>
                <div className="p-3 bg-green-50 rounded-full text-green-600">
                    <FiDollarSign className="w-5 h-5" />
                </div>
            </div>

            <div className="bg-white p-4 rounded-lg border border-gray-200 shadow-sm flex items-center justify-between">
                <div>
                    <p className="text-xs text-gray-500 font-medium uppercase tracking-wider">Optimization Score</p>
                    <div className="flex items-end gap-2">
                        <p className="text-xl font-bold text-blue-600 mt-1">
                            {stats?.optimization_score || 0}/100
                        </p>
                    </div>
                </div>
                <div className="hidden md:block p-3 bg-blue-50 rounded-full text-blue-600">
                    <div className="relative w-10 h-10 flex items-center justify-center">
                        <svg className="absolute inset-0 w-full h-full transform -rotate-90">
                            <circle cx="20" cy="20" r="16" stroke="currentColor" strokeWidth="4" fill="transparent" className="text-blue-100" />
                            <circle cx="20" cy="20" r="16" stroke="currentColor" strokeWidth="4" fill="transparent" strokeDasharray={100} strokeDashoffset={100 - (stats?.optimization_score || 0)} className="text-blue-600" />
                        </svg>
                    </div>
                </div>
            </div>

            <div className="bg-white p-4 rounded-lg border border-gray-200 shadow-sm flex items-center justify-between">
                <div>
                    <p className="text-xs text-gray-500 font-medium uppercase tracking-wider">vCPU Reduction</p>
                    <p className="text-xl font-bold text-purple-600 mt-1">
                        {stats?.vcpu_reduction || 0} vCPU
                    </p>
                </div>
                <div className="p-3 bg-purple-50 rounded-full text-purple-600">
                    <FiCpu className="w-5 h-5" />
                </div>
            </div>

            <div className="bg-white p-4 rounded-lg border border-gray-200 shadow-sm flex items-center justify-between">
                <div>
                    <p className="text-xs text-gray-500 font-medium uppercase tracking-wider">Memory Reduction</p>
                    <p className="text-xl font-bold text-orange-600 mt-1">
                        {stats?.memory_reduction || 0} GB
                    </p>
                </div>
                <div className="p-3 bg-orange-50 rounded-full text-orange-600">
                    <FiLayers className="w-5 h-5" />
                </div>
            </div>
        </div>
    );
};

export default ImpactSummary;
