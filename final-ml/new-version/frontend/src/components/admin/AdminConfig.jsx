import React, { useState } from 'react';
import { Card, Button } from '../shared';
import { FiSettings, FiShield, FiSave, FiAlertCircle, FiRefreshCw } from 'react-icons/fi';

const AdminConfig = () => {
    const [safeMode, setSafeMode] = useState(true);
    const [agentVersion, setAgentVersion] = useState('v1.4.2');

    return (
        <div className="space-y-6">
            <div className="flex justify-between items-center">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900">System Configuration</h1>
                    <p className="text-gray-600">The Engine Room - Control global variables</p>
                </div>
                <Button variant="primary" icon={<FiSave />}>Save Changes</Button>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Safety Switch */}
                <div className="lg:col-span-2">
                    <Card className="p-6">
                        <div className="flex items-start justify-between">
                            <div className="flex items-center space-x-4">
                                <div className={`p-3 rounded-lg ${safeMode ? 'bg-green-100' : 'bg-red-100'}`}>
                                    <FiShield className={`w-8 h-8 ${safeMode ? 'text-green-600' : 'text-red-600'}`} />
                                </div>
                                <div>
                                    <h2 className="text-xl font-bold text-gray-900">Global Safe Mode</h2>
                                    <p className="text-gray-500 mt-1">
                                        {safeMode
                                            ? "ON: Recommendations are generated but NO ACTIONS are taken (Dry Run)."
                                            : "OFF: The system is taking automated actions on client clusters."}
                                    </p>
                                </div>
                            </div>
                            <div className="flex items-center">
                                <label className="relative inline-flex items-center cursor-pointer">
                                    <input
                                        type="checkbox"
                                        className="sr-only peer"
                                        checked={safeMode}
                                        onChange={() => setSafeMode(!safeMode)}
                                    />
                                    <div className="w-14 h-7 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-blue-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-0.5 after:left-[4px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-6 after:w-6 after:transition-all peer-checked:bg-green-600"></div>
                                </label>
                            </div>
                        </div>
                    </Card>

                    <div className="mt-6">
                        <h3 className="text-lg font-semibold text-gray-900 mb-4">Risk Parameters</h3>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <Card className="p-6">
                                <label className="block text-sm font-medium text-gray-700 mb-2">Global Risk TTL (Minutes)</label>
                                <div className="flex items-center space-x-2">
                                    <input type="number" defaultValue={30} className="w-full border rounded p-2" />
                                    <span className="text-gray-400 text-sm">min</span>
                                </div>
                                <p className="text-xs text-gray-500 mt-2">Time an AZ remains "Dangerous" after interruption.</p>
                            </Card>
                            <Card className="p-6">
                                <label className="block text-sm font-medium text-gray-700 mb-2">Optimization Cooldown (Minutes)</label>
                                <div className="flex items-center space-x-2">
                                    <input type="number" defaultValue={60} className="w-full border rounded p-2" />
                                    <span className="text-gray-400 text-sm">min</span>
                                </div>
                                <p className="text-xs text-gray-500 mt-2">Minimum time between actions on same node group.</p>
                            </Card>
                        </div>
                    </div>
                </div>

                {/* Agent Version Control */}
                <div>
                    <Card className="p-6 h-full">
                        <div className="flex items-center space-x-3 mb-6">
                            <FiRefreshCw className="w-6 h-6 text-blue-600" />
                            <h2 className="text-lg font-bold text-gray-900">Agent Version</h2>
                        </div>

                        <div className="space-y-4">
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-2">Latest Stable Version</label>
                                <input
                                    type="text"
                                    value={agentVersion}
                                    onChange={(e) => setAgentVersion(e.target.value)}
                                    className="w-full border rounded p-2 text-sm"
                                />
                            </div>

                            <div className="p-4 bg-yellow-50 rounded text-sm text-yellow-800 border border-yellow-200">
                                <div className="flex items-start">
                                    <FiAlertCircle className="w-5 h-5 mr-2 flex-shrink-0" />
                                    <p>Updating this will trigger an "Update Available" badge on all active client dashboards.</p>
                                </div>
                            </div>

                            <Button variant="outline" className="w-full">Release New Version</Button>
                        </div>
                    </Card>
                </div>
            </div>
        </div>
    );
};

export default AdminConfig;
