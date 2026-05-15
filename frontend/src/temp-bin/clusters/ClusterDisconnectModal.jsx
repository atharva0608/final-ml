/**
 * Cluster Disconnect Modal Component
 * CAST AI-style confirmation modal for disconnecting clusters
 */
import React, { useState } from 'react';
import { FiX, FiAlertTriangle } from 'react-icons/fi';
import { FaAws } from 'react-icons/fa';

const ClusterDisconnectModal = ({ isOpen, onClose, cluster, onConfirm }) => {
    const [confirmName, setConfirmName] = useState('');
    const [deleteNodes, setDeleteNodes] = useState(false);
    const [loading, setLoading] = useState(false);

    if (!isOpen || !cluster) return null;

    const isNameMatch = confirmName === cluster.name;

    const handleDisconnect = async () => {
        if (!isNameMatch) return;
        setLoading(true);
        try {
            await onConfirm(cluster.id, deleteNodes);
            onClose();
        } catch (error) {
            console.error('Disconnect failed:', error);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
            <div className="bg-white rounded-xl shadow-2xl max-w-md w-full mx-4 overflow-hidden">
                {/* Header */}
                <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
                    <div className="flex items-center gap-3">
                        <div className="w-8 h-8 bg-orange-100 rounded-full flex items-center justify-center">
                            <FaAws className="w-4 h-4 text-orange-500" />
                        </div>
                        <span className="font-semibold text-gray-900">{cluster.name}</span>
                    </div>
                    <button
                        onClick={onClose}
                        className="text-gray-400 hover:text-gray-600 transition-colors"
                    >
                        <FiX className="w-5 h-5" />
                    </button>
                </div>

                {/* Body */}
                <div className="px-6 py-5">
                    <h2 className="text-xl font-bold text-gray-900 mb-2">Disconnect your cluster</h2>
                    <p className="text-sm text-gray-600 mb-6">
                        This action will remove all Balancekube resources managing your cluster.
                        Please go to AWS IAM and delete it manually.{' '}
                        <a href="#" className="text-blue-600 hover:underline">Full list of resources</a>
                    </p>

                    {/* Confirmation Input */}
                    <div className="mb-6">
                        <h3 className="text-sm font-semibold text-gray-900 mb-2">Confirmation</h3>
                        <p className="text-sm text-gray-600 mb-3">
                            Please confirm that you want to disconnect from Balancekube by entering the cluster name below.
                        </p>
                        <div className="mb-2">
                            <span className="text-xs text-gray-400">{cluster.name}</span>
                        </div>
                        <input
                            type="text"
                            value={confirmName}
                            onChange={(e) => setConfirmName(e.target.value)}
                            placeholder={cluster.name}
                            className="w-full px-4 py-2.5 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                        />
                    </div>

                    {/* Delete Nodes Checkbox */}
                    <div className="bg-gray-50 rounded-lg p-4 mb-6">
                        <label className="flex items-start gap-3 cursor-pointer">
                            <input
                                type="checkbox"
                                checked={deleteNodes}
                                onChange={(e) => setDeleteNodes(e.target.checked)}
                                className="mt-0.5 w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                            />
                            <div className="flex-1">
                                <div className="flex items-center gap-2 mb-1">
                                    <span className="text-sm font-semibold text-gray-900">
                                        Delete all Balancekube created nodes
                                    </span>
                                    <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-amber-100 text-amber-700 text-xs font-medium rounded">
                                        <FiAlertTriangle className="w-3 h-3" />
                                        Might cause downtime
                                    </span>
                                </div>
                                <p className="text-xs text-gray-500">
                                    All optimized nodes will be drained and deleted. Depending on your application configuration this action might cause downtime.
                                </p>
                            </div>
                        </label>
                    </div>
                </div>

                {/* Footer */}
                <div className="flex justify-end gap-3 px-6 py-4 border-t border-gray-100 bg-gray-50">
                    <button
                        onClick={onClose}
                        className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
                    >
                        Cancel
                    </button>
                    <button
                        onClick={handleDisconnect}
                        disabled={!isNameMatch || loading}
                        className={`px-4 py-2 text-sm font-medium text-white rounded-lg transition-colors ${isNameMatch && !loading
                                ? 'bg-blue-600 hover:bg-blue-700'
                                : 'bg-gray-300 cursor-not-allowed'
                            }`}
                    >
                        {loading ? 'Disconnecting...' : 'Disconnect'}
                    </button>
                </div>
            </div>
        </div>
    );
};

export default ClusterDisconnectModal;
