import React, { useState, useEffect } from 'react';
import { rolesAPI } from '../services/api';
import PermissionMatrix from '../components/policies/PermissionMatrix';
import { Button, Card } from '../components/shared';
import toast from 'react-hot-toast';

const Roles = () => {
    const [roles, setRoles] = useState([]);
    const [permissions, setPermissions] = useState([]);
    const [editingRole, setEditingRole] = useState(null); // The role currently being edited
    const [selectedPerms, setSelectedPerms] = useState([]);
    const [loading, setLoading] = useState(true);

    // Fetch Data on Load
    useEffect(() => {
        const load = async () => {
            try {
                const [rData, pData] = await Promise.all([
                    rolesAPI.listRoles(),
                    rolesAPI.listPermissions()
                ]);
                setRoles(rData.data.roles || []);
                setPermissions(pData.data.permissions || []);
            } catch (err) {
                console.error(err);
                toast.error("Failed to load roles/permissions");
            } finally {
                setLoading(false);
            }
        };
        load();
    }, []);

    const handleSave = async () => {
        if (!editingRole) return;
        try {
            await rolesAPI.updateRole(editingRole.id, {
                ...editingRole,
                permission_slugs: selectedPerms
            });

            // Update local state
            setRoles(prev => prev.map(r =>
                r.id === editingRole.id
                    ? { ...r, permissions: permissions.filter(p => selectedPerms.includes(p.slug)) }
                    : r
            ));

            setEditingRole(null);
            toast.success("Role Updated!");
        } catch (err) {
            toast.error("Failed to update role");
            console.error(err);
        }
    };

    if (loading) return <div className="p-8">Loading...</div>;

    return (
        <div className="space-y-6">
            {/* Header Removed for Tabbed View Integration */}


            {/* Role Manager */}
            {!editingRole && (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                    {roles.map(role => (
                        <div
                            key={role.id}
                            onClick={() => {
                                setEditingRole(role);
                                setSelectedPerms(role.permissions?.map(p => p.slug) || []);
                            }}
                            className="bg-white rounded-xl border border-gray-200 p-6 hover:shadow-lg transition-all cursor-pointer hover:border-blue-300 group"
                        >
                            <div className="flex justify-between items-start mb-4">
                                <h3 className="text-xl font-bold text-gray-900 group-hover:text-blue-600 transition-colors">{role.name}</h3>
                                {role.type === 'SYSTEM' ? (
                                    <span className="bg-gray-100 text-gray-600 text-xs px-2 py-1 rounded font-medium">System</span>
                                ) : (
                                    <span className="bg-blue-100 text-blue-600 text-xs px-2 py-1 rounded font-medium">Custom</span>
                                )}
                            </div>
                            <p className="text-gray-500 text-sm mb-4 min-h-[40px]">{role.description || "No description provided."}</p>
                            <div className="text-xs text-gray-400">
                                {role.permissions?.length || 0} permissions assigned
                            </div>
                        </div>
                    ))}
                </div>
            )}

            {/* Editor Area */}
            {editingRole && (
                <div className="space-y-6">
                    <div className="flex items-center justify-between">
                        <h2 className="text-xl font-bold text-gray-800">
                            Editing: <span className="text-blue-600">{editingRole.name}</span>
                        </h2>
                        <Button variant="outline" onClick={() => setEditingRole(null)}>Cancel</Button>
                    </div>

                    <Card>
                        <div className="mb-6">
                            <PermissionMatrix
                                allPermissions={permissions}
                                selectedSlugs={selectedPerms}
                                onChange={setSelectedPerms}
                                readOnly={editingRole.name === 'Organization Admin' || editingRole.name === 'Client'} // Prevent locking yourself out
                            />
                        </div>
                        <div className="flex justify-end p-4 border-t bg-gray-50 -mx-6 -mb-6 rounded-b-lg">
                            <Button onClick={handleSave}>Save Changes</Button>
                        </div>
                    </Card>
                </div>
            )}
        </div>
    );
};

export default Roles;
