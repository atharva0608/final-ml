import React, { useState, useEffect } from 'react';
import { rolesAPI } from '../../services/api';
import PermissionMatrix from '../policies/PermissionMatrix';
import { FiShield, FiLock, FiEdit2, FiSave, FiPlus } from 'react-icons/fi';
import toast from 'react-hot-toast';

export default function RolesPoliciesTopTab() {
    const [roles, setRoles] = useState([]);
    const [permissions, setPermissions] = useState([]);
    const [loading, setLoading] = useState(true);
    const [editingRole, setEditingRole] = useState(null);
    const [selectedPerms, setSelectedPerms] = useState([]);

    useEffect(() => {
        fetchData();
    }, []);

    const fetchData = async () => {
        setLoading(true);
        try {
            const [rRes, pRes] = await Promise.all([
                rolesAPI.listRoles(),
                rolesAPI.listPermissions()
            ]);
            setRoles(rRes.data.roles || []);
            setPermissions(pRes.data.permissions || []);
        } catch (err) {
            toast.error("Failed to load roles data");
        } finally {
            setLoading(false);
        }
    };

    const handleEdit = (role) => {
        setEditingRole(role);
        setSelectedPerms(role.permissions?.map(p => p.slug) || []);
    };

    const handleCreate = () => {
        setEditingRole({ name: '', description: '', permissions: [], type: 'CUSTOM' });
        setSelectedPerms([]);
    };

    const handleSave = async () => {
        if (!editingRole) return;
        if (!editingRole.name) {
            toast.error("Role name is required");
            return;
        }

        try {
            if (editingRole.id) {
                await rolesAPI.updateRole(editingRole.id, {
                    ...editingRole,
                    permission_slugs: selectedPerms
                });
                toast.success("Role updated successfully");
            } else {
                await rolesAPI.createRole({
                    name: editingRole.name,
                    description: editingRole.description,
                    permission_slugs: selectedPerms
                });
                toast.success("Role created successfully");
            }
            setEditingRole(null);
            fetchData();
        } catch (err) {
            toast.error(err.response?.data?.detail || "Failed to save role");
        }
    };

    if (loading) return <div className="p-8 text-center text-gray-500 text-lg">Loading roles & policies...</div>;

    // Editor View
    if (editingRole) {
        const isNew = !editingRole.id;
        return (
            <div className="animate-in fade-in slide-in-from-bottom-4 duration-300">
                <div className="flex items-center justify-between mb-8">
                    <div>
                        <h2 className="text-2xl font-bold flex items-center gap-2 text-gray-900">
                            {isNew ? 'Create Custom Role' : (
                                <>
                                    <span className="text-gray-400 font-normal">Editing:</span>
                                    {editingRole.name}
                                </>
                            )}
                        </h2>
                        <p className="text-base text-gray-500 mt-1">Configure permissions for this role.</p>
                    </div>
                    <div className="flex gap-3">
                        <button onClick={() => setEditingRole(null)}
                            className="px-5 py-2.5 border border-gray-300 rounded-lg text-gray-700 font-medium hover:bg-gray-50 transition-colors text-base">
                            Cancel
                        </button>
                        <button onClick={handleSave}
                            className="px-5 py-2.5 bg-blue-600 text-white rounded-lg font-bold hover:bg-blue-700 transition-colors flex items-center gap-2 text-base shadow-sm hover:shadow">
                            <FiSave /> Save Role
                        </button>
                    </div>
                </div>

                <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-8">
                    <div className="grid grid-cols-2 gap-6 mb-8">
                        <div>
                            <label className="block text-sm font-bold text-gray-700 mb-2">Role Name</label>
                            <input
                                value={editingRole.name}
                                onChange={e => setEditingRole({ ...editingRole, name: e.target.value })}
                                placeholder="e.g. Finance Auditor"
                                className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition-all"
                                disabled={!isNew && editingRole.type === 'SYSTEM'}
                            />
                        </div>
                        <div>
                            <label className="block text-sm font-bold text-gray-700 mb-2">Description</label>
                            <input
                                value={editingRole.description || ''}
                                onChange={e => setEditingRole({ ...editingRole, description: e.target.value })}
                                placeholder="What is this role for?"
                                className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition-all"
                            />
                        </div>
                    </div>

                    <div className="border-t pt-6">
                        <h3 className="text-lg font-bold text-gray-900 mb-4">Permissions</h3>
                        <PermissionMatrix
                            allPermissions={permissions}
                            selectedSlugs={selectedPerms}
                            onChange={setSelectedPerms}
                            readOnly={editingRole.type === 'SYSTEM'}
                        />
                    </div>
                </div>
            </div>
        );
    }

    // Grid View
    return (
        <div>
            <div className="mb-8 flex justify-between items-end">
                <div>
                    <h2 className="text-xl font-bold text-gray-900">Roles & Access Policies</h2>
                    <p className="text-base text-gray-500 mt-1">Manage what users can do in your organization.</p>
                </div>
                <button
                    onClick={handleCreate}
                    className="flex items-center gap-2 px-5 py-2.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-base font-bold shadow-sm hover:shadow transition-all">
                    <FiPlus className="w-5 h-5" /> Create Custom Role
                </button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {roles.map(role => {
                    const isSystem = role.type === 'SYSTEM';
                    return (
                        <div key={role.id}
                            onClick={() => handleEdit(role)}
                            className="bg-white rounded-xl border border-gray-200 p-6 hover:shadow-lg transition-all cursor-pointer group hover:border-blue-300 relative overflow-hidden flex flex-col h-full">

                            <div className={`absolute top-0 right-0 p-3 ${isSystem ? 'text-gray-300' : 'text-blue-500 opacity-0 group-hover:opacity-100 transition-opacity'}`}>
                                {isSystem ? <FiLock size={18} /> : <FiEdit2 size={18} />}
                            </div>

                            <div className="flex items-center gap-4 mb-5">
                                <div className={`w-12 h-12 rounded-xl flex items-center justify-center text-xl shrink-0 ${isSystem ? 'bg-gray-100 text-gray-500' : 'bg-blue-50 text-blue-600'}`}>
                                    <FiShield />
                                </div>
                                <div>
                                    <h3 className="font-bold text-gray-900 text-lg group-hover:text-blue-700 transition-colors line-clamp-1">{role.name}</h3>
                                    <span className={`text-[11px] px-2.5 py-0.5 rounded-full font-bold uppercase tracking-wide ${isSystem ? 'bg-gray-100 text-gray-600' : 'bg-blue-100 text-blue-700'}`}>
                                        {role.type}
                                    </span>
                                </div>
                            </div>

                            <p className="text-base text-gray-500 mb-6 flex-grow">
                                {role.description || "No description provided."}
                            </p>

                            <div className="flex items-center justify-between text-sm text-gray-400 border-t pt-5 mt-auto">
                                <span className="font-medium text-gray-500">{role.permissions?.length || 0} permissions</span>
                                <span className="group-hover:translate-x-1 transition-transform text-blue-600 font-semibold opacity-0 group-hover:opacity-100">Configure &rarr;</span>
                            </div>
                        </div>
                    );
                })}
            </div>
        </div>
    );
}
