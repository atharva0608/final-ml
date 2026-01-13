import React, { useState, useEffect } from 'react';
import { teamAPI, organizationAPI } from '../../services/api';
import { FiChevronDown, FiChevronRight, FiEdit2, FiPlus, FiUser, FiUserPlus, FiShield, FiDatabase, FiMail, FiMoreVertical, FiArrowRight, FiSettings } from 'react-icons/fi';
import { Card, Button, Input, Badge } from '../shared';
import toast from 'react-hot-toast';
import { useAuthStore } from '../../store/useStore';
import TeamGovernance from './TeamGovernance';

const TeamManagement = () => {
    const { user: currentUser } = useAuthStore();
    const [teams, setTeams] = useState([]);
    const [members, setMembers] = useState([]);
    const [expandedTeam, setExpandedTeam] = useState(null);
    const [editingTeam, setEditingTeam] = useState(null);
    const [newName, setNewName] = useState("");

    // Modals
    const [showCreateModal, setShowCreateModal] = useState(false);
    const [createTeamName, setCreateTeamName] = useState("");
    const [showAssignModal, setShowAssignModal] = useState(false);
    const [showInviteModal, setShowInviteModal] = useState(false);
    const [showEditMemberModal, setShowEditMemberModal] = useState(false);
    const [showMoveModal, setShowMoveModal] = useState(false);

    const [selectedMember, setSelectedMember] = useState("");
    const [inviteEmail, setInviteEmail] = useState("");
    const [inviteRole, setInviteRole] = useState("MEMBER");
    const [assigningTeamId, setAssigningTeamId] = useState(null);

    // For editing member
    const [editingMember, setEditingMember] = useState(null);
    const [editMemberRole, setEditMemberRole] = useState("");
    const [moveToTeamId, setMoveToTeamId] = useState("");

    // Team Governance
    const [showGovernanceForTeam, setShowGovernanceForTeam] = useState(null);

    useEffect(() => {
        fetchTeams();
        if (isOrgAdmin) fetchMembers();
    }, []);

    const isOrgAdmin = currentUser?.role === 'ORG_ADMIN' || currentUser?.role === 'SUPER_ADMIN' || currentUser?.role === 'CLIENT';
    const isTeamLead = currentUser?.role === 'TEAM_LEAD';
    const isMemberView = currentUser?.role === 'MEMBER';

    const fetchTeams = async () => {
        try {
            const res = await teamAPI.list();
            setTeams(res.data);
            if (res.data.length === 1 && !isMemberView) {
                setExpandedTeam(res.data[0].id);
            }
        } catch (err) {
            console.error("Failed to fetch teams", err);
        }
    };

    const fetchMembers = async () => {
        try {
            const res = await organizationAPI.getMembers();
            setMembers(res.data.members || []);
        } catch (err) {
            console.error("Failed to fetch members", err);
        }
    };

    const handleRename = async (teamId) => {
        try {
            await teamAPI.rename(teamId, newName);
            setEditingTeam(null);
            fetchTeams();
            toast.success("Team renamed");
        } catch (err) {
            toast.error("Failed to rename team");
        }
    };

    const handleCreateTeam = async () => {
        try {
            await teamAPI.create(createTeamName);
            setShowCreateModal(false);
            setCreateTeamName("");
            fetchTeams();
            toast.success("Team created");
        } catch (err) {
            toast.error(err.response?.data?.detail || "Failed to create team");
        }
    };

    const handleAssignMember = async () => {
        if (!selectedMember || !assigningTeamId) return;
        try {
            await teamAPI.assign(assigningTeamId, selectedMember);
            setShowAssignModal(false);
            setSelectedMember("");
            fetchTeams();
            fetchMembers();
            toast.success("Member assigned to team");
        } catch (err) {
            toast.error(err.response?.data?.detail || "Failed to assign member");
        }
    };

    const handleInviteMember = async () => {
        if (!inviteEmail || !assigningTeamId) return;
        try {
            await teamAPI.invite(assigningTeamId, inviteEmail, inviteRole);
            setShowInviteModal(false);
            setInviteEmail("");
            setInviteRole("MEMBER");
            fetchTeams();
            toast.success(`Invitation sent to ${inviteEmail}. They will see a confirmation on first login.`);
        } catch (err) {
            toast.error(err.response?.data?.detail || "Failed to invite member");
        }
    };

    const handleEditMember = async () => {
        if (!editingMember) return;
        try {
            await organizationAPI.updateMemberRole(editingMember.id, editMemberRole, editingMember.access_level || "READ_ONLY");
            setShowEditMemberModal(false);
            setEditingMember(null);
            fetchTeams();
            fetchMembers();
            toast.success("Member role updated");
        } catch (err) {
            toast.error(err.response?.data?.detail || "Failed to update member");
        }
    };

    const handleMoveMember = async () => {
        if (!editingMember || !moveToTeamId) return;
        try {
            await teamAPI.assign(moveToTeamId, editingMember.id);
            setShowMoveModal(false);
            setEditingMember(null);
            setMoveToTeamId("");
            fetchTeams();
            fetchMembers();
            toast.success("Member moved to new team");
        } catch (err) {
            toast.error(err.response?.data?.detail || "Failed to move member");
        }
    };

    const openEditModal = (member) => {
        setEditingMember(member);
        setEditMemberRole(member.role);
        setShowEditMemberModal(true);
    };

    const openMoveModal = (member) => {
        setEditingMember(member);
        setMoveToTeamId("");
        setShowMoveModal(true);
    };

    const isAllowedToRename = (teamId) => {
        if (isOrgAdmin) return true;
        if (isTeamLead && currentUser?.team_id === teamId) return true;
        return false;
    };

    const canInviteToTeam = (teamId) => {
        if (isOrgAdmin) return true;
        if (isTeamLead && currentUser?.team_id === teamId) return true;
        return false;
    };

    // Member View
    if (isMemberView) {
        if (teams.length === 0) return <div className="text-gray-500 p-8 text-center">You are not assigned to any team.</div>;
        const myTeam = teams[0];
        const teamLead = myTeam.members?.find(m => m.role === 'TEAM_LEAD');

        return (
            <Card className="max-w-xl mx-auto mt-10 p-8 text-center border-t-4 border-t-indigo-600 shadow-lg">
                <div className="flex justify-center mb-6">
                    <div className="bg-indigo-100 p-4 rounded-full">
                        <FiShield className="w-10 h-10 text-indigo-600" />
                    </div>
                </div>
                <h2 className="text-2xl font-bold text-gray-900 mb-2">Team Membership</h2>
                <div className="space-y-4">
                    <p className="text-lg">
                        You are a member of: <span className="font-bold text-indigo-700">{myTeam.name}</span>
                    </p>
                    {teamLead ? (
                        <p className="text-gray-600">
                            Your Team Lead is: <span className="font-semibold text-gray-900">{teamLead.full_name || teamLead.email}</span>
                        </p>
                    ) : (
                        <p className="text-gray-500 italic">No Team Lead assigned.</p>
                    )}
                </div>
            </Card>
        );
    }

    // Admin/Lead View
    return (
        <div className="space-y-6">
            <div className="flex justify-between items-center">
                <div>
                    <h2 className="text-xl font-bold">Teams & Members</h2>
                    <p className="text-gray-500 text-sm">Manage teams and assign members</p>
                </div>
                {isOrgAdmin && (
                    <Button icon={<FiPlus />} onClick={() => setShowCreateModal(true)}>Create Team</Button>
                )}
            </div>

            <div className="space-y-4">
                {teams.map((team) => (
                    <Card key={team.id} className="overflow-hidden !p-0">
                        {/* Accordion Header */}
                        <div
                            className="p-4 bg-gray-50 flex justify-between items-center cursor-pointer border-b hover:bg-gray-100 transition-colors"
                            onClick={() => setExpandedTeam(expandedTeam === team.id ? null : team.id)}
                        >
                            <div className="flex items-center gap-3">
                                {expandedTeam === team.id ? <FiChevronDown /> : <FiChevronRight />}

                                {editingTeam === team.id ? (
                                    <div className="flex gap-2" onClick={e => e.stopPropagation()}>
                                        <Input value={newName} onChange={e => setNewName(e.target.value)} className="h-8" />
                                        <Button size="sm" onClick={() => handleRename(team.id)}>Save</Button>
                                        <Button size="sm" variant="outline" onClick={() => setEditingTeam(null)}>Cancel</Button>
                                    </div>
                                ) : (
                                    <h3 className="font-bold text-lg">{team.name}</h3>
                                )}

                                {isAllowedToRename(team.id) && !editingTeam && (
                                    <FiEdit2
                                        className="text-gray-400 hover:text-blue-600 cursor-pointer"
                                        onClick={(e) => { e.stopPropagation(); setEditingTeam(team.id); setNewName(team.name); }}
                                    />
                                )}
                            </div>
                            <div className="flex items-center gap-3">
                                <Badge color="blue">{team.members?.length || 0} Members</Badge>
                                {canInviteToTeam(team.id) && (
                                    <div className="flex gap-2" onClick={e => e.stopPropagation()}>
                                        {/* Only Org Admin can assign existing members (move between teams) */}
                                        {isOrgAdmin && (
                                            <Button size="xs" variant="outline" icon={<FiUserPlus className="w-3 h-3" />} onClick={() => { setAssigningTeamId(team.id); setShowAssignModal(true); }}>
                                                Assign
                                            </Button>
                                        )}
                                        {/* Both Org Admin and Team Lead (for own team) can invite new members */}
                                        <Button size="xs" variant="primary" icon={<FiMail className="w-3 h-3" />} onClick={() => { setAssigningTeamId(team.id); setShowInviteModal(true); }}>
                                            Invite New
                                        </Button>
                                    </div>
                                )}
                            </div>
                        </div>

                        {/* Accordion Body (Members List) */}
                        {expandedTeam === team.id && (
                            <div className="p-4 bg-white">
                                <table className="min-w-full">
                                    <thead>
                                        <tr className="text-left text-xs text-gray-500 uppercase border-b">
                                            <th className="pb-2 font-medium">Name</th>
                                            <th className="pb-2 font-medium">Email</th>
                                            <th className="pb-2 font-medium">Role</th>
                                            <th className="pb-2 font-medium">Accounts</th>
                                            <th className="pb-2 font-medium">Status</th>
                                            {isOrgAdmin && <th className="pb-2 font-medium">Actions</th>}
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y">
                                        {team.members?.map(member => (
                                            <tr key={member.id} className="hover:bg-gray-50">
                                                <td className="py-3 flex items-center gap-3">
                                                    <div className="w-8 h-8 rounded-full bg-blue-100 flex items-center justify-center text-blue-700 font-bold text-xs shrink-0">
                                                        {member.full_name ? member.full_name.charAt(0).toUpperCase() : member.email?.charAt(0).toUpperCase() || <FiUser />}
                                                    </div>
                                                    <div>
                                                        <div className="font-medium text-sm text-gray-900">{member.full_name || "No Name"}</div>
                                                        {member.role === 'TEAM_LEAD' && <span className="text-xs text-blue-600 font-bold flex items-center gap-1"><FiShield className="w-3 h-3" /> Team Lead</span>}
                                                    </div>
                                                </td>
                                                <td className="py-3 text-sm text-gray-600">{member.email}</td>
                                                <td className="py-3"><Badge>{member.role}</Badge></td>
                                                <td className="py-3 text-sm font-medium text-gray-700 pl-4">
                                                    {member.aws_accounts_count > 0 ? (
                                                        <span className="flex items-center gap-1 text-blue-600">
                                                            <FiDatabase className="w-3 h-3" /> {member.aws_accounts_count}
                                                        </span>
                                                    ) : <span className="text-gray-400">-</span>}
                                                </td>
                                                <td className="py-3">
                                                    <Badge color={member.status === 'ACTIVE' ? 'green' : 'yellow'}>{member.status || 'ACTIVE'}</Badge>
                                                </td>
                                                {isOrgAdmin && (
                                                    <td className="py-3">
                                                        <div className="flex gap-2">
                                                            <button
                                                                className="text-xs text-blue-600 hover:underline"
                                                                onClick={() => openEditModal(member)}
                                                            >
                                                                Edit Role
                                                            </button>
                                                            <button
                                                                className="text-xs text-purple-600 hover:underline flex items-center gap-1"
                                                                onClick={() => openMoveModal(member)}
                                                            >
                                                                <FiArrowRight className="w-3 h-3" /> Move
                                                            </button>
                                                        </div>
                                                    </td>
                                                )}
                                            </tr>
                                        ))}
                                        {(!team.members || team.members.length === 0) && (
                                            <tr><td colSpan={isOrgAdmin ? 6 : 5} className="py-8 text-center text-gray-500 italic">No members in this team</td></tr>
                                        )}
                                    </tbody>
                                </table>

                                {/* Team Governance Section - For Team Leads and Org Admins */}
                                {(isOrgAdmin || (isTeamLead && currentUser?.team_id === team.id)) && (
                                    <div className="mt-6 pt-4 border-t">
                                        <button
                                            onClick={() => setShowGovernanceForTeam(showGovernanceForTeam === team.id ? null : team.id)}
                                            className="flex items-center gap-2 text-purple-600 hover:text-purple-800 font-medium text-sm mb-4"
                                        >
                                            <FiSettings className="w-4 h-4" />
                                            {showGovernanceForTeam === team.id ? 'Hide Approval Policies' : 'Configure Approval Policies'}
                                            {showGovernanceForTeam === team.id ? <FiChevronDown className="w-4 h-4" /> : <FiChevronRight className="w-4 h-4" />}
                                        </button>

                                        {showGovernanceForTeam === team.id && (
                                            <TeamGovernance teamId={team.id} teamName={team.name} />
                                        )}
                                    </div>
                                )}
                            </div>
                        )}
                    </Card>
                ))}
                {teams.length === 0 && (
                    <div className="text-center py-10 text-gray-500">
                        No teams found. Create one to get started.
                    </div>
                )}
            </div>

            {/* Create Team Modal */}
            {showCreateModal && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
                    <div className="bg-white p-6 rounded-lg w-96 shadow-xl">
                        <h3 className="text-lg font-bold mb-4">Create New Team</h3>
                        <Input label="Team Name" value={createTeamName} onChange={e => setCreateTeamName(e.target.value)} />
                        <div className="flex justify-end gap-2 mt-4">
                            <Button variant="ghost" onClick={() => setShowCreateModal(false)}>Cancel</Button>
                            <Button onClick={handleCreateTeam}>Create</Button>
                        </div>
                    </div>
                </div>
            )}

            {/* Assign Existing Member Modal (ORG_ADMIN only) */}
            {showAssignModal && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
                    <div className="bg-white p-6 rounded-lg w-96 shadow-xl">
                        <h3 className="text-lg font-bold mb-4">Assign Existing Member</h3>
                        <p className="text-sm text-gray-500 mb-4">Move an existing organization member to this team.</p>
                        <div className="mb-4">
                            <label className="block text-sm font-medium text-gray-700 mb-1">Select Member</label>
                            <select
                                className="w-full border rounded p-2"
                                value={selectedMember}
                                onChange={e => setSelectedMember(e.target.value)}
                            >
                                <option value="">Select a user...</option>
                                {members.filter(m => m.id !== currentUser?.user_id).map(m => (
                                    <option key={m.id} value={m.id}>
                                        {m.email} {m.team_id ? `(Current: ${teams.find(t => t.id === m.team_id)?.name || 'Unknown'})` : '(Unassigned)'}
                                    </option>
                                ))}
                            </select>
                        </div>
                        <div className="flex justify-end gap-2 mt-4">
                            <Button variant="ghost" onClick={() => setShowAssignModal(false)}>Cancel</Button>
                            <Button onClick={handleAssignMember}>Assign</Button>
                        </div>
                    </div>
                </div>
            )}

            {/* Invite New Member Modal */}
            {showInviteModal && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
                    <div className="bg-white p-6 rounded-lg w-96 shadow-xl">
                        <h3 className="text-lg font-bold mb-4">Invite New Member</h3>
                        <p className="text-sm text-gray-500 mb-4">
                            Create account for a new user. They will confirm on first login.
                        </p>
                        <div className="space-y-4">
                            <Input
                                label="Email Address"
                                type="email"
                                placeholder="user@example.com"
                                value={inviteEmail}
                                onChange={e => setInviteEmail(e.target.value)}
                            />
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-1">Role</label>
                                <select
                                    className="w-full border rounded p-2"
                                    value={inviteRole}
                                    onChange={e => setInviteRole(e.target.value)}
                                >
                                    <option value="MEMBER">Member</option>
                                    {/* Only Org Admin can create Team Leads */}
                                    {isOrgAdmin && <option value="TEAM_LEAD">Team Lead</option>}
                                </select>
                            </div>
                        </div>
                        <div className="flex justify-end gap-2 mt-4">
                            <Button variant="ghost" onClick={() => setShowInviteModal(false)}>Cancel</Button>
                            <Button onClick={handleInviteMember}>Send Invitation</Button>
                        </div>
                    </div>
                </div>
            )}

            {/* Edit Member Role Modal (ORG_ADMIN only) */}
            {showEditMemberModal && editingMember && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
                    <div className="bg-white p-6 rounded-lg w-96 shadow-xl">
                        <h3 className="text-lg font-bold mb-4">Edit Member Role</h3>
                        <p className="text-sm text-gray-500 mb-4">Update role for: <strong>{editingMember.email}</strong></p>
                        <div>
                            <label className="block text-sm font-medium text-gray-700 mb-1">Role</label>
                            <select
                                className="w-full border rounded p-2"
                                value={editMemberRole}
                                onChange={e => setEditMemberRole(e.target.value)}
                            >
                                <option value="MEMBER">Member</option>
                                <option value="TEAM_LEAD">Team Lead</option>
                                <option value="ORG_ADMIN">Org Admin</option>
                            </select>
                        </div>
                        <div className="flex justify-end gap-2 mt-4">
                            <Button variant="ghost" onClick={() => setShowEditMemberModal(false)}>Cancel</Button>
                            <Button onClick={handleEditMember}>Save Changes</Button>
                        </div>
                    </div>
                </div>
            )}

            {/* Move Member to Another Team Modal (ORG_ADMIN only) */}
            {showMoveModal && editingMember && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
                    <div className="bg-white p-6 rounded-lg w-96 shadow-xl">
                        <h3 className="text-lg font-bold mb-4">Move Member to Team</h3>
                        <p className="text-sm text-gray-500 mb-4">Move <strong>{editingMember.email}</strong> to another team.</p>
                        <div>
                            <label className="block text-sm font-medium text-gray-700 mb-1">Select Target Team</label>
                            <select
                                className="w-full border rounded p-2"
                                value={moveToTeamId}
                                onChange={e => setMoveToTeamId(e.target.value)}
                            >
                                <option value="">Select team...</option>
                                {teams.filter(t => t.id !== editingMember.team_id).map(t => (
                                    <option key={t.id} value={t.id}>{t.name}</option>
                                ))}
                            </select>
                        </div>
                        <div className="flex justify-end gap-2 mt-4">
                            <Button variant="ghost" onClick={() => setShowMoveModal(false)}>Cancel</Button>
                            <Button onClick={handleMoveMember}>Move Member</Button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default TeamManagement;
