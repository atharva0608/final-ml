import React, { useState, useEffect, useCallback } from 'react';
import { teamAPI, organizationAPI, rolesAPI } from '../../services/api';
import { FiPlus, FiUser, FiSearch, FiMoreVertical, FiEdit2, FiTrash2, FiLock, FiShield, FiUsers, FiCheckSquare, FiSquare, FiDollarSign, FiCpu, FiGrid, FiX } from 'react-icons/fi';
import { Card, Badge } from '../shared';
import toast from 'react-hot-toast';
import { useAuthStore } from '../../store/useStore';

const TeamManagement = () => {
    const { user: currentUser } = useAuthStore();
    const [activeTab, setActiveTab] = useState('members');
    const [memberFilter, setMemberFilter] = useState('ACTIVE');
    const [searchQuery, setSearchQuery] = useState('');
    const [teams, setTeams] = useState([]);
    const [selectedTeam, setSelectedTeam] = useState(null);
    const [allMembers, setAllMembers] = useState([]);

    // RBAC State
    const [roles, setRoles] = useState([]);
    const [permissions, setPermissions] = useState([]);
    const [showRoleEditor, setShowRoleEditor] = useState(false);
    const [editingRole, setEditingRole] = useState(null);
    const [roleForm, setRoleForm] = useState({ name: '', description: '', permission_slugs: [] });

    // Modals
    const [showInviteModal, setShowInviteModal] = useState(false);
    const [showEditModal, setShowEditModal] = useState(false);
    const [showDeleteModal, setShowDeleteModal] = useState(false);
    const [showCreateTeamModal, setShowCreateTeamModal] = useState(false);
    const [showMoveTeamModal, setShowMoveTeamModal] = useState(false);
    const [showTeamDetailsModal, setShowTeamDetailsModal] = useState(false);

    // Selection State
    const [selectedMember, setSelectedMember] = useState(null);
    const [viewingTeam, setViewingTeam] = useState(null);
    const [teamStats, setTeamStats] = useState(null);

    // Forms
    const [inviteEmail, setInviteEmail] = useState('');
    const [inviteRole, setInviteRole] = useState('MEMBER');
    const [inviteTeamId, setInviteTeamId] = useState('');
    const [editMemberRole, setEditMemberRole] = useState('');
    const [newTeamName, setNewTeamName] = useState('');
    const [moveToTeamId, setMoveToTeamId] = useState('');

    // Custom Policy Assignment State
    const [assignmentType, setAssignmentType] = useState('ROLE'); // 'ROLE' or 'POLICY'
    const [customPolicySlugs, setCustomPolicySlugs] = useState([]);

    // Dropdown states
    const [openDropdown, setOpenDropdown] = useState(null);

    const isOrgAdmin = currentUser?.role === 'ORG_ADMIN' || currentUser?.role === 'SUPER_ADMIN' || currentUser?.role === 'CLIENT';
    const isTeamLead = currentUser?.role === 'TEAM_LEAD';
    const isMemberView = currentUser?.role === 'MEMBER';

    const fetchAll = useCallback(async () => {
        await Promise.all([fetchTeams(), fetchMembers(), fetchRoles(), fetchPermissions()]);
    }, []);

    useEffect(() => {
        fetchAll();
    }, []);

    useEffect(() => {
        const handleClick = () => setOpenDropdown(null);
        document.addEventListener('click', handleClick);
        return () => document.removeEventListener('click', handleClick);
    }, []);

    const fetchTeams = async () => {
        try {
            const res = await teamAPI.list();
            setTeams(res.data || []);
        } catch (err) {
            console.error("Failed to fetch teams", err);
        }
    };

    const fetchMembers = async () => {
        try {
            const res = await organizationAPI.getMembers();
            setAllMembers(res.data.members || []);
        } catch (err) {
            console.error("Failed to fetch members", err);
        }
    };

    const fetchRoles = async () => {
        try {
            const res = await rolesAPI.listRoles();
            setRoles(res.data.roles || []);
        } catch (err) {
            console.error("Failed to fetch roles", err);
        }
    };

    const fetchPermissions = async () => {
        try {
            const res = await rolesAPI.listPermissions();
            setPermissions(res.data.permissions || []);
        } catch (err) {
            console.error("Failed to fetch permissions", err);
        }
    };

    // ========== TEAM ACTIONS ==========

    const handleTeamClick = async (team) => {
        setViewingTeam(team);
        setTeamStats(null); // Reset stats while loading
        setShowTeamDetailsModal(true);
        try {
            const res = await teamAPI.getStats(team.id);
            setTeamStats(res.data);
        } catch (err) {
            toast.error("Failed to load team statistics");
        }
    };

    const handleCreateTeam = async () => {
        if (!newTeamName.trim()) return;
        try {
            await teamAPI.create(newTeamName);
            setShowCreateTeamModal(false);
            setNewTeamName('');
            await fetchTeams();
            toast.success(`Team "${newTeamName}" created`);
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Failed to create team');
        }
    };

    // ========== MEMBER ACTIONS ==========

    const handleInvite = async () => {
        if (!inviteEmail) return;
        try {
            // For now, invites always use standard roles because custom roles need a user ID first.
            // We'll warn the user if they try to use Custom Policy on invite.
            if (assignmentType === 'POLICY') {
                toast("Invites must use a standard role first. You can customize permissions after the user accepts.", { icon: 'ℹ️' });
                return;
            }

            const targetTeamId = inviteTeamId || teams[0]?.id;
            if (targetTeamId) {
                await teamAPI.invite(targetTeamId, inviteEmail, inviteRole);
            }

            setShowInviteModal(false);
            setInviteEmail('');
            setInviteRole('MEMBER');
            setInviteTeamId('');
            setAssignmentType('ROLE');

            await Promise.all([fetchMembers(), fetchTeams()]);
            toast.success(`Invitation sent to ${inviteEmail}`);
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Failed to invite member');
        }
    };

    const handleMoveToTeam = async () => {
        if (!selectedMember || !moveToTeamId) return;
        try {
            await teamAPI.assign(moveToTeamId, selectedMember.id);
            setShowMoveTeamModal(false);
            setSelectedMember(null);
            setMoveToTeamId('');
            await Promise.all([fetchMembers(), fetchTeams()]);
            toast.success(`Member moved to new team`);
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Failed to move member');
        }
    };

    const handleEditAccess = async () => {
        if (!selectedMember) return;
        try {
            let roleIdToAssign = null;

            if (assignmentType === 'POLICY') {
                // Create a unique custom role for this user
                const roleName = `Custom: ${selectedMember.email}`;
                const res = await rolesAPI.createRole({
                    name: roleName,
                    description: `Custom policy for ${selectedMember.email}`,
                    permission_slugs: customPolicySlugs,
                    type: 'CUSTOM'
                });
                roleIdToAssign = res.data.id;
            } else {
                // Standard Role assignment
                // Map the enum string back to a role ID if needed, or use the legacy update endpoint
                const targetRole = roles.find(r => r.name === (editMemberRole === 'ORG_ADMIN' ? 'Organization Admin' : editMemberRole === 'TEAM_LEAD' ? 'Team Lead' : 'Member'));
                if (targetRole) roleIdToAssign = targetRole.id;
            }

            if (roleIdToAssign) {
                await rolesAPI.assignRole(selectedMember.id, roleIdToAssign);
            } else {
                // Fallback
                await organizationAPI.updateMemberRole(selectedMember.id, editMemberRole, selectedMember.access_level || 'READ_ONLY');
            }

            setShowEditModal(false);
            setSelectedMember(null);
            setAssignmentType('ROLE');
            setCustomPolicySlugs([]);
            await fetchMembers();
            toast.success('Member access updated');
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Failed to update access');
        }
    };

    const handleDeleteMember = async () => {
        if (!selectedMember) return;
        try {
            await organizationAPI.removeMember(selectedMember.id);
            setShowDeleteModal(false);
            setSelectedMember(null);
            await Promise.all([fetchMembers(), fetchTeams()]);
            toast.success('Member removed');
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Failed to remove member');
        }
    };

    // ========== ROLE ACTIONS ==========

    const openRoleEditor = (role = null) => {
        if (role) {
            setEditingRole(role);
            setRoleForm({ name: role.name, description: role.description || '', permission_slugs: role.permissions?.map(p => p.slug) || [] });
        } else {
            setEditingRole(null);
            setRoleForm({ name: '', description: '', permission_slugs: [] });
        }
        setShowRoleEditor(true);
    };

    const handleSaveRole = async () => {
        try {
            if (editingRole) {
                await rolesAPI.updateRole(editingRole.id, roleForm);
                toast.success('Role updated');
            } else {
                await rolesAPI.createRole(roleForm);
                toast.success('Role created');
            }
            setShowRoleEditor(false);
            fetchRoles();
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Failed to save role');
        }
    };

    const handleDeleteRole = async (roleId) => {
        if (!window.confirm('Delete this role?')) return;
        try {
            await rolesAPI.deleteRole(roleId);
            toast.success('Role deleted');
            fetchRoles();
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Failed to delete role');
        }
    };

    // Utility
    const togglePermission = (slug) => {
        setRoleForm(prev => ({
            ...prev,
            permission_slugs: prev.permission_slugs.includes(slug)
                ? prev.permission_slugs.filter(s => s !== slug)
                : [...prev.permission_slugs, slug]
        }));
    };

    const toggleCustomPolicySlug = (slug) => {
        setCustomPolicySlugs(prev => prev.includes(slug) ? prev.filter(s => s !== slug) : [...prev, slug]);
    };

    const permissionsByModule = permissions.reduce((acc, perm) => {
        if (!acc[perm.module]) acc[perm.module] = [];
        acc[perm.module].push(perm);
        return acc;
    }, {});

    const filteredMembers = allMembers.filter(m => {
        const matchesTeam = !selectedTeam || m.team_id === selectedTeam;
        const matchesFilter = memberFilter === 'ACTIVE' ? m.status !== 'PENDING_INVITE' : m.status === 'PENDING_INVITE';
        const matchesSearch = !searchQuery ||
            m.full_name?.toLowerCase().includes(searchQuery.toLowerCase()) ||
            m.email?.toLowerCase().includes(searchQuery.toLowerCase());
        return matchesTeam && matchesFilter && matchesSearch;
    });

    const getTeamName = (teamId) => teams.find(t => t.id === teamId)?.name || 'Unassigned';

    // ========== RENDER ==========

    if (isMemberView) {
        const myTeam = teams.find(t => t.id === currentUser?.team_id);
        return (
            <Card className="max-w-xl mx-auto mt-10 p-8 text-center border-t-4 border-t-emerald-500 shadow-lg">
                <div className="flex justify-center mb-6">
                    <div className="bg-emerald-100 p-4 rounded-full"><FiShield className="w-10 h-10 text-emerald-600" /></div>
                </div>
                <h2 className="text-2xl font-bold text-gray-900 mb-2">Team Membership</h2>
                <p className="text-lg text-gray-600">You are a member of: <span className="font-bold text-emerald-700">{myTeam?.name || 'No Team'}</span></p>
            </Card>
        );
    }

    return (
        <div className="space-y-6">
            <div className="border-b border-gray-200 pb-4">
                <h1 className="text-2xl font-bold text-gray-900">Team Management</h1>
                <p className="text-sm text-gray-600 mt-1">Manage users, teams, and access policies.</p>
            </div>

            {/* Tabs */}
            <div className="border-b border-gray-200">
                <div className="flex gap-8">
                    {['members', 'teams', 'roles'].map(tab => (
                        <button key={tab} onClick={() => setActiveTab(tab)}
                            className={`pb-3 text-sm font-medium border-b-2 transition-colors capitalize ${activeTab === tab ? 'border-emerald-500 text-emerald-600' : 'border-transparent text-gray-500 hover:text-gray-700'
                                }`}>
                            {tab === 'roles' ? 'Roles & Permissions' : tab}
                        </button>
                    ))}
                </div>
            </div>

            {/* Members Tab */}
            {activeTab === 'members' && (
                <div className="space-y-6">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                            <h2 className="text-lg font-semibold text-gray-900">Team Members</h2>
                            {(isOrgAdmin || isTeamLead) && (
                                <button onClick={() => setShowInviteModal(true)} className="flex items-center gap-2 px-3 py-1.5 bg-emerald-500 text-white rounded-lg hover:bg-emerald-600 text-sm font-medium">
                                    <FiPlus className="w-4 h-4" /> Add Member
                                </button>
                            )}
                        </div>
                    </div>

                    <div className="flex items-center justify-between flex-wrap gap-4">
                        <div className="flex items-center gap-4">
                            <select value={selectedTeam || ''} onChange={(e) => setSelectedTeam(e.target.value || null)}
                                className="px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-emerald-500">
                                <option value="">All Teams</option>
                                {teams.map(team => <option key={team.id} value={team.id}>{team.name}</option>)}
                            </select>
                            <div className="flex gap-2">
                                {['ACTIVE', 'INVITED'].map(f => (
                                    <button key={f} onClick={() => setMemberFilter(f)}
                                        className={`px-4 py-1.5 text-sm font-medium rounded ${memberFilter === f ? 'bg-gray-900 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'}`}>
                                        {f}
                                    </button>
                                ))}
                            </div>
                        </div>
                        <div className="relative">
                            <FiSearch className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 w-4 h-4" />
                            <input type="text" placeholder="Search..." value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)}
                                className="pl-10 pr-4 py-2 border border-gray-300 rounded-lg text-sm w-64 focus:ring-2 focus:ring-emerald-500" />
                        </div>
                    </div>

                    <div className="bg-white rounded-lg border border-gray-200 overflow-hidden shadow-sm">
                        <table className="min-w-full divide-y divide-gray-200">
                            <thead className="bg-gray-50">
                                <tr>
                                    <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase">Name</th>
                                    <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase">Email</th>
                                    <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase">Team</th>
                                    <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase">Access</th>
                                    <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase">Actions</th>
                                </tr>
                            </thead>
                            <tbody className="bg-white divide-y divide-gray-200">
                                {filteredMembers.map((member) => (
                                    <tr key={member.id} className="hover:bg-gray-50 transition-colors">
                                        <td className="px-6 py-4 whitespace-nowrap">
                                            <div className="flex items-center gap-3">
                                                <div className="w-8 h-8 rounded-full bg-blue-100 flex items-center justify-center text-blue-700 font-semibold text-sm">
                                                    {member.full_name?.charAt(0)?.toUpperCase() || member.email?.charAt(0)?.toUpperCase() || <FiUser />}
                                                </div>
                                                <span className="text-sm font-medium text-gray-900">{member.full_name || 'No Name'}</span>
                                            </div>
                                        </td>
                                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600">{member.email}</td>
                                        <td className="px-6 py-4 whitespace-nowrap">
                                            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                                                {getTeamName(member.team_id)}
                                            </span>
                                        </td>
                                        <td className="px-6 py-4 whitespace-nowrap">
                                            {member.assigned_role?.type === 'CUSTOM' ? (
                                                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-purple-100 text-purple-800">
                                                    <FiCheckSquare className="w-3 h-3" /> Custom Policy
                                                </span>
                                            ) : (
                                                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-800">
                                                    <FiShield className="w-3 h-3" /> {member.role === 'ORG_ADMIN' ? 'Org Admin' : member.role === 'TEAM_LEAD' ? 'Team Lead' : 'Member'}
                                                </span>
                                            )}
                                        </td>
                                        <td className="px-6 py-4 whitespace-nowrap">
                                            {isOrgAdmin && (
                                                <div className="relative">
                                                    <button onClick={(e) => { e.stopPropagation(); setOpenDropdown(openDropdown === member.id ? null : member.id); }}
                                                        className="p-1 hover:bg-gray-100 rounded text-gray-400 hover:text-gray-600">
                                                        <FiMoreVertical className="w-5 h-5" />
                                                    </button>
                                                    {openDropdown === member.id && (
                                                        <div className="absolute right-0 mt-1 w-48 bg-white rounded-lg shadow-lg border z-10 py-1">
                                                            <button onClick={() => { setSelectedMember(member); setEditMemberRole(member.role); setAssignmentType('ROLE'); setShowEditModal(true); setOpenDropdown(null); }}
                                                                className="w-full px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-50 flex items-center gap-2">
                                                                <FiEdit2 className="w-4 h-4" /> Configure Access
                                                            </button>
                                                            <button onClick={() => { setSelectedMember(member); setMoveToTeamId(member.team_id || ''); setShowMoveTeamModal(true); setOpenDropdown(null); }}
                                                                className="w-full px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-50 flex items-center gap-2">
                                                                <FiUsers className="w-4 h-4" /> Move to Team
                                                            </button>
                                                            <button onClick={() => { setSelectedMember(member); setShowDeleteModal(true); setOpenDropdown(null); }}
                                                                className="w-full px-4 py-2 text-left text-sm text-red-600 hover:bg-red-50 flex items-center gap-2">
                                                                <FiTrash2 className="w-4 h-4" /> Make Inactive
                                                            </button>
                                                        </div>
                                                    )}
                                                </div>
                                            )}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}

            {/* Teams Tab */}
            {activeTab === 'teams' && (
                <div className="space-y-6">
                    <div className="flex items-center gap-3">
                        <h2 className="text-lg font-semibold text-gray-900">Teams</h2>
                        {isOrgAdmin && (
                            <button onClick={() => setShowCreateTeamModal(true)} className="flex items-center gap-2 px-3 py-1.5 bg-emerald-500 text-white rounded-lg hover:bg-emerald-600 text-sm font-medium">
                                <FiPlus className="w-4 h-4" /> New Team
                            </button>
                        )}
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                        {teams.map(team => {
                            const teamMembers = allMembers.filter(m => m.team_id === team.id);
                            return (
                                <div key={team.id}
                                    onClick={() => handleTeamClick(team)}
                                    className="bg-white rounded-xl border border-gray-200 p-6 hover:shadow-lg transition-all cursor-pointer group hover:border-emerald-300">
                                    <div className="flex items-center justify-between mb-6">
                                        <div className="flex items-center gap-4">
                                            <div className="w-12 h-12 bg-emerald-100 rounded-xl flex items-center justify-center group-hover:bg-emerald-200 transition-colors">
                                                <FiUsers className="w-6 h-6 text-emerald-600" />
                                            </div>
                                            <div>
                                                <h3 className="font-bold text-gray-900 text-lg group-hover:text-emerald-700 transition-colors">{team.name}</h3>
                                                <p className="text-xs text-gray-500">ID: {team.id.substring(0, 8)}...</p>
                                            </div>
                                        </div>
                                    </div>
                                    <div className="space-y-4">
                                        <div className="flex items-center justify-between text-sm">
                                            <span className="text-gray-500">Members</span>
                                            <span className="font-semibold text-gray-900">{teamMembers.length}</span>
                                        </div>
                                        <div className="w-full bg-gray-100 h-1.5 rounded-full overflow-hidden">
                                            <div className="bg-emerald-500 h-full rounded-full" style={{ width: `${Math.min(teamMembers.length * 10, 100)}%` }}></div>
                                        </div>
                                        <div className="flex items-center justify-between text-xs text-gray-400 pt-2 border-t">
                                            <span>Click for resource & cost usage</span>
                                        </div>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                </div>
            )}

            {/* Roles Tab */}
            {activeTab === 'roles' && (
                <div className="space-y-6">
                    <div className="flex items-center gap-3">
                        <h2 className="text-lg font-semibold text-gray-900">Roles</h2>
                        {isOrgAdmin && (
                            <button onClick={() => openRoleEditor()} className="flex items-center gap-2 px-3 py-1.5 bg-emerald-500 text-white rounded-lg hover:bg-emerald-600 text-sm font-medium">
                                <FiPlus className="w-4 h-4" /> New Role
                            </button>
                        )}
                    </div>
                    <div className="bg-white rounded-lg border overflow-x-auto shadow-sm">
                        <table className="min-w-full divide-y divide-gray-200">
                            <thead className="bg-gray-50">
                                <tr>
                                    <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase w-48 sticky left-0 bg-gray-50 z-10 shadow-sm">Role</th>
                                    {Object.keys(permissionsByModule).slice(0, 8).map(m => (
                                        <th key={m} className="px-3 py-3 text-center text-xs font-semibold text-gray-500 uppercase whitespace-nowrap">{m.replace('Management', '')}</th>
                                    ))}
                                    {isOrgAdmin && <th className="px-3 py-3 text-center text-xs font-semibold text-gray-500 uppercase w-20">Actions</th>}
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-gray-200">
                                {roles.map((role) => (
                                    <tr key={role.id} className="hover:bg-gray-50">
                                        <td className="px-6 py-4 whitespace-nowrap sticky left-0 bg-white z-10 shadow-sm">
                                            <div className="flex items-center gap-2">
                                                {role.type === 'SYSTEM' && <FiLock className="w-4 h-4 text-gray-400" title="System Role" />}
                                                <div>
                                                    <span className="text-sm font-medium text-gray-900 block">{role.name}</span>
                                                    <span className="text-xs text-gray-500">{role.description?.substring(0, 30)}</span>
                                                </div>
                                            </div>
                                        </td>
                                        {Object.entries(permissionsByModule).slice(0, 8).map(([mod, perms]) => (
                                            <td key={mod} className="px-3 py-4 text-center">
                                                {perms.every(p => role.permissions?.some(rp => rp.slug === p.slug)) ? (
                                                    <span className="px-2 py-0.5 rounded text-xs font-semibold bg-emerald-500 text-white">ALL</span>
                                                ) : perms.some(p => role.permissions?.some(rp => rp.slug === p.slug)) ? (
                                                    <span className="px-2 py-0.5 rounded text-xs font-semibold bg-blue-400 text-white">SOME</span>
                                                ) : (
                                                    <span className="px-2 py-0.5 rounded text-xs font-semibold bg-gray-200 text-gray-500">-</span>
                                                )}
                                            </td>
                                        ))}
                                        {isOrgAdmin && (
                                            <td className="px-3 py-4 text-center">
                                                {role.type === 'CUSTOM' && (
                                                    <div className="flex justify-center gap-1">
                                                        <button onClick={() => openRoleEditor(role)} className="p-1 hover:bg-gray-100 rounded text-gray-500"><FiEdit2 className="w-4 h-4" /></button>
                                                        <button onClick={() => handleDeleteRole(role.id)} className="p-1 hover:bg-red-50 rounded text-red-500"><FiTrash2 className="w-4 h-4" /></button>
                                                    </div>
                                                )}
                                            </td>
                                        )}
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}

            {/* --- MODALS --- */}

            {/* Team Details Modal (Stats) */}
            {showTeamDetailsModal && viewingTeam && (
                <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 backdrop-blur-sm">
                    <div className="bg-white rounded-xl p-0 w-[500px] shadow-2xl overflow-hidden animate-fade-in">
                        <div className="bg-gradient-to-r from-emerald-500 to-teal-600 p-6 text-white flex justify-between items-start">
                            <div>
                                <h3 className="text-2xl font-bold">{viewingTeam.name}</h3>
                                <p className="text-emerald-100 text-sm mt-1">Team Details & Usage</p>
                            </div>
                            <button onClick={() => setShowTeamDetailsModal(false)} className="text-white/80 hover:text-white p-1 rounded-full hover:bg-white/10">
                                <FiX className="w-6 h-6" />
                            </button>
                        </div>

                        <div className="p-6">
                            {!teamStats ? (
                                <div className="flex justify-center py-8"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-emerald-500"></div></div>
                            ) : (
                                <div className="grid grid-cols-2 gap-4">
                                    <div className="bg-gray-50 p-4 rounded-xl text-center border hover:border-emerald-200 transition-colors">
                                        <div className="bg-blue-100 w-10 h-10 rounded-full flex items-center justify-center mx-auto mb-2 text-blue-600"><FiUsers /></div>
                                        <p className="text-sm text-gray-500">Members</p>
                                        <p className="text-2xl font-bold text-gray-900">{teamStats.member_count}</p>
                                    </div>
                                    <div className="bg-gray-50 p-4 rounded-xl text-center border hover:border-emerald-200 transition-colors">
                                        <div className="bg-purple-100 w-10 h-10 rounded-full flex items-center justify-center mx-auto mb-2 text-purple-600"><FiCpu /></div>
                                        <p className="text-sm text-gray-500">Resources</p>
                                        <p className="text-2xl font-bold text-gray-900">{teamStats.resource_count}</p>
                                    </div>
                                    <div className="col-span-2 bg-emerald-50 p-4 rounded-xl flex items-center justify-between border border-emerald-100">
                                        <div className="flex items-center gap-3">
                                            <div className="bg-emerald-200 w-10 h-10 rounded-full flex items-center justify-center text-emerald-700"><FiDollarSign className="w-5 h-5" /></div>
                                            <div>
                                                <p className="text-sm text-emerald-800 font-medium">Estimated Monthly Cost</p>
                                                <p className="text-xs text-emerald-600">Based on assigned resources</p>
                                            </div>
                                        </div>
                                        <p className="text-3xl font-bold text-emerald-700">${teamStats.total_cost}</p>
                                    </div>
                                </div>
                            )}

                            <div className="mt-6 flex justify-end">
                                <button onClick={() => setShowTeamDetailsModal(false)} className="px-4 py-2 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-lg text-sm font-medium transition-colors">Close</button>
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {/* Create Team Modal */}
            {showCreateTeamModal && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
                    <div className="bg-white rounded-xl p-6 w-96 shadow-2xl">
                        <h3 className="text-lg font-bold text-gray-900 mb-4">Create New Team</h3>
                        <input type="text" placeholder="e.g., Cloud, DevOps" value={newTeamName} onChange={(e) => setNewTeamName(e.target.value)}
                            className="w-full px-3 py-2 border border-gray-300 rounded-lg mb-4 focus:ring-2 focus:ring-emerald-500 outline-none" autoFocus />
                        <div className="flex justify-end gap-3">
                            <button onClick={() => setShowCreateTeamModal(false)} className="px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 rounded-lg">Cancel</button>
                            <button onClick={handleCreateTeam} className="px-4 py-2 text-sm bg-emerald-500 text-white rounded-lg hover:bg-emerald-600">Create</button>
                        </div>
                    </div>
                </div>
            )}

            {/* Move Team Modal */}
            {showMoveTeamModal && selectedMember && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
                    <div className="bg-white rounded-xl p-6 w-96 shadow-2xl">
                        <h3 className="text-lg font-bold text-gray-900 mb-4">Move Member</h3>
                        <p className="text-sm text-gray-600 mb-4">Move <strong>{selectedMember.email}</strong> to:</p>
                        <select value={moveToTeamId} onChange={(e) => setMoveToTeamId(e.target.value)}
                            className="w-full px-3 py-2 border border-gray-300 rounded-lg mb-6">
                            <option value="">Select Team...</option>
                            {teams.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
                        </select>
                        <div className="flex justify-end gap-3">
                            <button onClick={() => setShowMoveTeamModal(false)} className="px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 rounded-lg">Cancel</button>
                            <button onClick={handleMoveToTeam} className="px-4 py-2 text-sm bg-emerald-500 text-white rounded-lg hover:bg-emerald-600">Move</button>
                        </div>
                    </div>
                </div>
            )}

            {/* Access Configuration Modal (Invite / Edit) */}
            {(showInviteModal || showEditModal) && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
                    <div className="bg-white rounded-xl p-6 w-[750px] max-h-[90vh] overflow-y-auto shadow-2xl">
                        <h3 className="text-xl font-bold text-gray-900 mb-2">{showEditModal ? 'Configure User Access' : 'Invite New Member'}</h3>
                        <p className="text-gray-500 text-sm mb-6">Define who the user is and what they can do.</p>

                        {/* Basic Info */}
                        <div className="grid grid-cols-2 gap-6 mb-8">
                            {showInviteModal && (
                                <div className="col-span-2">
                                    <label className="block text-sm font-medium text-gray-700 mb-1">Email Address</label>
                                    <input type="email" placeholder="user@company.com" value={inviteEmail} onChange={(e) => setInviteEmail(e.target.value)} className="w-full px-4 py-2.5 border rounded-lg focus:ring-2 focus:ring-emerald-500 outline-none" />
                                </div>
                            )}

                            {/* Access Type Toggle */}
                            <div className="col-span-2 bg-gray-50 p-1.5 rounded-lg flex border">
                                <button
                                    onClick={() => setAssignmentType('ROLE')}
                                    className={`flex-1 py-2 rounded-md text-sm font-medium transition-all flex items-center justify-center gap-2 ${assignmentType === 'ROLE' ? 'bg-white shadow text-emerald-600' : 'text-gray-500 hover:text-gray-700'}`}>
                                    <FiShield className="w-4 h-4" /> Standard Role
                                </button>
                                <button
                                    onClick={() => setAssignmentType('POLICY')}
                                    className={`flex-1 py-2 rounded-md text-sm font-medium transition-all flex items-center justify-center gap-2 ${assignmentType === 'POLICY' ? 'bg-white shadow text-purple-600' : 'text-gray-500 hover:text-gray-700'}`}>
                                    <FiCheckSquare className="w-4 h-4" /> Custom Policy
                                </button>
                            </div>

                            {/* Standard Role Selection */}
                            {assignmentType === 'ROLE' && (
                                <>
                                    <div className="col-span-1">
                                        <label className="block text-sm font-medium text-gray-700 mb-1">Role</label>
                                        <select value={showEditModal ? editMemberRole : inviteRole} onChange={(e) => showEditModal ? setEditMemberRole(e.target.value) : setInviteRole(e.target.value)}
                                            className="w-full px-3 py-2.5 border rounded-lg focus:ring-2 focus:ring-emerald-500">
                                            <option value="MEMBER">Member (Standard Access)</option>
                                            <option value="TEAM_LEAD">Team Lead (Manager)</option>
                                            <option value="ORG_ADMIN">Organization Admin</option>
                                        </select>
                                    </div>
                                    <div className="col-span-1">
                                        <label className="block text-sm font-medium text-gray-700 mb-1">Team Assignment</label>
                                        <select value={showInviteModal ? inviteTeamId : (selectedMember?.team_id || '')}
                                            onChange={(e) => showInviteModal ? setInviteTeamId(e.target.value) : null}
                                            disabled={showEditModal}
                                            className="w-full px-3 py-2.5 border rounded-lg disabled:bg-gray-100 disabled:text-gray-500">
                                            <option value="">Select Team...</option>
                                            {teams.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
                                        </select>
                                    </div>
                                    <div className="col-span-2 text-sm text-gray-500 bg-emerald-50 p-3 rounded-lg border border-emerald-100">
                                        ℹ️ Assigning a standard role provides a pre-defined set of permissions suitable for most users.
                                    </div>
                                </>
                            )}

                            {/* Custom Policy Grid */}
                            {assignmentType === 'POLICY' && (
                                <div className="col-span-2">
                                    {showInviteModal && <div className="mb-4 text-sm text-amber-600 bg-amber-50 p-3 rounded border border-amber-200">
                                        Warning: Inviting directly with a custom policy is not yet supported. Please invite as 'Member' first, then edit their access.
                                    </div>}

                                    <div className="border rounded-xl max-h-80 overflow-y-auto">
                                        <div className="bg-gray-50 px-4 py-2 border-b sticky top-0 z-10 flex justify-between items-center">
                                            <h4 className="font-semibold text-gray-700 text-sm">Select Permissions</h4>
                                            <span className="text-xs text-gray-500">{customPolicySlugs.length} selected</span>
                                        </div>
                                        <div className="p-4 grid grid-cols-2 gap-6">
                                            {Object.entries(permissionsByModule).map(([mod, perms]) => (
                                                <div key={mod}>
                                                    <h5 className="font-bold text-gray-800 text-xs uppercase mb-2 border-b pb-1">{mod}</h5>
                                                    <div className="space-y-2">
                                                        {perms.map(perm => (
                                                            <label key={perm.slug} className="flex items-start gap-2 cursor-pointer group">
                                                                <div className="pt-0.5">
                                                                    <input type="checkbox"
                                                                        checked={customPolicySlugs.includes(perm.slug)}
                                                                        onChange={() => toggleCustomPolicySlug(perm.slug)}
                                                                        className="w-4 h-4 text-emerald-500 rounded border-gray-300 focus:ring-emerald-500"
                                                                    />
                                                                </div>
                                                                <div>
                                                                    <div className="text-sm font-medium text-gray-700 group-hover:text-gray-900 transition-colors">{perm.slug.split(':')[1]?.replace(/_/g, ' ') || perm.slug}</div>
                                                                    <div className="text-xs text-gray-400 leading-tight">{perm.description}</div>
                                                                </div>
                                                            </label>
                                                        ))}
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                </div>
                            )}
                        </div>

                        <div className="flex justify-end gap-3 pt-6 border-t">
                            <button onClick={() => { setShowInviteModal(false); setShowEditModal(false); setAssignmentType('ROLE'); }}
                                className="px-5 py-2.5 text-sm text-gray-700 hover:bg-gray-100 rounded-lg font-medium">Cancel</button>
                            <button onClick={showInviteModal ? handleInvite : handleEditAccess}
                                className="px-5 py-2.5 text-sm bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 font-medium shadow-sm">
                                {showInviteModal ? 'Send Invite' : 'Save Configuration'}
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* Role Editor Modal */}
            {showRoleEditor && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
                    <div className="bg-white rounded-xl p-6 w-[800px] max-h-[85vh] overflow-y-auto shadow-2xl">
                        <h3 className="text-lg font-bold text-gray-900 mb-4">{editingRole ? 'Edit Role' : 'Create New Role'}</h3>
                        <div className="grid grid-cols-2 gap-4 mb-4">
                            <div className="col-span-2">
                                <label className="block text-sm font-medium text-gray-700 mb-1">Role Name</label>
                                <input type="text" placeholder="e.g. Finance Auditor" value={roleForm.name} onChange={(e) => setRoleForm({ ...roleForm, name: e.target.value })}
                                    className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-emerald-500" />
                            </div>
                            <div className="col-span-2">
                                <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
                                <input type="text" placeholder="What is this role for?" value={roleForm.description} onChange={(e) => setRoleForm({ ...roleForm, description: e.target.value })}
                                    className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-emerald-500" />
                            </div>
                        </div>

                        <div className="border rounded-lg bg-gray-50 overflow-hidden">
                            <div className="px-4 py-3 border-b bg-gray-100 font-medium text-sm text-gray-700">Permissions</div>
                            <div className="p-4 grid grid-cols-2 md:grid-cols-3 gap-6">
                                {Object.entries(permissionsByModule).map(([mod, perms]) => (
                                    <div key={mod} className="bg-white p-3 rounded border shadow-sm">
                                        <h4 className="font-semibold text-gray-800 mb-2 border-b pb-1 text-xs uppercase tracking-wide">{mod}</h4>
                                        <div className="space-y-2">
                                            {perms.map(perm => (
                                                <label key={perm.slug} className="flex items-start gap-2 cursor-pointer hover:bg-gray-50 -mx-1 px-1 rounded transition-colors">
                                                    <div className="pt-0.5">
                                                        <input type="checkbox" checked={roleForm.permission_slugs.includes(perm.slug)} onChange={() => togglePermission(perm.slug)}
                                                            className="w-3.5 h-3.5 text-emerald-500 rounded border-gray-300 focus:ring-emerald-500" />
                                                    </div>
                                                    <div className="text-xs text-gray-700 leading-tight">
                                                        <span className="font-medium block">{perm.slug.split(':')[1] || perm.slug}</span>
                                                    </div>
                                                </label>
                                            ))}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>

                        <div className="flex justify-end gap-3 mt-4 pt-4 border-t sticky bottom-0 bg-white">
                            <button onClick={() => setShowRoleEditor(false)} className="px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 rounded-lg">Cancel</button>
                            <button onClick={handleSaveRole} className="px-4 py-2 text-sm bg-emerald-500 text-white rounded-lg hover:bg-emerald-600">Save Role</button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default TeamManagement;
