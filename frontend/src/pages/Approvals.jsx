import React, { useState, useEffect } from 'react';
import { approvalsAPI } from '../services/api';
import { useAuthStore } from '../store/useStore';
import { Card, Button } from '../components/shared';
import { formatDistanceToNow, format } from 'date-fns';
import TicketRequestModal from '../components/approvals/TicketRequestModal';
import ActiveJITBanner from '../components/governance/ActiveJITBanner';
import RiskBadge from '../components/shared/RiskBadge';
import toast from 'react-hot-toast';
import { Shield, Clock, AlertTriangle } from 'lucide-react';

const Approvals = () => {
    const { user } = useAuthStore();

    // Include CLIENT role as ORG_ADMIN equivalent
    const isOrgAdmin = user?.role === 'ORG_ADMIN' || user?.role === 'SUPER_ADMIN' || user?.role === 'CLIENT';
    const isTeamLead = user?.role === 'TEAM_LEAD';
    const isMember = user?.role === 'MEMBER';

    const [activeTab, setActiveTab] = useState('incoming');
    const [tickets, setTickets] = useState([]);
    const [loading, setLoading] = useState(false);
    const [showModal, setShowModal] = useState(false);

    useEffect(() => {
        // Set default tab based on role on mount
        if (isOrgAdmin) setActiveTab('queue');
        else if (isTeamLead) setActiveTab('incoming');
        else setActiveTab('my_requests');
    }, [isOrgAdmin, isTeamLead]);

    useEffect(() => {
        fetchTickets();
    }, []);

    const fetchTickets = async () => {
        setLoading(true);
        try {
            const res = await approvalsAPI.list();
            console.log('Tickets API Response:', res.data); // Debug log
            setTickets(Array.isArray(res.data) ? res.data : []);
        } catch (err) {
            console.error('Failed to fetch tickets:', err);
            toast.error('Failed to load tickets');
        } finally {
            setLoading(false);
        }
    };

    const handleApprove = async (id) => {
        try {
            await approvalsAPI.approve(id);
            toast.success("Ticket Approved");
            fetchTickets();
        } catch (err) {
            console.error('Approve error:', err);
            toast.error(err.response?.data?.detail || "Failed to approve");
        }
    };

    const handleRevoke = async (id) => {
        if (!window.confirm("Are you sure you want to revoke access immediately?")) return;
        try {
            await approvalsAPI.revoke(id);
            toast.success("Access Revoked");
            fetchTickets();
        } catch (err) {
            toast.error("Failed to revoke");
        }
    };

    const handleAccept = async (id) => {
        try {
            await approvalsAPI.acceptGrant(id);
            toast.success("Access Granted & Timer Started");
            fetchTickets();
        } catch (err) {
            toast.error("Failed to accept grant");
        }
    };

    const handleReject = async (id) => {
        if (!window.confirm("Decline this access grant?")) return;
        try {
            await approvalsAPI.rejectGrant(id);
            toast.success("Grant Declined");
            fetchTickets();
        } catch (err) {
            toast.error("Failed to decline");
        }
    };

    const getStatusColor = (status) => {
        switch (status) {
            case 'APPROVED_ACTIVE': return 'bg-green-100 text-green-800';
            case 'PENDING': return 'bg-yellow-100 text-yellow-800';
            case 'PENDING_CONSENT': return 'bg-purple-100 text-purple-800 border border-purple-200';
            case 'REVOKED': return 'bg-red-100 text-red-800';
            case 'EXPIRED': return 'bg-gray-100 text-gray-800';
            case 'REJECTED': return 'bg-gray-200 text-gray-600';
            default: return 'bg-gray-100 text-gray-800';
        }
    };

    const getStatusLabel = (status) => {
        switch (status) {
            case 'APPROVED_ACTIVE': return 'Active';
            case 'PENDING': return 'Pending Approval';
            case 'PENDING_CONSENT': return 'Awaiting Consent';
            case 'REVOKED': return 'Revoked';
            case 'EXPIRED': return 'Expired';
            case 'REJECTED': return 'Rejected';
            default: return status;
        }
    };

    // Get display tickets based on active tab
    const getDisplayTickets = () => {
        switch (activeTab) {
            case 'queue':
                // Admin: All PENDING tickets (requests awaiting approval)
                return tickets.filter(t => t.status === 'PENDING');
            case 'active_grants':
                // Admin: All ACTIVE tickets in the org (not just ones they approved)
                return tickets.filter(t => ['APPROVED_ACTIVE', 'PENDING_CONSENT'].includes(t.status));
            case 'incoming':
                // Team Lead: PENDING tickets from their team (not their own)
                return tickets.filter(t => t.status === 'PENDING' && t.user_id !== user?.id);
            case 'active_team_access':
                // Team Lead: Active tickets in their team
                return tickets.filter(t => t.status === 'APPROVED_ACTIVE' && t.user_id !== user?.id);
            case 'outgoing':
            case 'my_requests':
                // All tickets created by the current user
                return tickets.filter(t => t.user_id === user?.id);
            default:
                return [];
        }
    };

    const displayTickets = getDisplayTickets();

    // Format time remaining for active tickets
    const getTimeRemaining = (expiresAt) => {
        if (!expiresAt) return null;
        const now = new Date();
        const expires = new Date(expiresAt);
        if (expires <= now) return 'Expired';
        return formatDistanceToNow(expires, { addSuffix: true });
    };

    return (
        <div className="space-y-6">
            {/* Active JIT Banner */}
            <ActiveJITBanner />

            <div className="flex justify-between items-center">
                <div>
                    <div className="flex items-center space-x-3">
                        <Shield className="h-8 w-8 text-blue-600" />
                        <div>
                            <h1 className="text-2xl font-bold text-gray-900">
                                {isOrgAdmin ? 'Access Governance' : 'Ticket Center'}
                            </h1>
                            <p className="text-sm text-gray-500 mt-1">
                                {isOrgAdmin ? 'Manage JIT access requests and active grants' : 'Manage your access requests'}
                            </p>
                        </div>
                    </div>
                </div>
                <Button onClick={() => setShowModal(true)}>
                    {isOrgAdmin ? '+ Grant Access' : (isTeamLead ? '+ Manage Access' : '+ Request Access')}
                </Button>
            </div>

            {/* Pending Grants Alert (For Receiver) */}
            {tickets.filter(t => t.user_id === user?.id && t.status === 'PENDING_CONSENT').length > 0 && (
                <div className="bg-gradient-to-r from-purple-50 to-indigo-50 border border-purple-200 rounded-xl p-6">
                    <h3 className="text-lg font-bold text-purple-900 mb-4 flex items-center">
                        <span className="bg-purple-600 text-white rounded-full w-6 h-6 flex items-center justify-center text-xs mr-2">
                            {tickets.filter(t => t.user_id === user?.id && t.status === 'PENDING_CONSENT').length}
                        </span>
                        Action Required: Pending Grants
                    </h3>
                    <div className="grid gap-4">
                        {tickets.filter(t => t.user_id === user?.id && t.status === 'PENDING_CONSENT').map(grant => (
                            <div key={grant.id} className="bg-white p-4 rounded-lg shadow-sm border border-purple-100 flex justify-between items-center">
                                <div>
                                    <p className="font-medium text-gray-900">
                                        You have been granted <strong>{grant.type === 'ACTION' ? grant.action_type : 'Access Window'}</strong>
                                    </p>
                                    <p className="text-sm text-gray-500">
                                        Duration: {grant.duration_hours}h • {grant.reason_category}: {grant.reason_text}
                                    </p>
                                </div>
                                <div className="flex space-x-3">
                                    <Button variant="outline" size="sm" onClick={() => handleReject(grant.id)}>Decline</Button>
                                    <Button size="sm" onClick={() => handleAccept(grant.id)}>Accept & Start</Button>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* Stats Summary */}
            {isOrgAdmin && (
                <div className="grid grid-cols-3 gap-4">
                    <div className="bg-yellow-50 rounded-xl p-4 border border-yellow-100">
                        <div className="text-2xl font-bold text-yellow-700">
                            {tickets.filter(t => t.status === 'PENDING').length}
                        </div>
                        <div className="text-sm text-yellow-600">Pending Requests</div>
                    </div>
                    <div className="bg-green-50 rounded-xl p-4 border border-green-100">
                        <div className="text-2xl font-bold text-green-700">
                            {tickets.filter(t => t.status === 'APPROVED_ACTIVE').length}
                        </div>
                        <div className="text-sm text-green-600">Active Grants</div>
                    </div>
                    <div className="bg-purple-50 rounded-xl p-4 border border-purple-100">
                        <div className="text-2xl font-bold text-purple-700">
                            {tickets.filter(t => t.status === 'PENDING_CONSENT').length}
                        </div>
                        <div className="text-sm text-purple-600">Awaiting Consent</div>
                    </div>
                </div>
            )}

            {/* Tabs */}
            <div className="border-b border-gray-200">
                <nav className="-mb-px flex space-x-8">
                    {/* Admin Tabs */}
                    {isOrgAdmin && (
                        <>
                            <button
                                onClick={() => setActiveTab('queue')}
                                className={`${activeTab === 'queue' ? 'border-indigo-500 text-indigo-600' : 'border-transparent text-gray-500 hover:text-gray-700'} whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm transition-colors`}
                            >
                                Pending Requests
                                {tickets.filter(t => t.status === 'PENDING').length > 0 && (
                                    <span className="ml-2 bg-yellow-100 text-yellow-800 px-2 py-0.5 rounded-full text-xs">
                                        {tickets.filter(t => t.status === 'PENDING').length}
                                    </span>
                                )}
                            </button>
                            <button
                                onClick={() => setActiveTab('active_grants')}
                                className={`${activeTab === 'active_grants' ? 'border-indigo-500 text-indigo-600' : 'border-transparent text-gray-500 hover:text-gray-700'} whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm transition-colors`}
                            >
                                Active Grants
                                {tickets.filter(t => ['APPROVED_ACTIVE', 'PENDING_CONSENT'].includes(t.status)).length > 0 && (
                                    <span className="ml-2 bg-green-100 text-green-800 px-2 py-0.5 rounded-full text-xs">
                                        {tickets.filter(t => ['APPROVED_ACTIVE', 'PENDING_CONSENT'].includes(t.status)).length}
                                    </span>
                                )}
                            </button>
                        </>
                    )}

                    {/* Team Lead Tabs */}
                    {isTeamLead && (
                        <>
                            <button
                                onClick={() => setActiveTab('incoming')}
                                className={`${activeTab === 'incoming' ? 'border-indigo-500 text-indigo-600' : 'border-transparent text-gray-500 hover:text-gray-700'} whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm transition-colors`}
                            >
                                Incoming Requests
                            </button>
                            <button
                                onClick={() => setActiveTab('active_team_access')}
                                className={`${activeTab === 'active_team_access' ? 'border-indigo-500 text-indigo-600' : 'border-transparent text-gray-500 hover:text-gray-700'} whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm transition-colors`}
                            >
                                Active Team Access
                            </button>
                            <button
                                onClick={() => setActiveTab('outgoing')}
                                className={`${activeTab === 'outgoing' ? 'border-indigo-500 text-indigo-600' : 'border-transparent text-gray-500 hover:text-gray-700'} whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm transition-colors`}
                            >
                                My Outgoing Requests
                            </button>
                        </>
                    )}

                    {/* Member Tabs */}
                    {isMember && (
                        <button
                            onClick={() => setActiveTab('my_requests')}
                            className={`${activeTab === 'my_requests' ? 'border-indigo-500 text-indigo-600' : 'border-transparent text-gray-500 hover:text-gray-700'} whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm transition-colors`}
                        >
                            My Requests
                        </button>
                    )}
                </nav>
            </div>

            {/* Loading State */}
            {loading && (
                <div className="text-center py-8">
                    <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-500"></div>
                    <p className="text-gray-500 mt-2">Loading tickets...</p>
                </div>
            )}

            {/* Table */}
            {!loading && (
                <Card className="overflow-hidden">
                    <div className="overflow-x-auto">
                        <table className="min-w-full divide-y divide-gray-200">
                            <thead className="bg-gray-50">
                                <tr>
                                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Type</th>
                                    {isOrgAdmin && <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Requester</th>}
                                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Reason</th>
                                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Duration</th>
                                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Status</th>
                                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Created</th>
                                    {activeTab === 'active_grants' && <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Expires</th>}
                                    <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
                                </tr>
                            </thead>
                            <tbody className="bg-white divide-y divide-gray-200">
                                {displayTickets.length === 0 ? (
                                    <tr>
                                        <td colSpan={isOrgAdmin ? 8 : 7} className="px-6 py-12 text-center">
                                            <div className="text-gray-400">
                                                <svg className="mx-auto h-12 w-12 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
                                                </svg>
                                                <p className="text-sm font-medium">No tickets found</p>
                                                <p className="text-xs mt-1">
                                                    {activeTab === 'queue' ? 'No pending access requests' :
                                                        activeTab === 'active_grants' ? 'No active grants at this time' :
                                                            'You have no tickets in this view'}
                                                </p>
                                            </div>
                                        </td>
                                    </tr>
                                ) : displayTickets.map(ticket => (
                                    <tr key={ticket.id} className="hover:bg-gray-50 transition-colors">
                                        <td className="px-6 py-4">
                                            <div className="flex items-center space-x-2">
                                                <span className={`w-2 h-2 rounded-full flex-shrink-0 ${
                                                    ticket.type === 'JIT_FEATURE' ? 'bg-purple-500' :
                                                    ticket.type === 'ACTION' ? 'bg-orange-400' : 'bg-blue-400'
                                                }`}></span>
                                                <div>
                                                    <div className="text-sm font-medium text-gray-900">
                                                        {ticket.type === 'JIT_FEATURE' && ticket.feature_id ? (
                                                            <div className="flex items-center space-x-2">
                                                                <span>{ticket.feature_id}</span>
                                                                {ticket.jit_metadata?.risk_level && (
                                                                    <RiskBadge level={ticket.jit_metadata.risk_level} />
                                                                )}
                                                            </div>
                                                        ) : ticket.type === 'ACTION' ? (ticket.action_type || 'Action') : 'Access Window'}
                                                    </div>
                                                    {ticket.resource_id && (
                                                        <div className="text-xs text-gray-400 font-mono mt-0.5 truncate max-w-[150px]" title={ticket.resource_id}>
                                                            {ticket.resource_id}
                                                        </div>
                                                    )}
                                                </div>
                                            </div>
                                        </td>
                                        {isOrgAdmin && (
                                            <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                                                <div className="font-medium text-gray-800">{ticket.user_id?.substring(0, 8)}...</div>
                                            </td>
                                        )}
                                        <td className="px-6 py-4">
                                            <span className={`inline-block px-2 py-0.5 text-xs rounded-full mb-1 ${ticket.reason_category === 'INCIDENT' ? 'bg-red-100 text-red-700' :
                                                    ticket.reason_category === 'MAINTENANCE' ? 'bg-blue-100 text-blue-700' :
                                                        ticket.reason_category === 'COST_OPT' ? 'bg-green-100 text-green-700' :
                                                            'bg-gray-100 text-gray-700'
                                                }`}>
                                                {ticket.reason_category}
                                            </span>
                                            <div className="text-sm text-gray-500 max-w-[200px] truncate" title={ticket.reason_text}>
                                                {ticket.reason_text || '-'}
                                            </div>
                                        </td>
                                        <td className="px-6 py-4 whitespace-nowrap">
                                            <span className="text-sm font-semibold text-gray-900">{ticket.duration_hours}h</span>
                                        </td>
                                        <td className="px-6 py-4 whitespace-nowrap">
                                            <span className={`px-2.5 py-1 inline-flex text-xs leading-5 font-semibold rounded-full ${getStatusColor(ticket.status)}`}>
                                                {getStatusLabel(ticket.status)}
                                            </span>
                                        </td>
                                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                                            <div>{formatDistanceToNow(new Date(ticket.created_at))} ago</div>
                                            <div className="text-xs text-gray-400">
                                                {format(new Date(ticket.created_at), 'MMM d, HH:mm')}
                                            </div>
                                        </td>
                                        {activeTab === 'active_grants' && (
                                            <td className="px-6 py-4 whitespace-nowrap text-sm">
                                                {ticket.expires_at ? (
                                                    <span className={`font-medium ${new Date(ticket.expires_at) > new Date() ? 'text-green-600' : 'text-red-600'}`}>
                                                        {getTimeRemaining(ticket.expires_at)}
                                                    </span>
                                                ) : (
                                                    <span className="text-gray-400">-</span>
                                                )}
                                            </td>
                                        )}
                                        <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium space-x-2">
                                            {/* Approve (Lead/Admin) logic */}
                                            {ticket.status === 'PENDING' && (isOrgAdmin || isTeamLead) && (activeTab === 'queue' || activeTab === 'incoming') && (
                                                <Button size="sm" onClick={() => handleApprove(ticket.id)}>Approve</Button>
                                            )}

                                            {/* Revoke (Admin/Lead) logic for Active items */}
                                            {['APPROVED_ACTIVE', 'PENDING_CONSENT'].includes(ticket.status) && (isOrgAdmin || isTeamLead) && (activeTab === 'active_grants' || activeTab === 'active_team_access') && (
                                                <Button size="sm" variant="danger" onClick={() => handleRevoke(ticket.id)}>Revoke</Button>
                                            )}

                                            {/* Accept (Receiver) logic */}
                                            {ticket.status === 'PENDING_CONSENT' && ticket.user_id === user?.id && (
                                                <Button size="sm" onClick={() => handleAccept(ticket.id)}>Accept</Button>
                                            )}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </Card>
            )}

            <TicketRequestModal
                isOpen={showModal}
                onClose={() => { setShowModal(false); fetchTickets(); }}
            />
        </div>
    );
};

export default Approvals;
