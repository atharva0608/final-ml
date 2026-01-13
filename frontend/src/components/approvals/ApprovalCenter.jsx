import React, { useState, useEffect } from 'react';
import { approvalsAPI } from '../../services/api';
import { Badge, Button, Card } from '../shared';
import { FiCheck, FiX, FiRefreshCw, FiAlertCircle } from 'react-icons/fi';
import toast from 'react-hot-toast';

const ApprovalCenter = () => {
    const [requests, setRequests] = useState([]);
    const [loading, setLoading] = useState(true);

    const fetchRequests = async () => {
        setLoading(true);
        try {
            const res = await approvalsAPI.listPending();
            setRequests(res.data || []);
        } catch (err) {
            console.error("Failed to load approvals", err);
            // toast.error("Failed to load approval requests");
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchRequests();
    }, []);

    const handleDecision = async (id, decision) => { // decision = 'approve' | 'reject'
        try {
            if (decision === 'approve') {
                await approvalsAPI.approve(id);
            } else {
                await approvalsAPI.reject(id, "Rejected by user"); // Simple reject for now
            }
            toast.success(`Request ${decision}ed successfully`);
            fetchRequests();
        } catch (err) {
            console.error(err);
            toast.error(err.response?.data?.detail || "Action failed");
        }
    };

    return (
        <div className="p-6 space-y-6 bg-gray-50 min-h-screen">
            <div className="flex justify-between items-center">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900">Approval Center</h1>
                    <p className="text-sm text-gray-500">Review and authorize critical actions (Four-Eyes Principle)</p>
                </div>
                <Button variant="secondary" onClick={fetchRequests} disabled={loading}>
                    <FiRefreshCw className={`mr-2 ${loading ? 'animate-spin' : ''}`} /> Refresh
                </Button>
            </div>

            {loading && requests.length === 0 ? (
                <div className="flex justify-center p-12">
                    <FiRefreshCw className="animate-spin text-gray-400 w-8 h-8" />
                </div>
            ) : requests.length === 0 ? (
                <div className="text-center py-16 bg-white rounded-lg border border-dashed border-gray-300">
                    <FiCheck className="mx-auto h-12 w-12 text-green-100 bg-green-500 rounded-full p-2 mb-4" />
                    <h3 className="text-lg font-medium text-gray-900">All Caught Up!</h3>
                    <p className="text-gray-500">No pending approvals required at this time.</p>
                </div>
            ) : (
                <div className="grid gap-4">
                    {requests.map(req => (
                        <Card key={req.id} className="p-4 border-l-4 border-l-yellow-400">
                            <div className="flex flex-col md:flex-row justify-between gap-4">
                                <div className="space-y-2">
                                    <div className="flex items-center gap-2">
                                        <Badge variant="warning">Pending Approval</Badge>
                                        <span className="text-xs text-gray-500 font-mono">ID: {req.id.slice(0, 8)}</span>
                                    </div>

                                    <h3 className="text-lg font-bold text-gray-900">
                                        {req.action.replace('_', ' ')} on {req.resource_type}
                                    </h3>

                                    <div className="text-sm text-gray-600">
                                        Requested by <span className="font-semibold text-indigo-600">{req.requester?.email || 'Unknown User'}</span>
                                        {' '} on {new Date(req.created_at).toLocaleString()}
                                    </div>

                                    <div className="bg-gray-50 p-3 rounded text-xs font-mono border border-gray-200 mt-2 max-w-2xl overflow-x-auto">
                                        <pre>{JSON.stringify(req.execution_payload, null, 2)}</pre>
                                    </div>
                                </div>

                                <div className="flex flex-row md:flex-col justify-center gap-2 min-w-[120px]">
                                    <Button variant="danger" size="sm" onClick={() => handleDecision(req.id, 'reject')} className="justify-center">
                                        <FiX className="mr-1" /> Reject
                                    </Button>
                                    <Button variant="primary" size="sm" onClick={() => handleDecision(req.id, 'approve')} className="justify-center">
                                        <FiCheck className="mr-1" /> Approve
                                    </Button>
                                </div>
                            </div>
                        </Card>
                    ))}
                </div>
            )}
        </div>
    );
};

export default ApprovalCenter;
