import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { teamAPI, metricsAPI } from '../services/api';
import {
    FiChevronDown, FiChevronRight, FiUser, FiDollarSign, FiTrash2,
    FiLayers, FiTrendingUp, FiArrowLeft, FiSettings, FiUsers, FiEdit2, FiXCircle, FiShield
} from 'react-icons/fi';
import { StatsCard, Card, Badge, Button, Dropdown } from '../components/shared';
import {
    AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer,
    PieChart, Pie, Cell, Legend
} from 'recharts';
import TeamGovernance from '../components/settings/TeamGovernance';
import MemberPermissionsModal from '../components/settings/MemberPermissionsModal';
import toast from 'react-hot-toast';
import { useAuthStore } from '../store/useStore';

// Chart Color Palette
const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042', '#8884d8'];

const TeamDetails = () => {
    const { teamId } = useParams();
    const navigate = useNavigate();
    const { user: currentUser } = useAuthStore();
    const [team, setTeam] = useState(null);
    const [stats, setStats] = useState(null);
    const [activeTab, setActiveTab] = useState('CONSOLIDATED');
    const [expandedMember, setExpandedMember] = useState(null);
    const [loading, setLoading] = useState(true);

    // Permissions Modal State
    const [permissionsModalOpen, setPermissionsModalOpen] = useState(false);
    const [selectedMemberForPermissions, setSelectedMemberForPermissions] = useState(null);

    useEffect(() => {
        fetchData();
    }, [teamId]);

    const fetchData = async () => {
        try {
            setLoading(true);
            const [tRes, sRes] = await Promise.all([
                teamAPI.get(teamId),
                metricsAPI.getTeamSummary(teamId)
            ]);
            setTeam(tRes.data);
            setStats(sRes.data);
        } catch (e) {
            console.error("Error loading team data", e);
            toast.error("Failed to load team data");
        } finally {
            setLoading(false);
        }
    };

    const handleRemoveMember = async (memberId) => {
        if (!window.confirm("Are you sure you want to remove this member from the team?")) return;

        try {
            await teamAPI.remove(teamId, memberId);
            toast.success("Member removed from team");
            fetchData(); // Refresh list
        } catch (e) {
            console.error("Failed to remove member", e);
            toast.error(e.response?.data?.detail || "Failed to remove member");
        }
    };

    if (loading) return <div className="p-8 text-gray-500">Loading Team Data...</div>;
    if (!team) return <div className="p-8 text-red-500">Team not found</div>;

    return (
        <div className="space-y-6">

            {/* Header Section */}
            <div className="flex flex-col md:flex-row justify-between items-start md:items-center border-b pb-4 bg-white p-6 rounded-lg shadow-sm gap-4">
                <div className="flex items-center gap-4">
                    <button onClick={() => navigate('/teams')} className="p-2 hover:bg-gray-100 rounded-full transition-colors">
                        <FiArrowLeft className="w-5 h-5 text-gray-500" />
                    </button>
                    <div>
                        <h1 className="text-2xl font-bold text-gray-900">{team.name}</h1>
                        <p className="text-gray-500 text-sm mt-1">
                            {team.members?.length || 0} members • Consolidated Governance View
                        </p>
                    </div>
                </div>

                {/* Tab Switcher */}
                <div className="flex bg-gray-100 p-1 rounded-lg">
                    <button
                        className={`px-4 py-2 rounded-md text-sm font-medium transition-all ${activeTab === 'CONSOLIDATED' ? 'bg-white shadow text-blue-600' : 'text-gray-500 hover:text-gray-700'}`}
                        onClick={() => setActiveTab('CONSOLIDATED')}
                    >
                        Overview
                    </button>
                    <button
                        className={`px-4 py-2 rounded-md text-sm font-medium transition-all ${activeTab === 'MEMBERS' ? 'bg-white shadow text-blue-600' : 'text-gray-500 hover:text-gray-700'}`}
                        onClick={() => setActiveTab('MEMBERS')}
                    >
                        Member Details
                    </button>
                    <button
                        className={`px-4 py-2 rounded-md text-sm font-medium transition-all flex items-center gap-1 ${activeTab === 'GOVERNANCE' ? 'bg-white shadow text-blue-600' : 'text-gray-500 hover:text-gray-700'}`}
                        onClick={() => setActiveTab('GOVERNANCE')}
                    >
                        <FiSettings className="w-4 h-4" /> Governance
                    </button>
                </div>
            </div>

            {/* === VIEW 1: DETAILED CONSOLIDATED DASHBOARD === */}
            {activeTab === 'CONSOLIDATED' && stats && (
                <div className="space-y-6 animate-fade-in">

                    {/* 1. KPI Cards */}
                    <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                        <StatsCard
                            title="Total Spend (Mo)"
                            value={`$${stats.total_cost || 0}`}
                            icon={FiDollarSign}
                            color="blue"
                            subtext="Combined Team Spend"
                        />
                        <StatsCard
                            title="Total Waste"
                            value={`$${stats.total_waste || 0}`}
                            icon={FiTrash2}
                            color="red"
                            subtext="Potential Savings"
                        />
                        <StatsCard
                            title="Team Members"
                            value={stats.member_count || 0}
                            icon={FiUsers}
                            color="purple"
                        />
                        <StatsCard
                            title="Efficiency Score"
                            value={`${stats.efficiency_score || 100}%`}
                            icon={FiTrendingUp}
                            color="green"
                            subtext={stats.efficiency_score >= 85 ? 'Healthy' : 'Needs Attention'}
                        />
                    </div>

                    {/* 2. Charts Section (Side by Side) */}
                    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

                        {/* Main Graph: Cost History */}
                        <div className="lg:col-span-2">
                            <Card title="Aggregated Cost Trends">
                                <div className="h-72 w-full">
                                    <ResponsiveContainer>
                                        <AreaChart data={stats.history || []}>
                                            <defs>
                                                <linearGradient id="colorCostGradient" x1="0" y1="0" x2="0" y2="1">
                                                    <stop offset="5%" stopColor="#2563eb" stopOpacity={0.8} />
                                                    <stop offset="95%" stopColor="#2563eb" stopOpacity={0} />
                                                </linearGradient>
                                            </defs>
                                            <XAxis dataKey="name" />
                                            <YAxis />
                                            <Tooltip formatter={(value) => `$${value}`} />
                                            <Area type="monotone" dataKey="cost" stroke="#2563eb" fillOpacity={1} fill="url(#colorCostGradient)" />
                                        </AreaChart>
                                    </ResponsiveContainer>
                                </div>
                            </Card>
                        </div>

                        {/* Side Graph: Waste Distribution Pie Chart */}
                        <Card title="Waste Breakdown">
                            <div className="h-72 w-full flex flex-col items-center justify-center relative">
                                {stats.waste_distribution && stats.waste_distribution.length > 0 ? (
                                    <ResponsiveContainer>
                                        <PieChart>
                                            <Pie
                                                data={stats.waste_distribution}
                                                innerRadius={50}
                                                outerRadius={80}
                                                paddingAngle={5}
                                                dataKey="value"
                                                nameKey="name"
                                            >
                                                {stats.waste_distribution.map((entry, index) => (
                                                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                                                ))}
                                            </Pie>
                                            <Tooltip formatter={(value) => `$${value}`} />
                                            <Legend verticalAlign="bottom" height={36} />
                                        </PieChart>
                                    </ResponsiveContainer>
                                ) : (
                                    <div className="text-center text-gray-400">
                                        <FiTrash2 className="w-12 h-12 mx-auto mb-2 opacity-50" />
                                        <p className="text-sm">No waste detected</p>
                                        <p className="text-xs text-gray-300">Team is running efficiently</p>
                                    </div>
                                )}
                            </div>
                        </Card>
                    </div>

                    {/* 3. Top Spenders Leaderboard */}
                    <Card title="Top Spenders (Cost Leaders)">
                        <div className="overflow-x-auto">
                            {stats.top_spenders && stats.top_spenders.length > 0 ? (
                                <table className="min-w-full divide-y divide-gray-200">
                                    <thead className="bg-gray-50">
                                        <tr>
                                            <th className="px-6 py-3 text-left text-xs font-bold text-gray-500 uppercase">Rank</th>
                                            <th className="px-6 py-3 text-left text-xs font-bold text-gray-500 uppercase">Member</th>
                                            <th className="px-6 py-3 text-left text-xs font-bold text-gray-500 uppercase">Accounts</th>
                                            <th className="px-6 py-3 text-left text-xs font-bold text-gray-500 uppercase">Monthly Spend</th>
                                            <th className="px-6 py-3 text-right text-xs font-bold text-gray-500 uppercase">Status</th>
                                        </tr>
                                    </thead>
                                    <tbody className="bg-white divide-y divide-gray-200">
                                        {stats.top_spenders.map((user, idx) => (
                                            <tr key={idx} className="hover:bg-gray-50">
                                                <td className="px-6 py-4 whitespace-nowrap">
                                                    <span className={`inline-flex items-center justify-center w-8 h-8 rounded-full font-bold text-sm ${idx === 0 ? 'bg-yellow-100 text-yellow-700' :
                                                        idx === 1 ? 'bg-gray-100 text-gray-600' :
                                                            idx === 2 ? 'bg-orange-100 text-orange-700' : 'bg-gray-50 text-gray-500'
                                                        }`}>
                                                        #{idx + 1}
                                                    </span>
                                                </td>
                                                <td className="px-6 py-4 whitespace-nowrap">
                                                    <div className="flex items-center">
                                                        <div className="h-10 w-10 rounded-full bg-blue-100 flex items-center justify-center text-blue-700 font-bold mr-3">
                                                            {user.name?.[0]?.toUpperCase() || '?'}
                                                        </div>
                                                        <div>
                                                            <div className="text-sm font-medium text-gray-900">{user.name}</div>
                                                            <div className="text-xs text-gray-500">{user.email}</div>
                                                        </div>
                                                    </div>
                                                </td>
                                                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600">
                                                    {user.account_count || 0} account{user.account_count !== 1 ? 's' : ''}
                                                </td>
                                                <td className="px-6 py-4 whitespace-nowrap">
                                                    <span className="text-lg font-bold text-gray-900">${user.cost}</span>
                                                </td>
                                                <td className="px-6 py-4 whitespace-nowrap text-right">
                                                    {user.cost > 500 ? (
                                                        <Badge color="red">High</Badge>
                                                    ) : user.cost > 100 ? (
                                                        <Badge color="yellow">Medium</Badge>
                                                    ) : (
                                                        <Badge color="green">Normal</Badge>
                                                    )}
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            ) : (
                                <div className="text-center py-8 text-gray-500">
                                    <FiUsers className="w-12 h-12 mx-auto mb-2 opacity-50" />
                                    <p>No spending data available yet</p>
                                    <p className="text-xs text-gray-400">Connect AWS accounts to see cost analytics</p>
                                </div>
                            )}
                        </div>
                    </Card>

                    {/* Quick Stats Row */}
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-center">
                        <div className="bg-white p-4 rounded-lg border shadow-sm">
                            <div className="text-2xl font-bold text-gray-900">{stats.instance_count || 0}</div>
                            <div className="text-sm text-gray-500">Active Instances</div>
                        </div>
                        <div className="bg-white p-4 rounded-lg border shadow-sm">
                            <div className="text-2xl font-bold text-gray-900">{stats.cluster_count || 0}</div>
                            <div className="text-sm text-gray-500">Clusters</div>
                        </div>
                        <div className="bg-white p-4 rounded-lg border shadow-sm">
                            <div className="text-2xl font-bold text-blue-600">{stats.account_count || 0}</div>
                            <div className="text-sm text-gray-500">AWS Accounts</div>
                        </div>
                        <div className="bg-white p-4 rounded-lg border shadow-sm">
                            <div className={`text-2xl font-bold ${stats.efficiency_score >= 85 ? 'text-green-600' : 'text-yellow-600'}`}>
                                {stats.efficiency_score || 100}%
                            </div>
                            <div className="text-sm text-gray-500">Efficiency</div>
                        </div>
                    </div>
                </div>
            )}

            {/* === VIEW 2: MEMBER DETAILS (Dropdown Style) === */}
            {activeTab === 'MEMBERS' && (
                <div className="space-y-3">
                    {team.members?.length === 0 && (
                        <div className="text-center py-12 text-gray-500">
                            <FiUsers className="w-12 h-12 mx-auto mb-3 opacity-50" />
                            <p>No members in this team yet.</p>
                        </div>
                    )}

                    {team.members?.map((member) => (
                        <div key={member.id} className="bg-white border rounded-lg overflow-hidden transition-all shadow-sm hover:shadow-md">

                            {/* Accordion Header */}
                            <div
                                className="p-4 flex items-center justify-between cursor-pointer hover:bg-gray-50 transition-colors"
                                onClick={() => setExpandedMember(expandedMember === member.id ? null : member.id)}
                            >
                                <div className="flex items-center gap-4">
                                    {expandedMember === member.id ? <FiChevronDown className="text-gray-400" /> : <FiChevronRight className="text-gray-400" />}
                                    <div className="h-10 w-10 rounded-full bg-indigo-100 flex items-center justify-center text-indigo-700 font-bold">
                                        {member.full_name?.[0]?.toUpperCase() || member.email?.[0]?.toUpperCase() || <FiUser />}
                                    </div>
                                    <div>
                                        <h4 className="text-lg font-bold text-gray-900">{member.full_name || 'No Name'}</h4>
                                        <span className="text-sm text-gray-500">{member.email}</span>
                                    </div>
                                </div>
                                <div className="flex items-center gap-6">
                                    <div className="text-right hidden sm:block">
                                        <span className="block text-xs text-gray-500">Role</span>
                                        <Badge color={member.role === 'TEAM_LEAD' ? 'purple' : member.role === 'ORG_ADMIN' ? 'blue' : 'gray'}>
                                            {member.role}
                                        </Badge>
                                    </div>
                                    <div className="text-right mr-4">
                                        <span className="block text-xs text-gray-500">Accounts</span>
                                        <span className="font-bold text-lg">{member.accounts?.length || 0}</span>
                                    </div>

                                    {/* Member Actions Dropdown */}
                                    <div onClick={(e) => e.stopPropagation()}>
                                        <Dropdown
                                            items={[
                                                // Permissions button only for TEAM_LEAD or ORG_ADMIN
                                                ...(currentUser?.role === 'TEAM_LEAD' || currentUser?.role === 'ORG_ADMIN' ? [{
                                                    label: 'Member Permissions',
                                                    icon: <FiShield />,
                                                    onClick: () => {
                                                        setSelectedMemberForPermissions(member);
                                                        setPermissionsModalOpen(true);
                                                    }
                                                }] : []),
                                                {
                                                    label: 'Edit Role',
                                                    icon: <FiEdit2 />,
                                                    onClick: () => toast('Edit Role feature coming soon')
                                                },
                                                {
                                                    label: 'Remove from Team',
                                                    icon: <FiXCircle />,
                                                    className: 'text-red-600 hover:text-red-700',
                                                    onClick: () => handleRemoveMember(member.id)
                                                }
                                            ]}
                                        />
                                    </div>
                                </div>
                            </div>

                            {/* Accordion Body */}
                            {expandedMember === member.id && (
                                <div className="p-6 bg-gray-50 border-t">
                                    <h5 className="text-xs font-bold text-gray-500 uppercase mb-3">Resource Overview</h5>

                                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
                                        <div className="bg-white p-4 rounded shadow-sm border">
                                            <div className="text-sm text-gray-500">Connected Accounts</div>
                                            <div className="text-xl font-bold">{member.accounts?.length || 0}</div>
                                        </div>
                                        <div className="bg-white p-4 rounded shadow-sm border">
                                            <div className="text-sm text-gray-500">Member Status</div>
                                            <Badge color={member.status === 'ACTIVE' ? 'green' : 'yellow'}>{member.status || 'ACTIVE'}</Badge>
                                        </div>
                                        <div className="bg-white p-4 rounded shadow-sm border">
                                            <div className="text-sm text-gray-500">AWS Accounts</div>
                                            <div className="text-xl font-bold">{member.aws_accounts_count || member.accounts?.length || 0}</div>
                                        </div>
                                    </div>

                                    {/* Account List */}
                                    {member.accounts?.length > 0 ? (
                                        <div className="bg-white rounded border overflow-hidden">
                                            <table className="min-w-full divide-y divide-gray-200">
                                                <thead className="bg-gray-100">
                                                    <tr>
                                                        <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Account ID</th>
                                                        <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Provider</th>
                                                        <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                                                    </tr>
                                                </thead>
                                                <tbody className="divide-y divide-gray-200">
                                                    {member.accounts && member.accounts.map((acc, i) => (
                                                        <tr key={i} className="border-b last:border-0 hover:bg-gray-50">
                                                            <td className="px-4 py-2 font-mono text-sm">
                                                                <a
                                                                    href={`/accounts/${acc.id}/analytics`}
                                                                    onClick={(e) => {
                                                                        e.preventDefault();
                                                                        navigate(`/accounts/${acc.id}/analytics`);
                                                                    }}
                                                                    className="text-blue-600 hover:underline cursor-pointer"
                                                                >
                                                                    {acc.aws_account_id}
                                                                </a>
                                                            </td>
                                                            <td className="px-4 py-2"><Badge color={acc.status === 'ACTIVE' ? 'green' : 'gray'}>{acc.status || 'Unknown'}</Badge></td>
                                                            <td className="px-4 py-2 text-right text-gray-500 text-sm">N/A</td>
                                                        </tr>
                                                    ))}
                                                </tbody>
                                            </table>
                                        </div>
                                    ) : (
                                        <p className="text-sm text-gray-500 italic bg-white p-4 rounded border">No cloud accounts connected.</p>
                                    )}

                                    <div className="mt-4 pt-4 border-t flex justify-end">
                                        <Button size="sm" variant="outline">View Full User Audit</Button>
                                    </div>
                                </div>
                            )}
                        </div>
                    ))}
                </div>
            )}

            {/* === VIEW 3: GOVERNANCE === */}
            {activeTab === 'GOVERNANCE' && (
                <div className="max-w-3xl mx-auto">
                    <TeamGovernance teamId={teamId} />
                </div>
            )}

            {/* Member Permissions Modal */}
            <MemberPermissionsModal
                isOpen={permissionsModalOpen}
                onClose={() => {
                    setPermissionsModalOpen(false);
                    setSelectedMemberForPermissions(null);
                }}
                member={selectedMemberForPermissions}
                onSave={async (memberId, permissions) => {
                    try {
                        await teamAPI.updateMemberPermissions(teamId, memberId, permissions);
                        toast.success('Member permissions updated');
                        setPermissionsModalOpen(false);
                        fetchData(); // Refresh to show updated permissions
                    } catch (err) {
                        console.error("Failed to update permissions", err);
                        toast.error(err.response?.data?.detail || 'Failed to update permissions');
                    }
                }}
            />
        </div>
    );
};

export default TeamDetails;
