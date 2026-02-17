import React, { useState } from 'react';
import { FiAlertTriangle, FiCheck, FiX, FiInfo } from 'react-icons/fi';
import api from '../../services/api';

const BatchApplyModal = ({ isOpen, onClose, selectedInstances, onSuccess, clusterId }) => {
    const [isApplying, setIsApplying] = useState(false);
    const [result, setResult] = useState(null);

    if (!isOpen) return null;

    const handleConfirm = async () => {
        setIsApplying(true);
        try {
            const instanceIds = selectedInstances.map(i => i.instance_id);
            const response = await api.post('/optimization/rightsizing/batch-apply', {
                instance_ids: instanceIds,
                cluster_id: clusterId
            });
            setResult({
                success: true,
                message: response.data.message || 'Successfully applied changes.'
            });
            setTimeout(() => {
                onSuccess();
                onClose();
            }, 2000);
        } catch (error) {
            console.error("Batch apply failed:", error);
            setResult({
                success: false,
                message: error.response?.data?.message || 'Failed to apply changes.'
            });
        } finally {
            setIsApplying(false);
        }
    };

    return (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
            <div className="bg-white rounded-lg shadow-xl max-w-md w-full p-6 animate-fade-in">
                <h3 className="text-lg font-bold text-gray-900 mb-2">Confirm Bulk Optimization</h3>

                {!result ? (
                    <>
                        <div className="bg-yellow-50 border border-yellow-200 rounded-md p-3 mb-4 flex items-start gap-3">
                            <FiAlertTriangle className="text-yellow-600 w-5 h-5 flex-shrink-0 mt-0.5" />
                            <div className="text-sm text-yellow-800">
                                <p className="font-medium">You are about to modify {selectedInstances.length} resources.</p>
                                <p className="mt-1 text-xs">This action may trigger restarts for instances that require resizing. Ensure applications are fault-tolerant.</p>
                            </div>
                        </div>

                        <ul className="max-h-40 overflow-y-auto border border-gray-100 rounded-md mb-4 bg-gray-50 p-2 text-xs space-y-1">
                            {selectedInstances.map(inst => (
                                <li key={inst.instance_id} className="flex justify-between">
                                    <span className="font-mono text-gray-600">{inst.instance_id}</span>
                                    <span className="text-gray-500">{inst.instance_type} → {inst.recommendation.split('to ')[1]}</span>
                                </li>
                            ))}
                        </ul>

                        <div className="flex justify-end gap-3">
                            <button
                                onClick={onClose}
                                disabled={isApplying}
                                className="px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 rounded-md"
                            >
                                Cancel
                            </button>
                            <button
                                onClick={handleConfirm}
                                disabled={isApplying}
                                className="px-4 py-2 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 flex items-center gap-2"
                            >
                                {isApplying ? 'Applying...' : 'Confirm & Apply'}
                            </button>
                        </div>
                    </>
                ) : (
                    <div className="text-center py-4">
                        {result.success ? (
                            <div className="flex flex-col items-center text-green-600">
                                <div className="w-12 h-12 rounded-full bg-green-100 flex items-center justify-center mb-2">
                                    <FiCheck className="w-6 h-6" />
                                </div>
                                <p className="font-medium">{result.message}</p>
                            </div>
                        ) : (
                            <div className="flex flex-col items-center text-red-600">
                                <div className="w-12 h-12 rounded-full bg-red-100 flex items-center justify-center mb-2">
                                    <FiX className="w-6 h-6" />
                                </div>
                                <p className="font-medium">{result.message}</p>
                                <button onClick={() => setResult(null)} className="mt-4 text-sm text-gray-600 underline">Try Again</button>
                            </div>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
};

export default BatchApplyModal;
