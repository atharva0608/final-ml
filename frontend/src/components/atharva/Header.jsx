import React from 'react';
import { FiCpu, FiShield, FiZap, FiActivity } from 'react-icons/fi';

const Header = ({ status }) => {
    return (
        <header className="mb-6 flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
            <div>
                <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-3">
                    AtharvaAi
                    <span className="text-xs font-mono bg-blue-100 text-blue-700 px-2 py-1 rounded border border-blue-200">BETA</span>
                </h1>
                <p className="text-gray-500 mt-1 text-sm">Intelligent Cost Optimization & Risk Management</p>
            </div>

            {/* Quick Stats Cards */}
            <div className="flex gap-4 w-full md:w-auto overflow-x-auto pb-2 md:pb-0">

                {/* Risk Score Card */}
                <div className="bg-white p-3 rounded-lg border border-gray-200 flex items-center gap-3 min-w-[140px] shadow-sm">
                    <div className={`p-2 rounded-full ${status?.risk_level === 'low' ? 'bg-green-100 text-green-600' :
                            status?.risk_level === 'medium' ? 'bg-yellow-100 text-yellow-600' :
                                'bg-red-100 text-red-600'
                        }`}>
                        <FiShield className="w-5 h-5" />
                    </div>
                    <div>
                        <p className="text-[10px] text-gray-500 uppercase font-bold tracking-wider">Risk Score</p>
                        <div className="flex items-baseline gap-1">
                            <p className={`font-bold text-lg ${status?.risk_level === 'low' ? 'text-green-600' :
                                    status?.risk_level === 'medium' ? 'text-yellow-600' :
                                        'text-red-600'
                                }`}>{status?.risk_score}</p>
                            <span className="text-xs text-gray-400">/100</span>
                        </div>
                    </div>
                </div>

                {/* Savings Card */}
                <div className="bg-white p-3 rounded-lg border border-gray-200 flex items-center gap-3 min-w-[140px] shadow-sm">
                    <div className="p-2 rounded-full bg-blue-100 text-blue-600">
                        <FiActivity className="w-5 h-5" />
                    </div>
                    <div>
                        <p className="text-[10px] text-gray-500 uppercase font-bold tracking-wider">Savings Rate</p>
                        <p className="font-bold text-lg text-gray-900">{status?.savings_rate}%</p>
                    </div>
                </div>

                {/* Active Opts Card */}
                <div className="bg-white p-3 rounded-lg border border-gray-200 flex items-center gap-3 min-w-[140px] shadow-sm">
                    <div className="p-2 rounded-full bg-purple-100 text-purple-600">
                        <FiZap className="w-5 h-5" />
                    </div>
                    <div>
                        <p className="text-[10px] text-gray-500 uppercase font-bold tracking-wider">Active Opts</p>
                        <p className="font-bold text-lg text-gray-900">{status?.active_optimization_count}</p>
                    </div>
                </div>

            </div>
        </header>
    );
};

export default Header;
