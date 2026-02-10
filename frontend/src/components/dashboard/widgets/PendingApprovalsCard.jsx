/**
 * Pending Approvals Card Widget
 * Shows tickets awaiting action from real API data
 */
import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { FiAlertCircle, FiClock, FiUser } from 'react-icons/fi';
import { approvalsAPI } from '../../../services/api';
import { useAuthStore } from '../../../store/useStore';
import { formatDistanceToNow } from 'date-fns';

const PendingApprovalsCard = ({ data = {}, widgetKey }) => {
    const navigate = useNavigate();
    const { user } = useAuthStore();
    const [tickets, setTickets] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        fetchTickets();
    }, []);

    const fetchTickets = async () => {
        try {
            const res = await approvalsAPI.list();
            const allTickets = Array.isArray(res.data) ? res.data : [];

            // Filter based on user role
            let filteredTickets = allTickets;

            // Show PENDING tickets for admins and team leads
            if (user?.role === 'ORG_ADMIN' || user?.role === 'SUPER_ADMIN' || user?.role === 'CLIENT') {
                filteredTickets = allTickets.filter(t => t.status === 'PENDING');
            } else if (user?.role === 'TEAM_LEAD') {
                // Show pending tickets from team members (not their own)
                filteredTickets = allTickets.filter(t => t.status === 'PENDING' && t.user_id !== user?.id);
            } else {
                // Members see their own requests
                filteredTickets = allTickets.filter(t => t.user_id === user?.id);
            }

            setTickets(filteredTickets);
        } catch (err) {
            console.error('Failed to fetch tickets:', err);
        } finally {
            setLoading(false);
        }
    };

    const getStatusColor = (status) => {
        switch (status) {
            case 'APPROVED_ACTIVE': return 'bg-green-50 border-green-200 text-green-700';
            case 'PENDING': return 'bg-amber-50 border-amber-200 text-amber-700';
            case 'EXPIRED': return 'bg-gray-50 border-gray-200 text-gray-500';
            default: return 'bg-amber-50 border-amber-200 text-amber-700';
        }
    };

    if (loading) {
        return (
            <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
                <div className="animate-pulse space-y-3">
                    <div className="h-4 bg-gray-200 rounded w-1/3"></div>
                    <div className="h-12 bg-gray-200 rounded"></div>
                    <div className="h-12 bg-gray-200 rounded"></div>
                </div>
            </div>
        );
    }

    return (
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 hover:shadow-md transition-shadow">
            <div className="flex items-center justify-between mb-4">
                <div>
                    <h3 className="text-lg font-semibold text-gray-900">
                        {user?.role === 'MEMBER' ? 'My Requests' : 'Pending Approvals'}
                    </h3>
                    <p className="text-sm text-gray-500">
                        {tickets.length} {user?.role === 'MEMBER' ? 'active' : 'awaiting action'}
                    </p>
                </div>
                <div className="p-2 bg-amber-50 rounded-lg">
                    <FiAlertCircle className="w-5 h-5 text-amber-600" />
                </div>
            </div>

            {tickets.length === 0 ? (
                <div className="text-center py-8 text-gray-500">
                    <FiAlertCircle className="w-8 h-8 mx-auto mb-2 text-gray-300" />
                    <p className="text-sm">
                        {user?.role === 'MEMBER' ? 'No active requests' : 'No pending approvals'}
                    </p>
                </div>
            ) : (
                <div className="space-y-3">
                    {tickets.slice(0, 3).map((ticket) => (
                        <div
                            key={ticket.id}
                            className={`flex items-start justify-between p-3 rounded-lg border ${getStatusColor(ticket.status)} cursor-pointer hover:shadow-sm transition-shadow`}
                            onClick={() => navigate('/approvals')}
                        >
                            <div className="flex items-start gap-3 flex-1 min-w-0">
                                <FiUser className="w-4 h-4 text-amber-600 mt-0.5 flex-shrink-0" />
                                <div className="min-w-0 flex-1">
                                    <p className="text-sm font-medium text-gray-900 truncate">
                                        {ticket.type === 'JIT_FEATURE' ? ticket.feature_id : ticket.action_type || ticket.type}
                                    </p>
                                    <p className="text-xs text-gray-600">
                                        {ticket.duration_hours}h · {ticket.reason_category}
                                    </p>
                                </div>
                            </div>
                            <span className="text-xs text-gray-500 whitespace-nowrap ml-2">
                                {formatDistanceToNow(new Date(ticket.created_at), { addSuffix: true })}
                            </span>
                        </div>
                    ))}
                    {tickets.length > 3 && (
                        <button
                            onClick={() => navigate('/approvals')}
                            className="w-full text-sm text-center text-blue-600 cursor-pointer hover:underline py-2"
                        >
                            View all {tickets.length} requests →
                        </button>
                    )}
                </div>
            )}
        </div>
    );
};

export default PendingApprovalsCard;
