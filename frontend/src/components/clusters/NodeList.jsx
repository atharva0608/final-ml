import React, { useState, useEffect } from 'react';
import { Card, Badge, Button } from '../shared';
import { FiCpu, FiServer, FiActivity } from 'react-icons/fi';
import { clusterAPI } from '../../services/api';
import { formatDateTime } from '../../utils/formatters';

const NodeList = ({ clusterId }) => {
    const [nodes, setNodes] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    useEffect(() => {
        fetchNodes();
    }, [clusterId]);

    const fetchNodes = async () => {
        try {
            setError(null);
            setLoading(true);
            const response = await clusterAPI.getNodes(clusterId);
            setNodes(response.data.nodes || []);
        } catch (err) {
            console.error('Failed to fetch nodes', err);
            setError(err.message || 'Failed to load nodes');
            setNodes([]);
        } finally {
            setLoading(false);
        }
    };

    const getLifecycleColor = (lifecycle) => {
        return lifecycle === 'SPOT' ? 'green' : 'blue';
    };

    if (loading) {
        return <div className="text-center py-4">Loading nodes...</div>;
    }

    if (error) {
        return (
            <Card>
                <div className="flex flex-col items-center justify-center py-8 px-4">
                    <div className="p-3 bg-red-50 rounded-full mb-3">
                        <FiActivity className="w-6 h-6 text-red-500" />
                    </div>
                    <p className="text-sm font-medium text-gray-900 mb-1">Failed to load nodes</p>
                    <p className="text-xs text-gray-500 mb-4">{error}</p>
                    <button
                        onClick={fetchNodes}
                        className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 transition-colors"
                    >
                        Retry
                    </button>
                </div>
            </Card>
        );
    }

    if (nodes.length === 0) {
        return (
            <Card>
                <div className="flex flex-col items-center justify-center py-8 px-4">
                    <div className="p-3 bg-gray-100 rounded-full mb-3">
                        <FiServer className="w-6 h-6 text-gray-400" />
                    </div>
                    <p className="text-sm font-medium text-gray-900 mb-1">No nodes found</p>
                    <p className="text-xs text-gray-500">No node data is available for this cluster yet.</p>
                </div>
            </Card>
        );
    }

    return (
        <Card>
            <div className="flex justify-between items-center mb-4">
                <h3 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
                    <FiServer className="w-5 h-5" />
                    Node List
                </h3>
                <Badge color="gray">{nodes.length} Nodes</Badge>
            </div>

            <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200">
                    <thead className="bg-gray-50">
                        <tr>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Instance ID</th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Type</th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Lifecycle</th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">CPU %</th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Zone</th>
                        </tr>
                    </thead>
                    <tbody className="bg-white divide-y divide-gray-200">
                        {nodes.map((node) => (
                            <tr key={node.id}>
                                <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">{node.id}</td>
                                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{node.type}</td>
                                <td className="px-6 py-4 whitespace-nowrap">
                                    <Badge color={getLifecycleColor(node.lifecycle)}>{node.lifecycle}</Badge>
                                </td>
                                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                                    <div className="flex items-center">
                                        <div className="w-16 bg-gray-200 rounded-full h-2 mr-2">
                                            <div className={`h-2 rounded-full ${node.cpu_util > 80 ? 'bg-red-500' : 'bg-green-500'}`} style={{ width: `${node.cpu_util}%` }}></div>
                                        </div>
                                        {node.cpu_util}%
                                    </div>
                                </td>
                                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{node.az}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </Card>
    );
};

export default NodeList;
