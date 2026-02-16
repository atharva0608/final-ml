import React, { useState } from 'react';
import { FiCpu, FiServer, FiSettings, FiCheck, FiShield, FiTarget, FiDollarSign } from 'react-icons/fi';

const NodeConfiguration = () => {
    const [activeTab, setActiveTab] = useState('templates');
    const [selectedStrategy, setSelectedStrategy] = useState('balanced');

    return (
        <div className="bg-white rounded-xl border border-gray-200 p-5 h-full flex flex-col shadow-sm">
            <div className="flex justify-between items-center mb-6">
                <h2 className="text-lg font-semibold flex items-center gap-2 text-gray-900">
                    <FiServer className="text-purple-600" /> Node Configuration
                </h2>
                <button className="text-xs bg-white hover:bg-gray-50 px-3 py-1.5 rounded transition-colors flex items-center gap-1 border border-gray-300 text-gray-700 shadow-sm">
                    <FiSettings className="text-gray-500" /> Manage
                </button>
            </div>

            {/* Tabs */}
            <div className="flex bg-gray-100 p-1 rounded-lg mb-6 border border-gray-200">
                <button
                    onClick={() => setActiveTab('templates')}
                    className={`flex-1 text-sm font-medium py-1.5 rounded-md transition-all ${activeTab === 'templates' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'
                        }`}
                >
                    Templates
                </button>
                <button
                    onClick={() => setActiveTab('allocation')}
                    className={`flex-1 text-sm font-medium py-1.5 rounded-md transition-all ${activeTab === 'allocation' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'
                        }`}
                >
                    Allocation
                </button>
            </div>

            {/* Content Area */}
            <div className="flex-1 space-y-6">
                {/* Visual Strategy Selector */}
                <div>
                    <label className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-3 block">Optimization Strategy</label>
                    <div className="grid grid-cols-3 gap-3">
                        <div
                            onClick={() => setSelectedStrategy('safe')}
                            className={`cursor-pointer p-3 rounded-lg border-2 text-center transition-all ${selectedStrategy === 'safe'
                                    ? 'border-green-500 bg-green-50'
                                    : 'border-gray-200 bg-white hover:border-gray-300 hover:bg-gray-50'
                                }`}>
                            <div className="text-lg mb-1 flex justify-center text-green-600"><FiShield /></div>
                            <div className="text-xs font-bold text-gray-700">Safety First</div>
                        </div>
                        <div
                            onClick={() => setSelectedStrategy('balanced')}
                            className={`cursor-pointer p-3 rounded-lg border-2 text-center transition-all ${selectedStrategy === 'balanced'
                                    ? 'border-blue-500 bg-blue-50'
                                    : 'border-gray-200 bg-white hover:border-gray-300 hover:bg-gray-50'
                                }`}>
                            <div className="text-lg mb-1 flex justify-center text-blue-600"><FiTarget /></div>
                            <div className="text-xs font-bold text-gray-700">Balanced</div>
                        </div>
                        <div
                            onClick={() => setSelectedStrategy('cheap')}
                            className={`cursor-pointer p-3 rounded-lg border-2 text-center transition-all ${selectedStrategy === 'cheap'
                                    ? 'border-yellow-500 bg-yellow-50'
                                    : 'border-gray-200 bg-white hover:border-gray-300 hover:bg-gray-50'
                                }`}>
                            <div className="text-lg mb-1 flex justify-center text-yellow-600"><FiDollarSign /></div>
                            <div className="text-xs font-bold text-gray-700">Lowest Cost</div>
                        </div>
                    </div>
                </div>

                {/* Resource Sliders (Mock) */}
                <div className="space-y-4">
                    <label className="text-xs font-bold text-gray-500 uppercase tracking-wider block">Resource Constraints</label>

                    <div className="bg-gray-50 p-4 rounded-lg border border-gray-200 space-y-4">
                        <div>
                            <div className="flex justify-between text-xs mb-1">
                                <span className="text-gray-500">Min vCPU</span>
                                <span className="text-gray-900 font-mono font-medium">2 vCPU</span>
                            </div>
                            <div className="h-1.5 bg-gray-200 rounded-full overflow-hidden">
                                <div className="h-full bg-blue-500 w-[20%]"></div>
                            </div>
                        </div>
                        <div>
                            <div className="flex justify-between text-xs mb-1">
                                <span className="text-gray-500">Min Memory</span>
                                <span className="text-gray-900 font-mono font-medium">4 GiB</span>
                            </div>
                            <div className="h-1.5 bg-gray-200 rounded-full overflow-hidden">
                                <div className="h-full bg-purple-500 w-[35%]"></div>
                            </div>
                        </div>
                    </div>
                </div>

                {/* Active Template Preview */}
                <div className="bg-white rounded-lg p-3 border border-gray-200 flex items-center justify-between shadow-sm">
                    <div className="flex items-center gap-3">
                        <div className="p-2 bg-gray-100 rounded text-gray-600">
                            <FiCpu />
                        </div>
                        <div>
                            <div className="text-sm font-bold text-gray-900">General Purpose</div>
                            <div className="text-xs text-gray-500">m5, m6i, t3 families</div>
                        </div>
                    </div>
                    <FiCheck className="text-green-500" />
                </div>

            </div>
        </div>
    );
};

export default NodeConfiguration;
