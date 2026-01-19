/**
 * Cluster Health Card Widget
 * Shows cluster status summary
 */
import React from 'react';
import { FiServer, FiCheckCircle, FiAlertTriangle, FiXCircle } from 'react-icons/fi';

const ClusterHealthCard = ({ data = {}, widgetKey }) => {
    const clusters = data.clusters || [
        { name: 'prod-cluster', status: 'healthy', nodes: 12 },
        { name: 'staging-cluster', status: 'warning', nodes: 6 },
        { name: 'dev-cluster', status: 'healthy', nodes: 3 }
    ];

    const getStatusIcon = (status) => {
        switch (status) {
            case 'healthy': return <FiCheckCircle className="w-4 h-4 text-green-500" />;
            case 'warning': return <FiAlertTriangle className="w-4 h-4 text-amber-500" />;
            case 'critical': return <FiXCircle className="w-4 h-4 text-red-500" />;
            default: return <FiServer className="w-4 h-4 text-gray-400" />;
        }
    };

    const healthyClusters = clusters.filter(c => c.status === 'healthy').length;

    return (
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 hover:shadow-md transition-shadow">
            <div className="flex items-center justify-between mb-4">
                <div>
                    <h3 className="text-lg font-semibold text-gray-900">Cluster Health</h3>
                    <p className="text-sm text-gray-500">{healthyClusters}/{clusters.length} clusters healthy</p>
                </div>
                <div className="p-2 bg-cyan-50 rounded-lg">
                    <FiServer className="w-5 h-5 text-cyan-600" />
                </div>
            </div>

            <div className="space-y-3">
                {clusters.map((cluster, idx) => (
                    <div key={idx} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                        <div className="flex items-center gap-3">
                            {getStatusIcon(cluster.status)}
                            <span className="font-medium text-gray-900">{cluster.name}</span>
                        </div>
                        <span className="text-sm text-gray-500">{cluster.nodes} nodes</span>
                    </div>
                ))}
            </div>
        </div>
    );
};

export default ClusterHealthCard;
