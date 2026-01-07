import React from 'react';
import { Card, Button } from '../shared';
import { FiCpu, FiAlertTriangle, FiUpload, FiMap, FiActivity } from 'react-icons/fi';

const AdminLab = () => {
    return (
        <div className="space-y-6">
            <div className="flex justify-between items-center">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900">The Lab (AI & Intelligence)</h1>
                    <p className="text-gray-600">Manage ML models and Global Risk parameters</p>
                </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Model Registry */}
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
                        <Button variant="outline" icon={<FiUpload />}>Upload Model</Button>
                    </div>

                    <div className="space-y-4">
                        {[
                            { version: 'v1.2-beta', status: 'Shadow Mode', accuracy: '94%', last_trained: '2h ago' },
                            { version: 'v1.0 (Prod)', status: 'Active', accuracy: '91%', last_trained: '2d ago' },
                        ].map((model, i) => (
                            <div key={i} className="flex items-center justify-between p-4 border rounded-lg hover:border-purple-200 transition-colors">
                                <div className="flex items-center space-x-4">
                                    <div className={`w-2 h-2 rounded-full ${model.status === 'Active' ? 'bg-green-500' : 'bg-yellow-500'}`} />
                                    <div>
                                        <h3 className="font-semibold text-gray-900">{model.version}</h3>
                                        <p className="text-xs text-gray-500">Last trained: {model.last_trained}</p>
                                    </div>
                                </div>
                                <div className="flex items-center space-x-6">
                                    <div className="text-right">
                                        <p className="text-xs text-gray-500">Accuracy</p>
                                        <p className="font-medium text-gray-900">{model.accuracy}</p>
                                    </div>
                                    <span className={`px-2 py-1 text-xs font-medium rounded-full ${model.status === 'Active' ? 'bg-green-100 text-green-700' : 'bg-yellow-100 text-yellow-700'
                                        }`}>
                                        {model.status}
                                    </span>
                                    <Button size="sm" variant="ghost">Promote</Button>
                                </div>
                            </div>
                        ))}
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
