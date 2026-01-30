import React, { useState } from 'react';
import { FiLock, FiAlertCircle } from 'react-icons/fi';
import { Button } from '../shared';
import { api } from '../../services/api';
import toast from 'react-hot-toast';

const AccessRequestModal = ({ isOpen, onClose, resourceName, actionType, onSuccess }) => {
    const [reason, setReason] = useState('');
    const [duration, setDuration] = useState(1);
    const [loading, setLoading] = useState(false);

    if (!isOpen) return null;

    const handleSubmit = async (e) => {
        e.preventDefault();
        setLoading(true);
        try {
            // Create ticket
            await api.post('/api/v1/tickets', {
                title: `Request Access: ${resourceName}`,
                description: `Requesting permission to ${actionType} ${resourceName}`,
                type: 'ACTION', // or ACCESS_WINDOW depending on model. Using ACTION for specific capability.
                action_type: actionType, // e.g. "CONNECT_AWS_ACCOUNT"
                reason_category: 'MAINTENANCE', // Default
                reason_text: reason,
                duration_hours: duration,
                resource_id: 'GLOBAL' // Account connection is global usually
            });

            toast.success('Access request submitted successfully');
            if (onSuccess) onSuccess();
            onClose();
        } catch (error) {
            console.error(error);
            toast.error('Failed to submit request');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
            <div className="absolute inset-0 bg-gray-900/50 backdrop-blur-sm" onClick={onClose} />

            <div className="relative bg-white rounded-2xl shadow-xl p-6 max-w-md w-full mx-4 border border-gray-100">
                <div className="flex items-start gap-4 mb-6">
                    <div className="p-3 bg-amber-100 rounded-full text-amber-600">
                        <FiLock className="w-6 h-6" />
                    </div>
                    <div>
                        <h2 className="text-xl font-bold text-gray-900">Access Restricted</h2>
                        <p className="text-gray-500 text-sm mt-1">
                            You don't have permission to <strong>{resourceName}</strong>.
                        </p>
                    </div>
                </div>

                <div className="bg-gray-50 p-4 rounded-lg mb-6 text-sm text-gray-700 border border-gray-200">
                    <p className="flex items-center gap-2 mb-2 font-semibold">
                        <FiAlertCircle className="text-blue-500" />
                        JIT Access
                    </p>
                    <p>
                        You can request temporary access. Your Team Lead will review this ticket.
                        Once approved, you will have a <strong>{duration} hour</strong> window to perform this action.
                    </p>
                </div>

                <form onSubmit={handleSubmit}>
                    <div className="mb-4">
                        <label className="block text-sm font-medium text-gray-700 mb-1">Reason for Access</label>
                        <textarea
                            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:outline-none"
                            rows="3"
                            placeholder="Why do you need this access?"
                            value={reason}
                            onChange={(e) => setReason(e.target.value)}
                            required
                        />
                    </div>

                    <div className="mb-6">
                        <label className="block text-sm font-medium text-gray-700 mb-1">Duration (Hours)</label>
                        <select
                            value={duration}
                            onChange={(e) => setDuration(parseInt(e.target.value))}
                            className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                        >
                            <option value={1}>1 Hour</option>
                            <option value={4}>4 Hours</option>
                            <option value={24}>24 Hours</option>
                        </select>
                    </div>

                    <div className="flex gap-3 justify-end">
                        <Button variant="ghost" onClick={onClose} type="button">Cancel</Button>
                        <Button variant="primary" type="submit" isLoading={loading}>Request Access</Button>
                    </div>
                </form>
            </div>
        </div>
    );
};

export default AccessRequestModal;
