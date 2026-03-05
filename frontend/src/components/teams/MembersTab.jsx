import React, { useState, useEffect } from 'react';
import { organizationAPI, teamAPI } from '../../services/api';
import { FiUser, FiMoreVertical, FiEdit2, FiTrash2, FiUsers, FiMail, FiCheck, FiX, FiShield, FiBriefcase } from 'react-icons/fi';
import toast from 'react-hot-toast';

const ROLE_META = {
    ORG_ADMIN: { bg: "#fef3c7", text: "#92400e", label: "Org Admin" }, // Amber
    TEAM_LEAD: { bg: "#dbeafe", text: "#1e40af", label: "Team Lead" }, // Blue
    MEMBER: { bg: "#f0fdf4", text: "#166534", label: "Member" }, // Green
};

const STATUS_META = {
    ACTIVE: { dot: "#10b981", label: "Active", bg: "#d1fae5", text: "#065f46" },
    PENDING_INVITE: { dot: "#f59e0b", label: "Invited", bg: "#fef9c3", text: "#854d0e" },
};

function initials(name = "", email = "") {
    if (name?.trim()) return name.split(" ").map(w => w[0]).join("").slice(0, 2).toUpperCase();
    return email?.slice(0, 2).toUpperCase() || "??";
}

const AV_COLORS = ["#6366f1", "#0ea5e9", "#10b981", "#f59e0b", "#f43f5e", "#8b5cf6", "#ec4899"];
function avColor(s = "") { return AV_COLORS[(s.charCodeAt(0) || 0) % AV_COLORS.length]; }

function Avatar({ name = "", email = "", size = 40 }) {
    const label = initials(name, email);
    return (
        <div style={{
            width: size, height: size, borderRadius: "50%", background: avColor(name || email),
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: size * 0.4, fontWeight: 700, color: "#fff", flexShrink: 0, letterSpacing: "-0.5px"
        }}>
            {label}
        </div>
    );
}

function Chip({ bg, color, children }) {
    return <span style={{ fontSize: 12, fontWeight: 600, background: bg, color, padding: "2px 10px", borderRadius: 20, whiteSpace: "nowrap", display: "inline-block" }}>{children}</span>;
}

export default function MembersTab() {
    const [filter, setFilter] = useState("ACTIVE");
    const [teamFilter, setTeamFilter] = useState("all");
    const [search, setSearch] = useState("");
    const [openMenu, setOpenMenu] = useState(null);
    const [showInvite, setShowInvite] = useState(false);

    const [inviteEmail, setInviteEmail] = useState("");
    const [inviteName, setInviteName] = useState("");
    const [inviteRole, setInviteRole] = useState("MEMBER");
    const [inviteTeam, setInviteTeam] = useState("");

    const [members, setMembers] = useState([]);
    const [teams, setTeams] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        fetchData();
    }, []);

    const fetchData = async () => {
        setLoading(true);
        try {
            const [mRes, tRes] = await Promise.all([
                organizationAPI.getMembers(),
                teamAPI.list()
            ]);
            setMembers(mRes.data.members || []);
            setTeams(tRes.data || []);
        } catch (err) {
            toast.error("Failed to load members/teams");
        } finally {
            setLoading(false);
        }
    };

    const handleInvite = async () => {
        if (!inviteEmail) return;
        try {
            if (inviteTeam) {
                await teamAPI.invite(inviteTeam, inviteEmail, inviteRole, inviteName);
            } else {
                await organizationAPI.inviteMember(inviteEmail, inviteRole, 'FULL');
            }

            toast.success(`Invitation sent to ${inviteEmail}`);
            setShowInvite(false);
            setInviteEmail("");
            setInviteName("");
            fetchData();
        } catch (err) {
            toast.error(err.response?.data?.detail || "Failed to invite member");
        }
    };

    const handleRemove = async (id) => {
        if (!window.confirm("Are you sure you want to remove this member?")) return;
        try {
            await organizationAPI.removeMember(id);
            toast.success("Member removed");
            setMembers(prev => prev.filter(m => m.id !== id));
        } catch (err) {
            toast.error("Failed to remove member");
        }
    };

    const teamName = id => teams.find(t => t.id === id)?.name;
    const teamColor = id => {
        const colors = ["#6366f1", "#0ea5e9", "#10b981", "#f59e0b", "#f43f5e", "#8b5cf6"];
        return colors[(id?.charCodeAt(0) || 0) % colors.length];
    }

    const filtered = members.filter(m => {
        const isPending = m.status === "PENDING_INVITE";
        const statusMatch = filter === "ACTIVE" ? !isPending : isPending;
        const teamMatch = teamFilter === "all" || m.team_id === teamFilter;
        const q = search.toLowerCase();
        const searchMatch = !q || (m.full_name || "").toLowerCase().includes(q) || m.email.toLowerCase().includes(q);
        return statusMatch && teamMatch && searchMatch;
    });

    if (loading) return <div className="p-8 text-center text-gray-500 text-lg">Loading members...</div>;

    return (
        <div>
            {/* Stats */}
            <div className="grid grid-cols-3 gap-4 mb-6">
                {[
                    ["Active members", members.filter(m => m.status !== "PENDING_INVITE").length, "#0f172a"],
                    ["Pending invites", members.filter(m => m.status === "PENDING_INVITE").length, "#d97706"],
                    ["Unassigned", members.filter(m => !m.team_id).length, "#dc2626"],
                ].map(([l, v, c]) => (
                    <div key={l} style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 12, padding: "16px 20px", boxShadow: "0 1px 2px rgba(0,0,0,0.04)" }}>
                        <p style={{ fontSize: 13, color: "#64748b", margin: "0 0 4px", fontWeight: 600 }}>{l}</p>
                        <p style={{ fontSize: 24, fontWeight: 800, color: c, margin: 0 }}>{v}</p>
                    </div>
                ))}
            </div>

            {/* Toolbar */}
            <div className="flex items-center justify-between mb-5 gap-3 flex-wrap">
                <div className="flex items-center gap-3">
                    <button onClick={() => setShowInvite(true)}
                        className="bg-blue-600 text-white border-none rounded-lg px-4 py-2.5 text-sm font-bold cursor-pointer flex items-center gap-2 hover:bg-blue-700 transition-colors shadow-sm">
                        <FiUser className="w-5 h-5" /> Invite Member
                    </button>
                    <div className="flex bg-slate-100 rounded-lg p-1">
                        {["ACTIVE", "INVITED"].map(s => (
                            <button key={s} onClick={() => setFilter(s)} style={{
                                padding: "6px 14px", borderRadius: 6, fontSize: 13, fontWeight: 600, border: "none", cursor: "pointer",
                                background: filter === s ? "#fff" : "transparent", color: filter === s ? "#0f172a" : "#64748b",
                                boxShadow: filter === s ? "0 1px 3px rgba(0,0,0,0.08)" : "none", transition: "all 0.15s",
                            }}>{s === "ACTIVE" ? "Active" : "Pending"}</button>
                        ))}
                    </div>
                </div>
                <div className="flex items-center gap-3">
                    <select value={teamFilter} onChange={e => setTeamFilter(e.target.value)}
                        style={{ fontSize: 13, border: "1px solid #cbd5e1", borderRadius: 8, padding: "8px 12px", background: "#fff", cursor: "pointer", outline: "none", minWidth: 140 }}>
                        <option value="all">All Teams</option>
                        {teams.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
                    </select>
                </div>
                <div className="relative">
                    <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm"><FiUsers /></span>
                    <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search members…"
                        style={{ paddingLeft: 34, paddingRight: 12, paddingTop: 9, paddingBottom: 9, fontSize: 14, border: "1px solid #cbd5e1", borderRadius: 8, width: 240, outline: "none" }} />
                </div>
            </div>

            {/* Table */}
            <div style={{ background: "#fff", borderRadius: 12, border: "1px solid #e2e8f0", overflow: "hidden", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
                <div style={{ display: "grid", gridTemplateColumns: "2.5fr 2fr 1.5fr 1.3fr 1fr 80px", padding: "12px 20px", background: "#f8fafc", borderBottom: "1px solid #e2e8f0" }}>
                    {["Member", "Email", "Team", "Role", "Status", ""].map(h => (
                        <span key={h} style={{ fontSize: 11, fontWeight: 700, color: "#64748b", textTransform: "uppercase", letterSpacing: "0.05em" }}>{h}</span>
                    ))}
                </div>

                {filtered.length === 0 ? (
                    <div style={{ textAlign: "center", padding: "48px 0", color: "#9ca3af", fontSize: 14 }}>
                        {search ? "No members match your search." : "No members in this view."}
                    </div>
                ) : filtered.map((m, i) => {
                    const sm = STATUS_META[m.status] || STATUS_META.ACTIVE;
                    const roleKey = ROLE_META[m.role] ? m.role : 'MEMBER';
                    const rm = ROLE_META[roleKey];
                    const tn = teamName(m.team_id);
                    const tc = teamColor(m.team_id);

                    return (
                        <div key={m.id}
                            style={{
                                display: "grid", gridTemplateColumns: "2.5fr 2fr 1.5fr 1.3fr 1fr 80px", padding: "16px 20px",
                                borderBottom: i < filtered.length - 1 ? "1px solid #f1f5f9" : "none", alignItems: "center",
                                transition: "background 0.1s", cursor: "default"
                            }}
                            onMouseEnter={e => e.currentTarget.style.background = "#f8fafc"}
                            onMouseLeave={e => e.currentTarget.style.background = "#fff"}>
                            {/* Member */}
                            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                                <div style={{ position: "relative", flexShrink: 0 }}>
                                    <Avatar name={m.full_name} email={m.email} size={40} />
                                    <span style={{ position: "absolute", bottom: 0, right: 0, width: 10, height: 10, borderRadius: "50%", background: sm.dot, border: "2px solid #fff", display: "block" }} />
                                </div>
                                <div>
                                    <div style={{ fontSize: 14, fontWeight: 600, color: "#0f172a" }}>{m.full_name || <em style={{ color: "#9ca3af" }}>No name</em>}</div>
                                    <Chip bg={sm.bg} color={sm.text}>{sm.label}</Chip>
                                </div>
                            </div>
                            {/* Email */}
                            <div style={{ fontSize: 13, color: "#475569", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", paddingRight: 8 }} title={m.email}>{m.email}</div>
                            {/* Team */}
                            <div>
                                {tn
                                    ? <span style={{ fontSize: 13, fontWeight: 600, background: tc + "18", color: tc, padding: "4px 10px", borderRadius: 6 }}>{tn}</span>
                                    : <span style={{ fontSize: 12, color: "#64748b", background: "#f1f5f9", padding: "4px 10px", borderRadius: 6, fontWeight: 600 }}>Unassigned</span>
                                }
                            </div>
                            {/* Role */}
                            <div><Chip bg={rm.bg} color={rm.text}>{rm.label}</Chip></div>
                            {/* Status Loop */}
                            <div style={{ fontSize: 13, color: "#64748b" }}>
                                {m.status === 'PENDING_INVITE' ? 'Invited' : 'Active'}
                            </div>
                            {/* Actions */}
                            <div style={{ position: "relative" }}>
                                <button onClick={() => setOpenMenu(openMenu === m.id ? null : m.id)}
                                    className="bg-transparent border border-gray-200 rounded p-1.5 cursor-pointer text-gray-500 hover:bg-gray-100 transition-colors">
                                    <FiMoreVertical size={16} />
                                </button>
                                {openMenu === m.id && (
                                    <div style={{ position: "absolute", right: 0, top: "110%", background: "#fff", border: "1px solid #e2e8f0", borderRadius: 10, boxShadow: "0 10px 30px rgba(0,0,0,0.1)", zIndex: 50, width: 160, overflow: "hidden" }}
                                        onMouseLeave={() => setOpenMenu(null)}>
                                        {[
                                            { label: "Remove", icon: <FiTrash2 className="w-4 h-4" />, fn: () => { handleRemove(m.id); setOpenMenu(null); }, danger: true },
                                        ].map(item => (
                                            <button key={item.label} onClick={item.fn}
                                                style={{
                                                    display: "flex", alignItems: "center", gap: 10, width: "100%", textAlign: "left", padding: "10px 16px", fontSize: 13, background: "none", border: "none", cursor: "pointer",
                                                    color: item.danger ? "#dc2626" : "#374151", fontWeight: item.danger ? 600 : 400
                                                }}
                                                onMouseEnter={e => e.target.style.background = "#f1f5f9"}
                                                onMouseLeave={e => e.target.style.background = "none"}>
                                                {item.icon} {item.label}
                                            </button>
                                        ))}
                                    </div>
                                )}
                            </div>
                        </div>
                    );
                })}
            </div>

            {/* Invite modal */}
            {showInvite && (
                <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 999 }} onClick={() => setShowInvite(false)}>
                    <div style={{ background: "#fff", borderRadius: 16, width: "100%", maxWidth: 480, boxShadow: "0 25px 50px -12px rgba(0, 0, 0, 0.25)", padding: 0 }} onClick={e => e.stopPropagation()}>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "20px 24px", borderBottom: "1px solid #f1f5f9" }}>
                            <h3 style={{ fontSize: 18, fontWeight: 700, color: "#0f172a", margin: 0 }}>Invite a team member</h3>
                            <button onClick={() => setShowInvite(false)} style={{ background: "none", border: "none", fontSize: 20, cursor: "pointer", color: "#64748b" }}><FiX /></button>
                        </div>
                        <div style={{ padding: 24, display: "flex", flexDirection: "column", gap: 16 }}>
                            <div>
                                <label style={{ fontSize: 13, fontWeight: 600, color: "#374151", display: "block", marginBottom: 6 }}>Full name</label>
                                <input value={inviteName} onChange={e => setInviteName(e.target.value)} placeholder="Jane Smith"
                                    style={{ width: "100%", fontSize: 14, border: "1px solid #cbd5e1", borderRadius: 8, padding: "10px 12px", outline: "none", boxSizing: "border-box" }} />
                            </div>
                            <div>
                                <label style={{ fontSize: 13, fontWeight: 600, color: "#374151", display: "block", marginBottom: 6 }}>Email address *</label>
                                <input value={inviteEmail} onChange={e => setInviteEmail(e.target.value)} placeholder="jane@company.com"
                                    style={{ width: "100%", fontSize: 14, border: "1px solid #cbd5e1", borderRadius: 8, padding: "10px 12px", outline: "none", boxSizing: "border-box" }} />
                            </div>
                            <div>
                                <label style={{ fontSize: 13, fontWeight: 600, color: "#374151", display: "block", marginBottom: 6 }}>Assign to team</label>
                                <select value={inviteTeam} onChange={e => setInviteTeam(e.target.value)}
                                    style={{ width: "100%", fontSize: 14, border: "1px solid #cbd5e1", borderRadius: 8, padding: "10px 12px", background: "#fff", cursor: "pointer", boxSizing: "border-box" }}>
                                    <option value="">No Team (Unassigned)</option>
                                    {teams.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
                                </select>
                            </div>
                            <div>
                                <label style={{ fontSize: 13, fontWeight: 600, color: "#374151", display: "block", marginBottom: 8 }}>Role</label>
                                <div style={{ display: "flex", gap: 10 }}>
                                    {["MEMBER", "TEAM_LEAD"].map(r => {
                                        const rc = ROLE_META[r];
                                        return (
                                            <button key={r} onClick={() => setInviteRole(r)}
                                                style={{ flex: 1, padding: "12px", borderRadius: 8, border: `1.5px solid ${inviteRole === r ? rc.text + "77" : "#e2e8f0"}`, background: inviteRole === r ? rc.bg : "#fff", cursor: "pointer", textAlign: "left" }}>
                                                <div style={{ fontSize: 14, fontWeight: 700, color: inviteRole === r ? rc.text : "#374151" }}>{rc.label}</div>
                                                <div style={{ fontSize: 12, color: "#64748b", marginTop: 2 }}>{r === "MEMBER" ? "Standard access" : "Manage team"}</div>
                                            </button>
                                        );
                                    })}
                                </div>
                            </div>
                            <div style={{ display: "flex", gap: 10, marginTop: 8 }}>
                                <button onClick={() => setShowInvite(false)}
                                    style={{ flex: 1, padding: "10px", borderRadius: 8, border: "1px solid #cbd5e1", background: "#fff", fontSize: 14, fontWeight: 600, cursor: "pointer", color: "#475569" }}>
                                    Cancel
                                </button>
                                <button onClick={handleInvite} disabled={!inviteEmail}
                                    style={{ flex: 2, padding: "10px", borderRadius: 8, border: "none", background: inviteEmail ? "#2563eb" : "#e2e8f0", color: inviteEmail ? "#fff" : "#94a3b8", fontSize: 14, fontWeight: 700, cursor: inviteEmail ? "pointer" : "not-allowed" }}>
                                    Send Invite
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
