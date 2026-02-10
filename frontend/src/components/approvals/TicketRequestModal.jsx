import React, { useState, useEffect } from 'react';
import { useAuthStore } from '../../store/useStore';
import { organizationAPI, approvalsAPI, hygieneAPI, accountsAPI } from '../../services/api';
import { Button } from '../shared';
import toast from 'react-hot-toast';
import { FiShield, FiClock, FiCheck, FiX, FiSearch, FiAlertTriangle, FiUsers } from 'react-icons/fi';

const TicketRequestModal = ({ isOpen, onClose, initialData }) => {
    const { user } = useAuthStore();
    const [accounts, setAccounts] = useState([]);
    const [selectedAccountId, setSelectedAccountId] = useState('');
    const [discoveryLoading, setDiscoveryLoading] = useState(false);
    const [discoveredResources, setDiscoveredResources] = useState([]);
    const [showDiscovery, setShowDiscovery] = useState(false);

    // Fetch accounts on mount
    useEffect(() => {
        if (isOpen) {
            accountsAPI.list().then(res => {
                const accts = res.data?.items || res.data || [];
                setAccounts(accts);
                if (accts.length > 0 && !selectedAccountId) {
                    setSelectedAccountId(accts[0].aws_account_id || accts[0].id);
                }
            }).catch(err => console.error('Failed to load accounts', err));
        }
    }, [isOpen]);

    const handleDiscover = async () => {
        if (!selectedAccountId) {
            toast.error("Please select an account first");
            return;
        }

        // Map action name to resource type
        let resourceType = 'INSTANCE';
        const action = formData.action_type.toUpperCase();
        if (action.includes('VOLUME')) resourceType = 'VOLUME';
        if (action.includes('SNAPSHOT')) resourceType = 'SNAPSHOT';
        if (action.includes('RDS') || action.includes('DATABASE')) resourceType = 'RDS_DB';

        setDiscoveryLoading(true);
        try {
            const res = await hygieneAPI.discover(selectedAccountId, resourceType);
            setDiscoveredResources(res.data || []);
            setShowDiscovery(true);
            if (res.data?.length === 0) {
                toast.error(`No ${resourceType} resources found in this account`);
            }
        } catch (err) {
            console.error('Discovery failed', err);
            toast.error('Failed to discover resources. Make sure action name is valid.');
        } finally {
            setDiscoveryLoading(false);
        }
    };

    const selectDiscovered = (res) => {
        setFormData(prev => ({
            ...prev,
            resource_id: res.id,
            reason_text: prev.reason_text || `Action ${formData.action_type} for ${res.name || res.id} (${res.region})`
        }));
        setShowDiscovery(false);
    };

    const isOrgAdmin = user?.role === 'ORG_ADMIN' || user?.role === 'SUPER_ADMIN' || user?.role === 'CLIENT';
    const isTeamLead = user?.role === 'TEAM_LEAD';
    const isMember = user?.role === 'MEMBER';

    const [loading, setLoading] = useState(false);
    const [membersLoading, setMembersLoading] = useState(false);
    const [isGrantMode, setIsGrantMode] = useState(isOrgAdmin);
    const [members, setMembers] = useState([]);
    const [selectedRecipients, setSelectedRecipients] = useState([]);
    const [approvers, setApprovers] = useState([]);
    const [approversLoading, setApproversLoading] = useState(false);

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
                type: 'JIT_FEATURE',
                feature_id: initialData.action || '',
                action_type: initialData.action || '',
                resource_id: initialData.resource_id || '',
                reason_text: `Requesting access to ${initialData.action}${initialData.resource_id ? ` on ${initialData.resource_id}` : ''}`
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

    // Fetch approvers when in Request Mode
    useEffect(() => {
        if (!isGrantMode && isOpen && approvers.length === 0) {
            setApproversLoading(true);
            organizationAPI.getMembers().then(res => {
                let allMembers = res.data?.members || [];
                if (!Array.isArray(allMembers)) {
                    allMembers = Array.isArray(res.data) ? res.data : [];
                }

                // Filter to show only Team Leads and Org Admins who can approve
                const potentialApprovers = allMembers.filter(m =>
                    m.role === 'TEAM_LEAD' ||
                    m.role === 'ORG_ADMIN' ||
                    m.role === 'CLIENT' ||
                    m.role === 'SUPER_ADMIN'
                );

                setApprovers(potentialApprovers);
            }).catch(err => {
                console.error('Failed to load approvers:', err);
            }).finally(() => {
                setApproversLoading(false);
            });
        }
    }, [isGrantMode, isOpen, approvers.length]);

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
                await approvalsAPI.delegate(payload);
                toast.success(`Access granted to ${selectedRecipients.length} user(s)`);
            } else {
                // Check if this is a JIT Feature request
                if (formData.type === 'JIT_FEATURE' && formData.feature_id) {
                    const payload = {
                        feature_id: formData.feature_id,
                        reason_category: formData.reason_category,
                        reason_text: formData.reason_text,
                        duration_hours: formData.duration_hours,
                        resource_id: formData.resource_id || null,
                        jit_scope: 'TEAM',
                        jit_metadata: {}
                    };
                    await approvalsAPI.createJITRequest(payload);
                    toast.success("JIT access request submitted successfully");
                } else {
                    await approvalsAPI.create(formData);
                    toast.success("Access request submitted successfully");
                }
            }
            onClose();
        } catch (err) {
            toast.error(err.response?.data?.detail || "Failed to submit request");
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
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-[60] p-4">
            <div className="w-full max-w-2xl bg-white rounded-lg shadow-xl relative max-h-[90vh] overflow-hidden flex flex-col">
                {/* Header */}
                <div className={`px-6 py-4 border-b ${isGrantMode ? 'bg-green-50 border-green-200' : 'bg-indigo-50 border-indigo-200'}`}>
                    <div className="flex justify-between items-center">
                        <div className="flex items-center space-x-3">
                            <div className={`w-10 h-10 rounded-lg ${isGrantMode ? 'bg-green-100' : 'bg-indigo-100'} flex items-center justify-center`}>
                                {isGrantMode ? (
                                    <FiShield className={`w-5 h-5 ${isGrantMode ? 'text-green-600' : 'text-indigo-600'}`} />
                                ) : (
                                    <FiClock className="w-5 h-5 text-indigo-600" />
                                )}
                            </div>
                            <div>
                                <h2 className={`text-xl font-bold ${isGrantMode ? 'text-green-900' : 'text-indigo-900'}`}>
                                    {isGrantMode ? 'Grant Access' : 'Request Access'}
                                </h2>
                                <p className={`text-sm ${isGrantMode ? 'text-green-700' : 'text-indigo-700'}`}>
                                    {isGrantMode ? 'Delegate time-bound permissions to team members' : 'Submit a request for time-limited elevated access'}
                                </p>
                            </div>
                        </div>
                        <button
                            onClick={onClose}
                            className="text-gray-400 hover:text-gray-600 transition-colors p-1"
                        >
                            <FiX className="w-6 h-6" />
                        </button>
                    </div>

                    {/* Toggle for Team Leads */}
                    {isTeamLead && !initialData && (
                        <div className="mt-4 flex items-center space-x-2 bg-white rounded-lg p-1 border border-gray-200">
                            <button
                                type="button"
                                onClick={() => setIsGrantMode(false)}
                                className={`flex-1 px-4 py-2 rounded-md text-sm font-medium transition-all ${!isGrantMode ? 'bg-indigo-600 text-white' : 'text-gray-600 hover:text-gray-900'}`}
                            >
                                Request Access
                            </button>
                            <button
                                type="button"
                                onClick={() => setIsGrantMode(true)}
                                className={`flex-1 px-4 py-2 rounded-md text-sm font-medium transition-all ${isGrantMode ? 'bg-green-600 text-white' : 'text-gray-600 hover:text-gray-900'}`}
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
                            <label className="flex items-center text-sm font-semibold text-gray-700 mb-2">
                                <FiUsers className="w-4 h-4 mr-2" />
                                Select Recipients
                                {selectedRecipients.length > 0 && (
                                    <span className="ml-2 px-2 py-0.5 bg-green-100 text-green-700 rounded-full text-xs font-medium">
                                        {selectedRecipients.length} selected
                                    </span>
                                )}
                            </label>
                            <div className="border border-gray-200 rounded-lg max-h-48 overflow-y-auto bg-gray-50">
                                {membersLoading ? (
                                    <div className="p-4 text-center">
                                        <div className="inline-block animate-spin rounded-full h-6 w-6 border-b-2 border-green-600"></div>
                                        <p className="text-sm text-gray-500 mt-2">Loading team members...</p>
                                    </div>
                                ) : members.length === 0 ? (
                                    <div className="p-4 text-center text-gray-500 text-sm">
                                        No team members found
                                    </div>
                                ) : (
                                    <div className="divide-y divide-gray-200">
                                        {members.map(member => (
                                            <label
                                                key={member.id}
                                                className={`flex items-center p-3 cursor-pointer transition-colors ${selectedRecipients.includes(member.id)
                                                    ? 'bg-green-50'
                                                    : 'hover:bg-gray-100'
                                                    }`}
                                            >
                                                <input
                                                    type="checkbox"
                                                    checked={selectedRecipients.includes(member.id)}
                                                    onChange={() => toggleRecipient(member.id)}
                                                    className="w-4 h-4 rounded border-gray-300 text-green-600 focus:ring-green-500"
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
                        <div className="grid grid-cols-2 gap-4 bg-indigo-50 p-4 rounded-lg border border-indigo-100">
                            <div>
                                <label className="text-xs font-semibold text-indigo-700 uppercase tracking-wide">Action</label>
                                <div className="font-mono text-sm font-medium text-gray-900 mt-1">{formData.action_type}</div>
                            </div>
                            <div>
                                <label className="text-xs font-semibold text-indigo-700 uppercase tracking-wide">Resource</label>
                                <div className="font-mono text-sm font-medium text-gray-900 mt-1 truncate" title={formData.resource_id}>{formData.resource_id}</div>
                            </div>
                        </div>
                    )}

                    {/* Show Approvers in Request Mode */}
                    {!isGrantMode && (
                        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                            <label className="flex items-center text-sm font-semibold text-blue-900 mb-3">
                                <FiShield className="w-4 h-4 mr-2" />
                                Your request will be sent to:
                            </label>
                            {approversLoading ? (
                                <div className="flex items-center justify-center py-3">
                                    <div className="inline-block animate-spin rounded-full h-5 w-5 border-b-2 border-blue-600"></div>
                                </div>
                            ) : approvers.length === 0 ? (
                                <p className="text-sm text-blue-700">Team Leads or Organization Admins</p>
                            ) : (
                                <div className="space-y-2">
                                    {approvers.map(approver => (
                                        <div key={approver.id} className="flex items-center bg-white rounded-lg p-2 border border-blue-100">
                                            <div className="w-8 h-8 bg-blue-600 rounded-full flex items-center justify-center text-white text-sm font-medium flex-shrink-0">
                                                {approver.email?.[0]?.toUpperCase()}
                                            </div>
                                            <div className="ml-3 flex-1 min-w-0">
                                                <p className="text-sm font-medium text-gray-900 truncate">
                                                    {approver.full_name || approver.email.split('@')[0]}
                                                </p>
                                                <p className="text-xs text-gray-500 truncate">{approver.email}</p>
                                            </div>
                                            <span className={`text-xs px-2 py-1 rounded-full font-medium flex-shrink-0 ${
                                                approver.role === 'ORG_ADMIN' || approver.role === 'CLIENT' || approver.role === 'SUPER_ADMIN'
                                                    ? 'bg-purple-100 text-purple-700'
                                                    : 'bg-blue-100 text-blue-700'
                                            }`}>
                                                {approver.role === 'CLIENT' ? 'ORG_ADMIN' : approver.role}
                                            </span>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    )}

                    {/* Grant Mode: Type Selection */}
                    {isGrantMode && (
                        <div>
                            <label className="block text-sm font-semibold text-gray-700 mb-2">Access Type</label>
                            <select
                                className="w-full px-4 py-2.5 rounded-lg border border-gray-300 focus:border-green-500 focus:ring-2 focus:ring-green-200 transition-all text-sm bg-white"
                                value={formData.type}
                                onChange={e => setFormData({ ...formData, type: e.target.value })}
                            >
                                <option value="ACCESS_WINDOW">Full Access Window (Time-Bound)</option>
                                <option value="ACTION">Specific Action Only</option>
                            </select>
                        </div>
                    )}

                    {/* Action/Resource inputs for Manual Grant */}
                    {(isGrantMode || (!isGrantMode && !initialData)) && formData.type === 'ACTION' && (
                        <div className="space-y-4">
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-sm font-semibold text-gray-700 mb-2">Target Account</label>
                                    <select
                                        className="w-full px-4 py-2.5 rounded-lg border border-gray-300 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 transition-all text-sm bg-white"
                                        value={selectedAccountId}
                                        onChange={e => setSelectedAccountId(e.target.value)}
                                    >
                                        <option value="">Select Account</option>
                                        {accounts.map(acc => (
                                            <option key={acc.id} value={acc.aws_account_id || acc.id}>
                                                {acc.aws_account_id} {acc.name ? `(${acc.name})` : ''}
                                            </option>
                                        ))}
                                    </select>
                                </div>
                                <div>
                                    <label className="block text-sm font-semibold text-gray-700 mb-2">Action Name</label>
                                    <input
                                        type="text"
                                        className={`w-full px-4 py-2.5 rounded-lg border border-gray-300 ${isGrantMode ? 'focus:border-green-500 focus:ring-green-200' : 'focus:border-indigo-500 focus:ring-indigo-200'} focus:ring-2 transition-all text-sm`}
                                        placeholder="e.g. TERMINATE_INSTANCE"
                                        value={formData.action_type}
                                        onChange={e => setFormData({ ...formData, action_type: e.target.value })}
                                    />
                                </div>
                            </div>

                            <div>
                                <label className="block text-sm font-semibold text-gray-700 mb-2">Resource ID</label>
                                <div className="flex space-x-2">
                                    <input
                                        type="text"
                                        className={`flex-1 px-4 py-2.5 rounded-lg border border-gray-300 ${isGrantMode ? 'focus:border-green-500 focus:ring-green-200' : 'focus:border-indigo-500 focus:ring-indigo-200'} focus:ring-2 transition-all text-sm font-mono`}
                                        placeholder="e.g. i-123456"
                                        value={formData.resource_id}
                                        onChange={e => setFormData({ ...formData, resource_id: e.target.value })}
                                    />
                                    <Button
                                        type="button"
                                        variant="outline"
                                        disabled={discoveryLoading || !formData.action_type}
                                        onClick={handleDiscover}
                                        className="flex items-center"
                                    >
                                        <FiSearch className="w-4 h-4 mr-2" />
                                        {discoveryLoading ? 'Searching...' : 'Discover'}
                                    </Button>
                                </div>

                                {showDiscovery && discoveredResources.length > 0 && (
                                    <div className="mt-2 border border-gray-200 rounded-lg max-h-40 overflow-y-auto bg-white shadow-sm">
                                        <div className="p-2 text-xs font-bold text-gray-500 uppercase tracking-wider border-b bg-gray-50 flex justify-between items-center">
                                            <span>Select Resource</span>
                                            <button
                                                type="button"
                                                onClick={() => setShowDiscovery(false)}
                                                className="text-gray-400 hover:text-gray-600"
                                            >
                                                <FiX className="w-4 h-4" />
                                            </button>
                                        </div>
                                        <div className="divide-y divide-gray-100">
                                            {discoveredResources.map(res => (
                                                <button
                                                    key={res.id}
                                                    type="button"
                                                    onClick={() => selectDiscovered(res)}
                                                    className="w-full text-left p-3 hover:bg-indigo-50 transition-colors flex justify-between items-center group"
                                                >
                                                    <div>
                                                        <p className="text-sm font-mono font-medium text-gray-800 group-hover:text-indigo-600">{res.id}</p>
                                                        <p className="text-xs text-gray-500">{res.name} • {res.region} • <span className="text-green-600 font-medium">{res.status}</span></p>
                                                    </div>
                                                    <FiCheck className="w-4 h-4 text-indigo-500 opacity-0 group-hover:opacity-100 transition-opacity" />
                                                </button>
                                            ))}
                                        </div>
                                    </div>
                                )}
                            </div>
                        </div>
                    )}

                    {/* Reason Category */}
                    <div>
                        <label className="block text-sm font-semibold text-gray-700 mb-2">Reason Category</label>
                        <select
                            className={`w-full px-4 py-2.5 rounded-lg border border-gray-300 ${isGrantMode ? 'focus:border-green-500 focus:ring-green-200' : 'focus:border-indigo-500 focus:ring-indigo-200'} focus:ring-2 transition-all text-sm bg-white`}
                            value={formData.reason_category}
                            onChange={e => setFormData({ ...formData, reason_category: e.target.value })}
                        >
                            <option value="MAINTENANCE">Maintenance</option>
                            <option value="COST_OPT">Cost Optimization</option>
                            <option value="INCIDENT">Incident Response</option>
                            <option value="TESTING">Testing</option>
                            <option value="OTHER">Other</option>
                        </select>
                    </div>

                    {/* Justification */}
                    <div>
                        <label className="block text-sm font-semibold text-gray-700 mb-2">Justification</label>
                        <textarea
                            required
                            className={`w-full px-4 py-3 rounded-lg border border-gray-300 ${isGrantMode ? 'focus:border-green-500 focus:ring-green-200' : 'focus:border-indigo-500 focus:ring-indigo-200'} focus:ring-2 transition-all text-sm resize-none`}
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
                                className={`flex-1 h-2 rounded-lg appearance-none cursor-pointer ${isGrantMode ? 'accent-green-600' : 'accent-indigo-600'}`}
                                value={formData.duration_hours}
                                onChange={e => setFormData({ ...formData, duration_hours: parseInt(e.target.value) })}
                            />
                            <div className={`px-4 py-2 rounded-lg font-bold text-lg ${isGrantMode ? 'bg-green-100 text-green-700' : 'bg-indigo-100 text-indigo-700'}`}>
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
                <div className="px-6 py-4 bg-gray-50 border-t border-gray-200 flex justify-end space-x-3">
                    <Button variant="secondary" onClick={onClose} type="button">
                        Cancel
                    </Button>
                    <button
                        onClick={handleSubmit}
                        disabled={loading}
                        className={`px-6 py-2.5 rounded-lg font-semibold text-white transition-all disabled:opacity-50 flex items-center ${isGrantMode
                            ? 'bg-green-600 hover:bg-green-700 shadow-sm'
                            : 'bg-indigo-600 hover:bg-indigo-700 shadow-sm'
                            }`}
                    >
                        {loading ? (
                            <>
                                <svg className="animate-spin h-4 w-4 mr-2" viewBox="0 0 24 24">
                                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                                </svg>
                                Processing...
                            </>
                        ) : (
                            <>
                                {isGrantMode ? (
                                    <>
                                        <FiShield className="w-4 h-4 mr-2" />
                                        Grant Access
                                    </>
                                ) : (
                                    <>
                                        <FiClock className="w-4 h-4 mr-2" />
                                        Submit Request
                                    </>
                                )}
                            </>
                        )}
                    </button>
                </div>
            </div>
        </div>
    );
};

export default TicketRequestModal;
