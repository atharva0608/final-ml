import React, { useState, useEffect } from 'react';
import { useAuthStore } from '../../store/useStore';
import { organizationAPI, ticketsAPI } from '../../services/api';
import { Button } from '../shared';
import toast from 'react-hot-toast';

const TicketRequestModal = ({ isOpen, onClose, initialData }) => {
    const { user } = useAuthStore();

    const isOrgAdmin = user?.role === 'ORG_ADMIN' || user?.role === 'SUPER_ADMIN';
    const isTeamLead = user?.role === 'TEAM_LEAD';
    const isMember = user?.role === 'MEMBER';

    const [loading, setLoading] = useState(false);
    const [membersLoading, setMembersLoading] = useState(false);
    const [isGrantMode, setIsGrantMode] = useState(isOrgAdmin);
    const [members, setMembers] = useState([]);
    const [selectedRecipients, setSelectedRecipients] = useState([]);

    useEffect(() => {
        if (initialData) {
            setIsGrantMode(false);
        } else {
            if (isOrgAdmin) {
                setIsGrantMode(true);
            } else if (isTeamLead) {
                setIsGrantMode(false);
            } else {
                setIsGrantMode(false);
            }
        }
    }, [initialData, isOpen, isOrgAdmin, isTeamLead]);

    const [formData, setFormData] = useState({
        type: 'ACCESS_WINDOW',
        reason_category: 'MAINTENANCE',
        reason_text: '',
        duration_hours: 1,
        action_type: '',
        resource_id: ''
    });

    useEffect(() => {
        if (initialData) {
            setIsGrantMode(false);
            setFormData(prev => ({
                ...prev,
                type: 'ACTION',
                action_type: initialData.action || '',
                resource_id: initialData.resource_id || '',
                reason_text: `Requesting access to ${initialData.action} on ${initialData.resource_id}`
            }));
        } else {
            setFormData({
                type: 'ACCESS_WINDOW',
                reason_category: 'MAINTENANCE',
                reason_text: '',
                duration_hours: 1,
                action_type: '',
                resource_id: ''
            });
            setSelectedRecipients([]);
        }
    }, [initialData, isOpen]);

    // Fetch members when entering Grant Mode
    useEffect(() => {
        if (isGrantMode && isOpen && members.length === 0) {
            setMembersLoading(true);
            organizationAPI.getMembers().then(res => {
                // Backend returns { members: [...], total: int }
                let allMembers = res.data?.members || [];

                // Fallback checks
                if (!Array.isArray(allMembers)) {
                    allMembers = Array.isArray(res.data) ? res.data : [];
                }

                // If Team Lead, filter to team members only
                if (isTeamLead && user?.team_id) {
                    allMembers = allMembers.filter(m => m.team_id === user.team_id);
                }
                setMembers(allMembers);
            }).catch(err => {
                console.error('Failed to load members:', err);
                toast.error('Failed to load team members');
            }).finally(() => {
                setMembersLoading(false);
            });
        }
    }, [isGrantMode, isOpen, isTeamLead, user?.team_id, members.length]);

    const handleSubmit = async (e) => {
        e.preventDefault();
        setLoading(true);
        try {
            if (isGrantMode) {
                if (selectedRecipients.length === 0) {
                    toast.error("Please select at least one recipient");
                    setLoading(false);
                    return;
                }
                const payload = {
                    ...formData,
                    recipient_ids: selectedRecipients,
                };
                await ticketsAPI.grantAccess(payload);
                toast.success(`Access granted to ${selectedRecipients.length} user(s)`);
            } else {
                await ticketsAPI.create(formData);
                toast.success("Access request submitted successfully!");
            }
            onClose();
        } catch (err) {
            toast.error("Failed to submit request");
            console.error(err);
        } finally {
            setLoading(false);
        }
    };

    const toggleRecipient = (memberId) => {
        if (selectedRecipients.includes(memberId)) {
            setSelectedRecipients(selectedRecipients.filter(id => id !== memberId));
        } else {
            setSelectedRecipients([...selectedRecipients, memberId]);
        }
    };

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-[60] p-4">
            <div className="w-full max-w-xl bg-white rounded-2xl shadow-2xl relative max-h-[90vh] overflow-hidden flex flex-col">
                {/* Header */}
                <div className={`px-6 py-5 ${isGrantMode ? 'bg-gradient-to-r from-emerald-500 to-teal-600' : 'bg-gradient-to-r from-indigo-500 to-purple-600'}`}>
                    <div className="flex justify-between items-center">
                        <div className="flex items-center space-x-3">
                            <div className="w-10 h-10 rounded-full bg-white/20 flex items-center justify-center">
                                <span className="text-xl">{isGrantMode ? '🗝️' : '🔒'}</span>
                            </div>
                            <div>
                                <h2 className="text-xl font-bold text-white">
                                    {isGrantMode ? 'Grant Access' : 'Request Access'}
                                </h2>
                                <p className="text-white/80 text-sm">
                                    {isGrantMode ? 'Delegate permissions to team members' : 'Submit a request for elevated privileges'}
                                </p>
                            </div>
                        </div>
                        <button
                            onClick={onClose}
                            className="text-white/70 hover:text-white transition-colors p-1"
                        >
                            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                            </svg>
                        </button>
                    </div>

                    {/* Toggle for Team Leads */}
                    {isTeamLead && !initialData && (
                        <div className="mt-4 flex items-center space-x-2">
                            <button
                                type="button"
                                onClick={() => setIsGrantMode(false)}
                                className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${!isGrantMode ? 'bg-white text-indigo-700' : 'bg-white/20 text-white hover:bg-white/30'}`}
                            >
                                Request from Admin
                            </button>
                            <button
                                type="button"
                                onClick={() => setIsGrantMode(true)}
                                className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${isGrantMode ? 'bg-white text-emerald-700' : 'bg-white/20 text-white hover:bg-white/30'}`}
                            >
                                Grant to Team
                            </button>
                        </div>
                    )}
                </div>

                {/* Body */}
                <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto p-6 space-y-5">
                    {/* Grant Mode: Recipient Selection */}
                    {isGrantMode && (
                        <div>
                            <label className="block text-sm font-semibold text-gray-700 mb-2">
                                Select Recipients
                                {selectedRecipients.length > 0 && (
                                    <span className="ml-2 px-2 py-0.5 bg-emerald-100 text-emerald-700 rounded-full text-xs">
                                        {selectedRecipients.length} selected
                                    </span>
                                )}
                            </label>
                            <div className="border-2 border-gray-100 rounded-xl max-h-48 overflow-y-auto bg-gray-50">
                                {membersLoading ? (
                                    <div className="p-4 text-center">
                                        <div className="inline-block animate-spin rounded-full h-6 w-6 border-b-2 border-emerald-500"></div>
                                        <p className="text-sm text-gray-500 mt-2">Loading team members...</p>
                                    </div>
                                ) : members.length === 0 ? (
                                    <div className="p-4 text-center text-gray-500 text-sm">
                                        No team members found
                                    </div>
                                ) : (
                                    <div className="divide-y divide-gray-100">
                                        {members.map(member => (
                                            <label
                                                key={member.id}
                                                className={`flex items-center p-3 cursor-pointer transition-colors ${selectedRecipients.includes(member.id)
                                                        ? 'bg-emerald-50'
                                                        : 'hover:bg-gray-100'
                                                    }`}
                                            >
                                                <input
                                                    type="checkbox"
                                                    checked={selectedRecipients.includes(member.id)}
                                                    onChange={() => toggleRecipient(member.id)}
                                                    className="w-4 h-4 rounded border-gray-300 text-emerald-600 focus:ring-emerald-500"
                                                />
                                                <div className="ml-3 flex-1">
                                                    <p className="text-sm font-medium text-gray-900">
                                                        {member.full_name || member.email.split('@')[0]}
                                                    </p>
                                                    <p className="text-xs text-gray-500">{member.email}</p>
                                                </div>
                                                <span className={`text-xs px-2 py-0.5 rounded-full ${member.role === 'ORG_ADMIN' ? 'bg-purple-100 text-purple-700' :
                                                        member.role === 'TEAM_LEAD' ? 'bg-blue-100 text-blue-700' :
                                                            'bg-gray-100 text-gray-600'
                                                    }`}>
                                                    {member.role}
                                                </span>
                                            </label>
                                        ))}
                                    </div>
                                )}
                            </div>
                        </div>
                    )}

                    {/* Read Only Details (Interceptor Mode) */}
                    {!isGrantMode && formData.action_type && (
                        <div className="grid grid-cols-2 gap-4 bg-gradient-to-r from-indigo-50 to-purple-50 p-4 rounded-xl border border-indigo-100">
                            <div>
                                <label className="text-xs font-semibold text-indigo-600 uppercase tracking-wide">Action</label>
                                <div className="font-mono text-sm font-medium text-gray-900 mt-1">{formData.action_type}</div>
                            </div>
                            <div>
                                <label className="text-xs font-semibold text-indigo-600 uppercase tracking-wide">Resource</label>
                                <div className="font-mono text-sm font-medium text-gray-900 mt-1 truncate" title={formData.resource_id}>{formData.resource_id}</div>
                            </div>
                        </div>
                    )}

                    {/* Grant Mode: Type Selection */}
                    {isGrantMode && (
                        <div>
                            <label className="block text-sm font-semibold text-gray-700 mb-2">Access Type</label>
                            <select
                                className="w-full px-4 py-2.5 rounded-xl border-2 border-gray-200 focus:border-emerald-500 focus:ring-2 focus:ring-emerald-200 transition-all text-sm bg-white"
                                value={formData.type}
                                onChange={e => setFormData({ ...formData, type: e.target.value })}
                            >
                                <option value="ACCESS_WINDOW">⏱️ Full Access Window (Time Bound)</option>
                                <option value="ACTION">🎯 Specific Action Only</option>
                            </select>
                        </div>
                    )}

                    {/* Action/Resource inputs for Manual Grant */}
                    {isGrantMode && formData.type === 'ACTION' && (
                        <div className="grid grid-cols-2 gap-4">
                            <div>
                                <label className="block text-sm font-semibold text-gray-700 mb-2">Action Name</label>
                                <input
                                    type="text"
                                    className="w-full px-4 py-2.5 rounded-xl border-2 border-gray-200 focus:border-emerald-500 focus:ring-2 focus:ring-emerald-200 transition-all text-sm"
                                    placeholder="e.g. TERMINATE_INSTANCE"
                                    value={formData.action_type}
                                    onChange={e => setFormData({ ...formData, action_type: e.target.value })}
                                />
                            </div>
                            <div>
                                <label className="block text-sm font-semibold text-gray-700 mb-2">Resource ID</label>
                                <input
                                    type="text"
                                    className="w-full px-4 py-2.5 rounded-xl border-2 border-gray-200 focus:border-emerald-500 focus:ring-2 focus:ring-emerald-200 transition-all text-sm"
                                    placeholder="e.g. i-123456"
                                    value={formData.resource_id}
                                    onChange={e => setFormData({ ...formData, resource_id: e.target.value })}
                                />
                            </div>
                        </div>
                    )}

                    {/* Reason Category */}
                    <div>
                        <label className="block text-sm font-semibold text-gray-700 mb-2">Reason Category</label>
                        <select
                            className={`w-full px-4 py-2.5 rounded-xl border-2 border-gray-200 ${isGrantMode ? 'focus:border-emerald-500 focus:ring-emerald-200' : 'focus:border-indigo-500 focus:ring-indigo-200'} focus:ring-2 transition-all text-sm bg-white`}
                            value={formData.reason_category}
                            onChange={e => setFormData({ ...formData, reason_category: e.target.value })}
                        >
                            <option value="MAINTENANCE">🔧 Maintenance</option>
                            <option value="COST_OPT">💰 Cost Optimization</option>
                            <option value="INCIDENT">🚨 Incident Response</option>
                            <option value="TESTING">🧪 Testing</option>
                            <option value="OTHER">📋 Other</option>
                        </select>
                    </div>

                    {/* Justification */}
                    <div>
                        <label className="block text-sm font-semibold text-gray-700 mb-2">Justification</label>
                        <textarea
                            required
                            className={`w-full px-4 py-3 rounded-xl border-2 border-gray-200 ${isGrantMode ? 'focus:border-emerald-500 focus:ring-emerald-200' : 'focus:border-indigo-500 focus:ring-indigo-200'} focus:ring-2 transition-all text-sm resize-none`}
                            rows={3}
                            value={formData.reason_text}
                            onChange={e => setFormData({ ...formData, reason_text: e.target.value })}
                            placeholder={isGrantMode ? "Why are you granting this access?" : "Why do you need this access?"}
                        />
                    </div>

                    {/* Duration */}
                    <div>
                        <label className="block text-sm font-semibold text-gray-700 mb-2">Duration</label>
                        <div className="flex items-center space-x-3">
                            <input
                                type="range"
                                min="1"
                                max="72"
                                className={`flex-1 h-2 rounded-lg appearance-none cursor-pointer ${isGrantMode ? 'accent-emerald-500' : 'accent-indigo-500'}`}
                                value={formData.duration_hours}
                                onChange={e => setFormData({ ...formData, duration_hours: parseInt(e.target.value) })}
                            />
                            <div className={`px-4 py-2 rounded-xl font-bold text-lg ${isGrantMode ? 'bg-emerald-100 text-emerald-700' : 'bg-indigo-100 text-indigo-700'}`}>
                                {formData.duration_hours}h
                            </div>
                        </div>
                        <div className="flex justify-between text-xs text-gray-400 mt-1 px-1">
                            <span>1 hour</span>
                            <span>72 hours</span>
                        </div>
                    </div>
                </form>

                {/* Footer */}
                <div className="px-6 py-4 bg-gray-50 border-t border-gray-100 flex justify-end space-x-3">
                    <Button variant="secondary" onClick={onClose} type="button">
                        Cancel
                    </Button>
                    <button
                        onClick={handleSubmit}
                        disabled={loading}
                        className={`px-6 py-2.5 rounded-xl font-semibold text-white transition-all disabled:opacity-50 ${isGrantMode
                                ? 'bg-gradient-to-r from-emerald-500 to-teal-600 hover:from-emerald-600 hover:to-teal-700 shadow-lg shadow-emerald-200'
                                : 'bg-gradient-to-r from-indigo-500 to-purple-600 hover:from-indigo-600 hover:to-purple-700 shadow-lg shadow-indigo-200'
                            }`}
                    >
                        {loading ? (
                            <span className="flex items-center space-x-2">
                                <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                                </svg>
                                <span>Processing...</span>
                            </span>
                        ) : (
                            isGrantMode ? '🗝️ Grant Access' : '📨 Submit Request'
                        )}
                    </button>
                </div>
            </div>
        </div>
    );
};

export default TicketRequestModal;
