import React, { useState, useEffect } from 'react';
import { Card, Button } from '../shared';
import { FiCpu, FiAlertTriangle, FiUpload, FiMap, FiActivity, FiRefreshCw } from 'react-icons/fi';
import { labAPI } from '../../services/api';
import toast from 'react-hot-toast';
import { formatRelativeTime } from '../../utils/formatters';

const AdminLab = () => {
    const [experiments, setExperiments] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        fetchExperiments();
    }, []);

    const fetchExperiments = async () => {
        try {
            setLoading(true);
            const response = await labAPI.listExperiments();
            setExperiments(response.data.items || []);
        } catch (error) {
            console.error('Failed to load experiments:', error);
            // toast.error('Failed to load lab data'); // Optional: don't spam errors
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="space-y-6">
            <div className="flex justify-between items-center">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900">The Lab (AI & Intelligence)</h1>
                    <p className="text-gray-600">Manage ML models and Global Risk parameters</p>
                </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Model Registry (Real Data) */}
                <Card className="p-6">
                    <div className="flex justify-between items-center mb-6">
                        <div className="flex items-center space-x-3">
                            <div className="p-3 bg-purple-100 rounded-lg">
                                <FiCpu className="w-6 h-6 text-purple-600" />
                            </div>
                            <div>
                                <h2 className="text-lg font-bold text-gray-900">Model Registry</h2>
                                <p className="text-sm text-gray-500">Manage Spot Stability Models</p>
                            </div>
                        </div>
                        <Button variant="outline" size="sm" onClick={fetchExperiments} icon={<FiRefreshCw className={loading ? "animate-spin" : ""} />}>Refresh</Button>
                    </div>

                    <div className="space-y-4">
                        {loading ? (
                            <p className="text-center text-gray-500 py-4">Loading models...</p>
                        ) : experiments.length === 0 ? (
                            <p className="text-center text-gray-500 py-4">No active experiments found.</p>
                        ) : (
                            experiments.map((exp, i) => (
                                <div key={exp.id} className="flex items-center justify-between p-4 border rounded-lg hover:border-purple-200 transition-colors">
                                    <div className="flex items-center space-x-4">
                                        <div className={`w-2 h-2 rounded-full ${exp.status === 'RUNNING' ? 'bg-green-500' : 'bg-yellow-500'}`} />
                                        <div>
                                            <h3 className="font-semibold text-gray-900">{exp.name}</h3>
                                            <p className="text-xs text-gray-500">Created: {formatRelativeTime(exp.created_at)}</p>
                                        </div>
                                    </div>
                                    <div className="flex items-center space-x-6">
                                        <span className={`px-2 py-1 text-xs font-medium rounded-full ${exp.status === 'RUNNING' ? 'bg-green-100 text-green-700' : 'bg-yellow-100 text-yellow-700'
                                            }`}>
                                            {exp.status}
                                        </span>
                                        <Button size="sm" variant="ghost">Details</Button>
                                    </div>
                                </div>
                            ))
                        )}
                    </div>
                </Card>

                {/* Global Risk Map */}
                <Card className="p-6">
                    <div className="flex justify-between items-center mb-6">
                        <div className="flex items-center space-x-3">
                            <div className="p-3 bg-red-100 rounded-lg">
                                <FiMap className="w-6 h-6 text-red-600" />
                            </div>
                            <div>
                                <h2 className="text-lg font-bold text-gray-900">Global Risk Map</h2>
                                <p className="text-sm text-gray-500">AWS Region Stability Heatmap</p>
                            </div>
                        </div>
                    </div>

                    <div className="bg-gray-100 rounded-lg aspect-video flex items-center justify-center mb-4 relative overflow-hidden">
                        {/* Placeholder for Map Visualization */}
                        <div className="absolute inset-0 bg-blue-50 opacity-50"></div>
                        <div className="text-center relative z-10">
                            <FiActivity className="w-8 h-8 text-gray-400 mx-auto mb-2" />
                            <p className="text-sm text-gray-500">Interactive Map Visualization</p>
                        </div>

                        {/* Mock High Risk Zone */}
                        <div className="absolute top-1/3 left-1/4 w-12 h-12 bg-red-500 rounded-full opacity-20 animate-pulse"></div>
                    </div>

                    <div className="space-y-3">
                        <h3 className="font-semibold text-sm text-gray-700">High Risk Zones (Auto-detected)</h3>
                        <div className="flex items-center justify-between p-3 bg-red-50 border border-red-100 rounded text-sm">
                            <span className="flex items-center font-medium text-red-700">
                                <FiAlertTriangle className="mr-2" /> us-east-1a
                            </span>
                            <span className="text-red-600">High Interruptions detected</span>
                            <Button size="sm" variant="danger">Cordone AZ</Button>
                        </div>
                    </div>
                </Card>
            </div>
        </div>
    );
};

export default AdminLab;
