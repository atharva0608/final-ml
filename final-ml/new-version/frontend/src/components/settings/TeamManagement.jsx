import React, { useState, useEffect } from 'react';
import { FiUserPlus, FiTrash2, FiShield, FiX, FiLink } from 'react-icons/fi';
import { Card, Button, Badge } from '../shared';
import { useAuth } from '../../hooks/useAuth';
import { organizationAPI } from '../../services/api';
import toast from 'react-hot-toast';

const TeamManagement = () => {
    const { user } = useAuth();
    const [members, setMembers] = useState([]);
    const [loading, setLoading] = useState(true);
    const [inviteModalOpen, setInviteModalOpen] = useState(false);

    // Invite Form
    const [inviteEmail, setInviteEmail] = useState('');
    const [inviteRole, setInviteRole] = useState('MEMBER');
    const [inviteAccess, setInviteAccess] = useState('READ_ONLY');
    const [inviteLoading, setInviteLoading] = useState(false);
    const [lastInviteData, setLastInviteData] = useState(null); // To show invite link

    const fetchMembers = async () => {
        try {
            setLoading(true);
            const response = await organizationAPI.getMembers();
            setMembers(response.data.members || []);
        } catch (error) {
            console.error('Failed to fetch members:', error);
            toast.error('Failed to load team members');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchMembers();
    }, []);

    const handleInvite = async (e) => {
        e.preventDefault();
        setInviteLoading(true);
        try {
            const response = await organizationAPI.inviteMember(inviteEmail, inviteRole, inviteAccess);
            toast.success('Invitation created successfully');

            // Show invite link
            if (response.data.invitation) {
                const inviteLink = `${window.location.origin}/signup?token=${response.data.invitation.token}`;
                setLastInviteData({
                    email: inviteEmail,
                    link: inviteLink
                });
            }

            setInviteModalOpen(false);
            setInviteEmail('');
            setInviteRole('MEMBER');
            setInviteAccess('READ_ONLY');
            fetchMembers();
        } catch (error) {
            console.error('Invite failed:', error);
            toast.error(error.response?.data?.detail || 'Failed to create invitation');
        } finally {
            setInviteLoading(false);
        }
    };

    const handleRemoveMember = async (memberId) => {
        if (!window.confirm("Are you sure you want to remove this member?")) return;

        try {
            await organizationAPI.removeMember(memberId);
            toast.success('Member removed');
            fetchMembers();
        } catch (error) {
            console.error('Remove failed:', error);
            toast.error(error.response?.data?.detail || 'Failed to remove member');
        }
    };

    const handleUpdate = async (memberId, field, value) => {
        try {
            const updates = {};
            if (field === 'role') updates.role = value;
            if (field === 'access_level') updates.access_level = value;

            await organizationAPI.updateMemberRole(memberId, updates.role, updates.access_level);
            toast.success(`${field === 'role' ? 'Role' : 'Access Level'} updated`);
            fetchMembers();
        } catch (error) {
            console.error('Update failed:', error);
            toast.error(error.response?.data?.detail || 'Failed to update member');
        }
    };

    // Permission Logic - ONLY ORG_ADMIN can manage team
    const myRole = user?.org_role || 'MEMBER';
    const canManageTeam = myRole === 'ORG_ADMIN';

    // Helper to check if I can modify a specific user
    // Only ORG_ADMIN can modify users (and cannot modify self)
    const canModifyUser = (targetMember) => {
        if (targetMember.id === user.id) return false; // Cannot modify self
        return myRole === 'ORG_ADMIN';
    };

    // Get allowed role options - only ORG_ADMIN has access to Team Management
    // so they can assign any role
    const getRoleOptions = () => {
        if (myRole === 'ORG_ADMIN') {
            return [
                { value: 'MEMBER', label: 'Member' },
                { value: 'TEAM_LEAD', label: 'Team Lead' },
                { value: 'ORG_ADMIN', label: 'Org Admin' }
            ];
        }
        return [];
    };

    // Get allowed access level options
    const getAccessOptions = () => {
        return [
            { value: 'READ_ONLY', label: 'Read Only' },
            { value: 'EXECUTION', label: 'Execution' },
            { value: 'FULL', label: 'Full Access' }
        ];
    };

    return (
        <div className="space-y-6">
            <div className="flex justify-between items-center">
                <div>
                    <h2 className="text-xl font-bold text-gray-900">Team Management</h2>
                    <p className="text-gray-500 text-sm">Manage members of {user?.organization_name || 'your organization'}</p>
                </div>
                {canManageTeam && (
                    <Button onClick={() => setInviteModalOpen(true)}>
                        <FiUserPlus className="mr-2" />
                        Invite Member
                    </Button>
                )}
            </div>

            {lastInviteData && (
                <div className="bg-green-50 border border-green-200 rounded-lg p-4 mb-4">
                    <div className="flex justify-between items-start">
                        <div>
                            <h4 className="text-sm font-bold text-green-800">Invitation Link Generated</h4>
                            <p className="text-sm text-green-700 mt-1">
                                Share this link with <strong>{lastInviteData.email}</strong> to join the organization.
                            </p>
                            <div className="mt-2 flex items-center gap-2">
                                <code className="bg-white px-2 py-1 rounded border border-green-200 text-xs font-mono select-all flex-1">
                                    {lastInviteData.link}
                                </code>
                                <Button size="sm" variant="secondary" onClick={() => navigator.clipboard.writeText(lastInviteData.link)}>
                                    Copy
                                </Button>
                            </div>
                        </div>
                        <button onClick={() => setLastInviteData(null)} className="text-green-500 hover:text-green-700">
                            <FiX />
                        </button>
                    </div>
                </div>
            )}

            <Card>
                <div className="overflow-x-auto">
                    <table className="min-w-full divide-y divide-gray-200">
                        <thead className="bg-gray-50">
                            <tr>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">User</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Role</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Access Level</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Status</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Joined</th>
                                {canManageTeam && <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>}
                            </tr>
                        </thead>
                        <tbody className="bg-white divide-y divide-gray-200">
                            {members.map((member) => {
                                const allowedToEdit = canModifyUser(member);
                                return (
                                    <tr key={member.id}>
                                        <td className="px-6 py-4 whitespace-nowrap">
                                            <div className="flex items-center">
                                                <div className="h-10 w-10 bg-blue-100 rounded-full flex items-center justify-center text-blue-600 font-bold">
                                                    {(member.email && member.email[0]) ? member.email[0].toUpperCase() : '?'}
                                                </div>
                                                <div className="ml-4">
                                                    <div className="text-sm font-medium text-gray-900">{member.email}</div>
                                                    {member.id === user.id && <span className="text-xs text-blue-500">(You)</span>}
                                                </div>
                                            </div>
                                        </td>
                                        <td className="px-6 py-4 whitespace-nowrap">
                                            <div className="flex items-center">
                                                <FiShield className="mr-1.5 text-gray-400" />
                                                {allowedToEdit ? (
                                                    <select
                                                        value={member.org_role}
                                                        onChange={(e) => handleUpdate(member.id, 'role', e.target.value)}
                                                        className="text-sm border-none bg-transparent focus:ring-0 cursor-pointer hover:bg-gray-50 rounded px-1 -ml-1"
                                                    >
                                                        {getRoleOptions().map(opt => (
                                                            <option key={opt.value} value={opt.value}>{opt.label}</option>
                                                        ))}
                                                    </select>
                                                ) : (
                                                    <span className="text-sm text-gray-700">{member.org_role}</span>
                                                )}
                                            </div>
                                        </td>
                                        <td className="px-6 py-4 whitespace-nowrap">
                                            {allowedToEdit ? (
                                                <select
                                                    value={member.access_level}
                                                    onChange={(e) => handleUpdate(member.id, 'access_level', e.target.value)}
                                                    className="text-sm border-none bg-transparent focus:ring-0 cursor-pointer hover:bg-gray-50 rounded px-1 -ml-1"
                                                >
                                                    {getAccessOptions().map(opt => (
                                                        <option key={opt.value} value={opt.value}>{opt.label}</option>
                                                    ))}
                                                </select>
                                            ) : (
                                                <span className="text-sm text-gray-700">{member.access_level}</span>
                                            )}
                                        </td>
                                        <td className="px-6 py-4 whitespace-nowrap">
                                            <Badge variant={member.is_active ? 'success' : 'warning'}>
                                                {member.is_active ? 'Active' : 'Inactive'}
                                            </Badge>
                                        </td>
                                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                                            {new Date(member.created_at).toLocaleDateString()}
                                        </td>
                                        {canManageTeam && (
                                            <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                                                {allowedToEdit && (
                                                    <button
                                                        onClick={() => handleRemoveMember(member.id)}
                                                        className="text-red-400 hover:text-red-600 p-1"
                                                        title="Remove member"
                                                    >
                                                        <FiTrash2 />
                                                    </button>
                                                )}
                                            </td>
                                        )}
                                    </tr>
                                )
                            })}
                        </tbody>
                    </table>
                </div>
            </Card>

            {/* Invite Modal */}
            {inviteModalOpen && (
                <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
                    <Card className="w-full max-w-md">
                        <h3 className="text-lg font-bold mb-4">Invite Team Member</h3>
                        <form onSubmit={handleInvite}>
                            <div className="mb-4">
                                <label className="block text-sm font-medium text-gray-700 mb-1">Email Address</label>
                                <input
                                    type="email"
                                    value={inviteEmail}
                                    onChange={(e) => setInviteEmail(e.target.value)}
                                    className="w-full border rounded p-2"
                                    placeholder="colleague@company.com"
                                    required
                                />
                            </div>
                            <div className="grid grid-cols-2 gap-4 mb-4">
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-1">Role</label>
                                    <select
                                        value={inviteRole}
                                        onChange={(e) => setInviteRole(e.target.value)}
                                        className="w-full border rounded p-2"
                                    >
                                        {getRoleOptions().map(opt => (
                                            <option key={opt.value} value={opt.value}>{opt.label}</option>
                                        ))}
                                    </select>
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-1">Access Level</label>
                                    <select
                                        value={inviteAccess}
                                        onChange={(e) => setInviteAccess(e.target.value)}
                                        className="w-full border rounded p-2"
                                    >
                                        {getAccessOptions().map(opt => (
                                            <option key={opt.value} value={opt.value}>{opt.label}</option>
                                        ))}
                                    </select>
                                </div>
                            </div>
                            <p className="text-xs text-gray-500 mb-4">
                                Member will receive an invitation link to join the organization with these permissions.
                            </p>
                            <div className="flex justify-end gap-2">
                                <Button type="button" variant="secondary" onClick={() => setInviteModalOpen(false)}>Cancel</Button>
                                <Button type="submit" disabled={inviteLoading}>
                                    {inviteLoading ? 'Creating Link...' : 'Generate Invite Link'}
                                </Button>
                            </div>
                        </form>
                    </Card>
                </div>
            )}
        </div>
    );
};

export default TeamManagement;
