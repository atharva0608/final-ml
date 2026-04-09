/**
 * Cluster Delete Modal Component
 * Confirmation modal for permanently deleting clusters
 */
import React, { useState } from 'react';
import { FiX, FiAlertTriangle } from 'react-icons/fi';
import { FaAws } from 'react-icons/fa';

const ClusterDeleteModal = ({ isOpen, onClose, cluster, onConfirm }) => {
    const [confirmName, setConfirmName] = useState('');
    const [loading, setLoading] = useState(false);

    if (!isOpen || !cluster) return null;

    const isNameMatch = confirmName === cluster.name;

    const handleDelete = async () => {
        if (!isNameMatch) return;
        setLoading(true);
        try {
            await onConfirm(cluster.id);
            onClose();
            setConfirmName(''); // Reset on success
        } catch (error) {
            console.error('Delete failed:', error);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
            <div className="bg-white rounded-xl shadow-2xl max-w-md w-full mx-4 overflow-hidden">
                {/* Header */}
                <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100 bg-red-50">
                    <div className="flex items-center gap-3">
                        <div className="w-8 h-8 bg-red-100 rounded-full flex items-center justify-center">
                            <FiAlertTriangle className="w-4 h-4 text-red-600" />
                        </div>
                        <span className="font-semibold text-gray-900">Delete Cluster</span>
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
                    <div className="flex items-start gap-3 mb-4">
                        <FaAws className="w-5 h-5 text-gray-400 mt-0.5" />
                        <div>
                            <h3 className="font-semibold text-gray-900 mb-1">{cluster.name}</h3>
                            <p className="text-sm text-gray-600">{cluster.region}</p>
                        </div>
                    </div>

                    <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-6">
                        <div className="flex items-start gap-2">
                            <FiAlertTriangle className="w-5 h-5 text-red-600 mt-0.5" />
                            <div>
                                <h4 className="text-sm font-semibold text-red-900 mb-1">
                                    This action cannot be undone
                                </h4>
                                <p className="text-sm text-red-700 mb-2">
                                    This will permanently delete the cluster and:
                                </p>
                                <ul className="text-sm text-red-700 space-y-1 ml-4">
                                    <li>• Remove the Balancekube agent from Kubernetes</li>
                                    <li>• Delete the balancekube namespace and all resources</li>
                                    <li>• Remove cluster data from our database</li>
                                    <li>• Delete all metrics history</li>
                                </ul>
                                <p className="text-sm text-red-700 mt-2 font-medium">
                                    Note: The cluster will reappear as "Discovered" after the next scan if it still exists in your AWS account.
                                </p>
                            </div>
                        </div>
                    </div>

                    {/* Confirmation Input */}
                    <div>
                        <h3 className="text-sm font-semibold text-gray-900 mb-2">Confirmation</h3>
                        <p className="text-sm text-gray-600 mb-3">
                            Type <span className="font-mono font-semibold text-gray-900">{cluster.name}</span> to confirm deletion
                        </p>
                        <input
                            type="text"
                            value={confirmName}
                            onChange={(e) => setConfirmName(e.target.value)}
                            placeholder={cluster.name}
                            className="w-full px-4 py-2.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent"
                            autoComplete="off"
                        />
                    </div>
                </div>

                {/* Footer */}
                <div className="flex justify-end gap-3 px-6 py-4 border-t border-gray-100 bg-gray-50">
                    <button
                        onClick={onClose}
                        disabled={loading}
                        className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors disabled:opacity-50"
                    >
                        Cancel
                    </button>
                    <button
                        onClick={handleDelete}
                        disabled={!isNameMatch || loading}
                        className={`px-4 py-2 text-sm font-medium text-white rounded-lg transition-colors ${
                            isNameMatch && !loading
                                ? 'bg-red-600 hover:bg-red-700'
                                : 'bg-gray-300 cursor-not-allowed'
                        }`}
                    >
                        {loading ? 'Deleting...' : 'Delete Cluster'}
                    </button>
                </div>
            </div>
        </div>
    );
};

export default ClusterDeleteModal;
