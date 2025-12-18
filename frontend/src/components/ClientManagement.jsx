import React, { useState, useEffect } from 'react';
import {
    Users, Search, Shield, Lock, Unlock, Trash2,
    MoreHorizontal, Activity, AlertTriangle, Plus, CheckCircle, X, Save
} from 'lucide-react';
import { cn } from '../lib/utils';
import api from '../services/api';

const ClientCreateModal = ({ onClose, onCreate }) => {
    const [formData, setFormData] = useState({
        username: '',
        email: '',
        password: '',
        full_name: '',
        role: 'user',
        is_active: true
    });

    const handleSubmit = (e) => {
        e.preventDefault();
        if (!formData.username || !formData.email || !formData.password) {
            alert("Username, email, and password are required");
            return;
        }
        onCreate(formData);
    };

    return (
        <div className="fixed inset-0 bg-black/50 z-[100] flex items-center justify-center backdrop-blur-sm animate-in fade-in duration-200">
            <div className="bg-white rounded-xl shadow-2xl w-full max-w-md overflow-hidden transform transition-all scale-100 p-0">
                <div className="px-6 py-4 border-b border-slate-100 flex justify-between items-center bg-slate-50/50">
                    <h3 className="text-lg font-bold text-slate-900">Add New User</h3>
                    <button onClick={onClose} className="text-slate-400 hover:text-slate-600 transition-colors">
                        <X className="w-5 h-5" />
                    </button>
                </div>

                <form onSubmit={handleSubmit} className="p-6 space-y-4">
                    <div>
                        <label className="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-1.5">Username *</label>
                        <input
                            type="text"
                            required
                            value={formData.username}
                            onChange={e => setFormData({ ...formData, username: e.target.value })}
                            className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none"
                            placeholder="Enter username"
                        />
                    </div>

                    <div>
                        <label className="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-1.5">Email *</label>
                        <input
                            type="email"
                            required
                            value={formData.email}
                            onChange={e => setFormData({ ...formData, email: e.target.value })}
                            className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none"
                            placeholder="user@example.com"
                        />
                    </div>

                    <div>
                        <label className="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-1.5">Password *</label>
                        <input
                            type="password"
                            required
                            value={formData.password}
                            onChange={e => setFormData({ ...formData, password: e.target.value })}
                            className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none"
                            placeholder="Enter password"
                        />
                    </div>

                    <div>
                        <label className="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-1.5">Full Name</label>
                        <input
                            type="text"
                            value={formData.full_name}
                            onChange={e => setFormData({ ...formData, full_name: e.target.value })}
                            className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none"
                            placeholder="Enter full name"
                        />
                    </div>

                    <div>
                        <label className="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-1.5">Role</label>
                        <select
                            value={formData.role}
                            onChange={e => setFormData({ ...formData, role: e.target.value })}
                            className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none bg-white"
                        >
                            <option value="admin">Administrator (Full Access)</option>
                            <option value="user">Standard User</option>
                            <option value="lab">Lab Researcher</option>
                        </select>
                    </div>

                    <div className="flex items-center justify-end pt-4 border-t border-slate-100 gap-3">
                        <button
                            type="button"
                            onClick={onClose}
                            className="px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50 rounded-lg transition-colors"
                        >
                            Cancel
                        </button>
                        <button
                            type="submit"
                            className="px-4 py-2 bg-slate-900 text-white text-sm font-bold rounded-lg hover:bg-slate-800 transition-all shadow-lg shadow-slate-900/10 flex items-center"
                        >
                            <Save className="w-4 h-4 mr-2" />
                            Create User
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
};

const ClientEditModal = ({ user, onClose, onSave }) => {
    const [formData, setFormData] = useState({ ...user });

    const handleSubmit = (e) => {
        e.preventDefault();
        onSave(formData);
    };

    return (
        <div className="fixed inset-0 bg-black/50 z-[100] flex items-center justify-center backdrop-blur-sm animate-in fade-in duration-200">
            <div className="bg-white rounded-xl shadow-2xl w-full max-w-md overflow-hidden transform transition-all scale-100 p-0">
                <div className="px-6 py-4 border-b border-slate-100 flex justify-between items-center bg-slate-50/50">
                    <h3 className="text-lg font-bold text-slate-900">Manage Access</h3>
                    <button onClick={onClose} className="text-slate-400 hover:text-slate-600 transition-colors">
                        <X className="w-5 h-5" />
                    </button>
                </div>

                <form onSubmit={handleSubmit} className="p-6 space-y-6">
                    <div className="flex items-center space-x-4 mb-6">
                        <div className="w-12 h-12 bg-slate-100 rounded-full flex items-center justify-center text-slate-500 font-bold text-xl">
                            {(user.name || '?').charAt(0).toUpperCase()}
                        </div>
                        <div>
                            <div className="font-bold text-slate-900 text-lg">{user.name || 'Unknown'}</div>
                            <div className="text-sm text-slate-500">{user.email}</div>
                        </div>
                    </div>

                    <div className="space-y-4">
                        <div>
                            <label className="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-1.5">Role</label>
                            <select
                                value={formData.role}
                                onChange={e => setFormData({ ...formData, role: e.target.value })}
                                className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none bg-white"
                            >
                                <option value="admin">Administrator (Full Access)</option>
                                <option value="user">Standard User</option>
                                <option value="lab">Lab Researcher</option>
                            </select>
                        </div>

                        <div className="pt-2">
                            <label className="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">Account Status</label>
                            <div className="flex gap-3">
                                <button
                                    type="button"
                                    onClick={() => setFormData({ ...formData, is_active: true })}
                                    className={cn(
                                        "flex-1 py-2 px-3 rounded-lg border text-sm font-bold transition-all flex items-center justify-center",
                                        formData.is_active
                                            ? "bg-emerald-50 border-emerald-200 text-emerald-700 ring-1 ring-emerald-500/20"
                                            : "border-slate-200 text-slate-500 hover:bg-slate-50"
                                    )}
                                >
                                    <CheckCircle className="w-4 h-4 mr-2" /> Active
                                </button>
                                <button
                                    type="button"
                                    onClick={() => setFormData({ ...formData, is_active: false })}
                                    className={cn(
                                        "flex-1 py-2 px-3 rounded-lg border text-sm font-bold transition-all flex items-center justify-center",
                                        !formData.is_active
                                            ? "bg-red-50 border-red-200 text-red-700 ring-1 ring-red-500/20"
                                            : "border-slate-200 text-slate-500 hover:bg-slate-50"
                                    )}
                                >
                                    <Lock className="w-4 h-4 mr-2" /> Blocked
                                </button>
                            </div>
                        </div>
                    </div>

                    <div className="flex items-center justify-end pt-4 border-t border-slate-100 gap-3">
                        <button
                            type="button"
                            onClick={onClose}
                            className="px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50 rounded-lg transition-colors"
                        >
                            Cancel
                        </button>
                        <button
                            type="submit"
                            className="px-4 py-2 bg-slate-900 text-white text-sm font-bold rounded-lg hover:bg-slate-800 transition-all shadow-lg shadow-slate-900/10 flex items-center"
                        >
                            <Save className="w-4 h-4 mr-2" />
                            Apply Changes
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
};

const ClientManagement = () => {
    const [users, setUsers] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [searchTerm, setSearchTerm] = useState('');
    const [selectedUser, setSelectedUser] = useState(null);
    const [showCreateModal, setShowCreateModal] = useState(false);

    // Fetch users on mount
    const fetchUsers = async () => {
        try {
            setLoading(true);
            const data = await api.getUsers();
            setUsers(data);
            setError(null);
        } catch (err) {
            console.error("Failed to fetch users", err);
            setError("Failed to load users. Please check your connection.");
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchUsers();
    }, []);

    const handleSave = async (updatedUser) => {
        // Optimistic UI update
        const previousUsers = [...users];
        setUsers(prev => prev.map(u => u.id === updatedUser.id ? updatedUser : u));

        try {
            // Call API in background
            if (updatedUser.role !== selectedUser.role) {
                await api.updateUserRole(updatedUser.id, updatedUser.role);
            }
            if (updatedUser.is_active !== selectedUser.is_active) {
                await api.updateUserStatus(updatedUser.id, updatedUser.is_active);
            }
            // Refresh to ensure sync
            await fetchUsers();
        } catch (e) {
            console.error(e);
            // Revert on error
            setUsers(previousUsers);
            alert("Failed to update user. Please try again.");
        }

        setSelectedUser(null);
    };

    const handleDelete = async (userId, e) => {
        e.stopPropagation();
        if (window.confirm("Permanently delete this user?")) {
            const previousUsers = [...users];
            setUsers(prev => prev.filter(u => u.id !== userId));
            try {
                await api.deleteUser(userId);
            } catch (e) {
                console.error(e);
                setUsers(previousUsers);
                alert("Failed to delete user.");
            }
        }
    };

    const handleCreateClient = async (newUserData) => {
        try {
            // Call API to create new user
            const createdUser = await api.createClient(newUserData);
            // Add to list
            setUsers(prev => [...prev, createdUser]);
            // Close modal
            setShowCreateModal(false);
            // Refresh list to ensure sync
            await fetchUsers();
        } catch (e) {
            console.error("Failed to create user:", e);
            alert("Failed to create user. Please try again.");
        }
    };

    const filteredUsers = users.filter(user =>
        (user.name || '').toLowerCase().includes(searchTerm.toLowerCase()) ||
        (user.email || '').toLowerCase().includes(searchTerm.toLowerCase())
    );

    return (
        <div className="space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
            {selectedUser && (
                <ClientEditModal
                    user={selectedUser}
                    onClose={() => setSelectedUser(null)}
                    onSave={handleSave}
                />
            )}

            {showCreateModal && (
                <ClientCreateModal
                    onClose={() => setShowCreateModal(false)}
                    onCreate={handleCreateClient}
                />
            )}

            {/* Header */}
            <div className="flex justify-between items-end">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900 mb-2 tracking-tight">Client Management</h1>
                    <p className="text-slate-500 text-sm">Manage clients, monitor topology, and control platform access</p>
                </div>
                <button
                    onClick={() => setShowCreateModal(true)}
                    className="flex items-center space-x-2 px-4 py-2 bg-slate-900 text-white text-sm font-bold rounded shadow-sm hover:bg-slate-800 transition-colors"
                >
                    <Plus className="w-4 h-4" /> <span>Add Client</span>
                </button>
            </div>

            {/* Table */}
            <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
                <div className="p-4 border-b border-slate-200 bg-slate-50/50 flex justify-between items-center">
                    <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wider">User Directory</h3>
                    <div className="relative">
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                        <input
                            type="text"
                            placeholder="Search users..."
                            className="pl-9 pr-4 py-1.5 border border-slate-200 rounded text-sm focus:ring-2 focus:ring-blue-500 outline-none w-64 bg-white"
                            value={searchTerm}
                            onChange={(e) => setSearchTerm(e.target.value)}
                        />
                    </div>
                </div>

                <div className="overflow-x-auto">
                    {loading ? (
                        <div className="p-12 text-center text-slate-400 italic">Loading users...</div>
                    ) : error ? (
                        <div className="p-12 text-center text-red-500 bg-red-50 flex flex-col items-center">
                            <AlertTriangle className="w-8 h-8 mb-2" />
                            {error}
                        </div>
                    ) : filteredUsers.length === 0 ? (
                        <div className="p-12 text-center text-slate-400">No users found.</div>
                    ) : (
                        <table className="w-full text-left text-sm">
                            <thead className="bg-slate-50 text-slate-500 font-medium border-b border-slate-200">
                                <tr>
                                    <th className="px-6 py-3">User</th>
                                    <th className="px-6 py-3">Role</th>
                                    <th className="px-6 py-3">Status</th>
                                    <th className="px-6 py-3">Last Login</th>
                                    <th className="px-6 py-3 text-right">Actions</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-100">
                                {filteredUsers.map(user => (
                                    <tr
                                        key={user.id}
                                        onClick={() => setSelectedUser(user)}
                                        className="hover:bg-slate-50 transition-colors cursor-pointer group"
                                    >
                                        <td className="px-6 py-4">
                                            <div className="flex items-center">
                                                <div className="w-8 h-8 rounded-full bg-slate-100 flex items-center justify-center text-slate-500 mr-3 font-bold border border-slate-200">
                                                    {(user.name || user.email || '?').charAt(0).toUpperCase()}
                                                </div>
                                                <div>
                                                    <div className="font-bold text-slate-900">{user.name || 'Unknown'}</div>
                                                    <div className="text-xs text-slate-500">{user.email}</div>
                                                </div>
                                            </div>
                                        </td>
                                        <td className="px-6 py-4">
                                            <span className={cn("px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider border rounded-sm",
                                                user.role === 'admin' ? "bg-purple-50 text-purple-700 border-purple-200" :
                                                    user.role === 'lab' ? "bg-amber-50 text-amber-700 border-amber-200" :
                                                        "bg-blue-50 text-blue-700 border-blue-200"
                                            )}>
                                                {user.role}
                                            </span>
                                        </td>
                                        <td className="px-6 py-4">
                                            <div className="flex items-center">
                                                <div className={cn("w-2 h-2 rounded-full mr-2", user.is_active ? "bg-emerald-500" : "bg-red-500")}></div>
                                                <span className={cn("text-xs font-medium", user.is_active ? "text-slate-700" : "text-red-600")}>
                                                    {user.is_active ? 'Active' : 'Blocked'}
                                                </span>
                                            </div>
                                        </td>
                                        <td className="px-6 py-4 text-slate-500 font-mono text-xs">
                                            {user.last_login ? new Date(user.last_login).toLocaleDateString() : 'Never'}
                                        </td>
                                        <td className="px-6 py-4 text-right">
                                            <button
                                                onClick={(e) => handleDelete(user.id, e)}
                                                className="p-1.5 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded transition-colors"
                                                title="Delete User"
                                            >
                                                <Trash2 className="w-4 h-4" />
                                            </button>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    )}
                </div>
            </div>
        </div>
    );
};

export default ClientManagement;
