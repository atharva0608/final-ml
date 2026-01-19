/**
 * Pending Approvals Card Widget
 * Shows tickets awaiting action
 */
import React from 'react';
import { FiAlertCircle, FiClock, FiUser } from 'react-icons/fi';

const PendingApprovalsCard = ({ data = {}, widgetKey }) => {
    const tickets = data.tickets || [
        { id: 1, requester: 'john@example.com', type: 'ACCESS_WINDOW', duration: '4 hours', created: '2h ago' },
        { id: 2, requester: 'jane@example.com', type: 'ACTION', resource: 'i-abc123', created: '5h ago' }
    ];

    return (
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 hover:shadow-md transition-shadow">
            <div className="flex items-center justify-between mb-4">
                <div>
                    <h3 className="text-lg font-semibold text-gray-900">Pending Approvals</h3>
                    <p className="text-sm text-gray-500">{tickets.length} awaiting action</p>
                </div>
                <div className="p-2 bg-amber-50 rounded-lg">
                    <FiAlertCircle className="w-5 h-5 text-amber-600" />
                </div>
            </div>

            {tickets.length === 0 ? (
                <div className="text-center py-8 text-gray-500">
                    <FiAlertCircle className="w-8 h-8 mx-auto mb-2 text-gray-300" />
                    <p>No pending approvals</p>
                </div>
            ) : (
                <div className="space-y-3">
                    {tickets.slice(0, 3).map((ticket) => (
                        <div key={ticket.id} className="flex items-start justify-between p-3 bg-amber-50 rounded-lg border border-amber-100">
                            <div className="flex items-start gap-3">
                                <FiUser className="w-4 h-4 text-amber-600 mt-0.5" />
                                <div>
                                    <p className="text-sm font-medium text-gray-900">{ticket.requester}</p>
                                    <p className="text-xs text-gray-600">{ticket.type} · {ticket.duration || ticket.resource}</p>
                                </div>
                            </div>
                            <span className="text-xs text-gray-500">{ticket.created}</span>
                        </div>
                    ))}
                    {tickets.length > 3 && (
                        <p className="text-sm text-center text-blue-600 cursor-pointer hover:underline">
                            View all {tickets.length} requests
                        </p>
                    )}
                </div>
            )}
        </div>
    );
};

export default PendingApprovalsCard;
