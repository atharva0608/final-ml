import React, { useState, useEffect } from 'react';
import { Card, Badge, Button } from '../shared';
import { FiCpu, FiServer, FiActivity } from 'react-icons/fi';
import { clusterAPI } from '../../services/api';
import { formatDateTime } from '../../utils/formatters';

const NodeList = ({ clusterId }) => {
    const [nodes, setNodes] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        fetchNodes();
    }, [clusterId]);

    const fetchNodes = async () => {
        try {
            const response = await clusterAPI.getNodes(clusterId);
            setNodes(response.data.nodes || []);
        } catch (error) {
            console.error('Failed to fetch nodes', error);
            // Mock data for now if API fails (since backend might not be ready)
            setNodes([
                { id: 'i-0123456789abcdef0', type: 'c5.large', lifecycle: 'SPOT', cpu_util: 45, memory_util: 60, az: 'us-east-1a', launch_time: new Date().toISOString() },
                { id: 'i-0abcdef1234567890', type: 'm5.large', lifecycle: 'ON_DEMAND', cpu_util: 12, memory_util: 30, az: 'us-east-1b', launch_time: new Date().toISOString() },
                { id: 'i-0987654321fedcba0', type: 'r5.xlarge', lifecycle: 'SPOT', cpu_util: 78, memory_util: 85, az: 'us-east-1a', launch_time: new Date().toISOString() },
            ]);
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
