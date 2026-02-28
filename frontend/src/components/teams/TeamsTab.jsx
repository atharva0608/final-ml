import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { teamAPI, organizationAPI } from '../../services/api';
import { FiPlus, FiArrowRight } from 'react-icons/fi';
import toast from 'react-hot-toast';

function StatBox({ label, value, valueColor }) {
    return (
        <div className="bg-gray-50 rounded-lg p-3">
            <div className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-1">{label}</div>
            <div className={`text-xl font-bold ${valueColor}`}>{value}</div>
        </div>
    );
}

function TeamCard({ team, memberCount, onClick }) {
    return (
        <div onClick={onClick}
            className="bg-white border border-gray-200 rounded-xl p-6 cursor-pointer relative overflow-hidden transition-all hover:-translate-y-1 hover:shadow-lg group"
        >
            <div className="flex justify-between items-start mb-6">
                <h3 className="text-lg font-bold text-gray-900 group-hover:text-blue-700 transition-colors">{team.name}</h3>
            </div>

            <div className="grid grid-cols-2 gap-4 mb-6">
                <StatBox label="Members" value={memberCount} valueColor="text-gray-900" />
                <StatBox label="Monthly Cost" value={`$${(team.monthly_cost || 0).toLocaleString()}`} valueColor="text-emerald-500" />
                <StatBox label="Resources" value={team.resource_count || 0} valueColor="text-indigo-600" />
                <StatBox label="Savings" value={`~$${(team.savings_realized || 0).toLocaleString()}`} valueColor="text-orange-500" />
            </div>

            <div className="flex items-center gap-2 text-blue-600 font-bold text-sm group-hover:gap-3 transition-all">
                View details <FiArrowRight />
            </div>
        </div>
    );
}

export default function TeamsTab() {
    const navigate = useNavigate();
    const [teams, setTeams] = useState([]);
    const [members, setMembers] = useState([]);
    const [loading, setLoading] = useState(true);
    const [showCreate, setShowCreate] = useState(false);
    const [newTeamName, setNewTeamName] = useState("");

    useEffect(() => {
        fetchData();
    }, []);

    const fetchData = async () => {
        setLoading(true);
        try {
            const [tRes, mRes] = await Promise.all([
                teamAPI.list(),
                organizationAPI.getMembers()
            ]);
            setTeams(tRes.data || []);
            setMembers(mRes.data.members || []);
        } catch (err) {
            toast.error("Failed to load teams");
        } finally {
            setLoading(false);
        }
    };

    const handleCreate = async () => {
        if (!newTeamName.trim()) return;
        try {
            await teamAPI.create(newTeamName);
            toast.success(`Team "${newTeamName}" created`);
            setNewTeamName("");
            setShowCreate(false);
            fetchData();
        } catch (err) {
            toast.error(err.response?.data?.detail || "Failed to create team");
        }
    };

    if (loading) return <div className="p-8 text-center text-gray-500 text-lg">Loading teams...</div>;

    return (
        <div>
            <div className="flex justify-between items-end mb-8">
                <div>
                    <h2 className="text-xl font-bold text-gray-900">Active Teams</h2>
                    <p className="text-base text-gray-500 mt-1">Manage team structures and resource allocation.</p>
                </div>
                <button onClick={() => setShowCreate(true)}
                    className="bg-blue-600 text-white px-5 py-2.5 rounded-lg text-base font-bold flex items-center gap-2 hover:bg-blue-700 transition-colors shadow-sm hover:shadow">
                    <FiPlus className="w-5 h-5" /> Create Team
                </button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {teams.map(team => (
                    <TeamCard
                        key={team.id}
                        team={team}
                        memberCount={members.filter(m => m.team_id === team.id).length}
                        onClick={() => navigate(`/teams/${team.id}`)}
                    />
                ))}

                {/* Add New Card Equivalent */}
                <button onClick={() => setShowCreate(true)}
                    className="bg-gray-50 border-2 border-dashed border-gray-200 rounded-xl flex flex-col items-center justify-center min-h-[260px] cursor-pointer text-gray-400 hover:border-gray-400 hover:text-gray-600 transition-all group">
                    <div className="w-12 h-12 rounded-full bg-white border border-gray-200 flex items-center justify-center mb-3 group-hover:scale-110 transition-transform shadow-sm">
                        <FiPlus size={24} />
                    </div>
                    <span className="text-base font-bold">Create new team</span>
                </button>
            </div>

            {/* Create Modal */}
            {showCreate && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
                    <div className="bg-white p-6 rounded-xl w-full max-w-md shadow-2xl">
                        <h3 className="text-xl font-bold mb-6 text-gray-900">Create New Team</h3>
                        <input
                            autoFocus
                            placeholder="e.g. Engineering, Sales..."
                            value={newTeamName}
                            onChange={e => setNewTeamName(e.target.value)}
                            onKeyDown={e => e.key === 'Enter' && handleCreate()}
                            className="w-full border border-gray-300 rounded-lg px-4 py-3 mb-8 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all"
                        />
                        <div className="flex justify-end gap-3">
                            <button onClick={() => setShowCreate(false)} className="px-5 py-2.5 text-gray-600 font-medium hover:bg-gray-100 rounded-lg text-base">Cancel</button>
                            <button onClick={handleCreate} className="px-5 py-2.5 bg-blue-600 text-white font-bold rounded-lg hover:bg-blue-700 text-base shadow-sm">Create Team</button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
