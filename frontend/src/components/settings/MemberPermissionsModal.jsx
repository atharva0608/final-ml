/**
 * MemberPermissionsModal Component
 * Allows Team Leads and Org Admins to set granular permission overrides for team members.
 */
import React, { useState, useEffect } from 'react';
import { FiShield, FiX, FiSave } from 'react-icons/fi';
import { Button } from '../shared';

// Define available permission toggles
const AVAILABLE_PERMISSIONS = [
    { key: 'allow_termination', label: 'Can Terminate Resources', description: 'Allows terminating EC2 instances, EBS volumes, etc.' },
    { key: 'allow_cleanup', label: 'Can Execute Cleanup Actions', description: 'Allows running cleanup scans and executing delete actions.' },
    { key: 'view_audit_logs', label: 'Can View Audit Logs', description: 'Allows access to the full audit log history.' },
    { key: 'read_only', label: 'Read-Only Mode', description: 'Restricts user to view-only access; overrides all other permissions.' },
];

const MemberPermissionsModal = ({ isOpen, onClose, member, onSave }) => {
    const [permissions, setPermissions] = useState({});
    const [saving, setSaving] = useState(false);

    useEffect(() => {
        if (member) {
            // Initialize toggles based on existing permissions
            setPermissions(member.team_member_permissions || {});
        }
    }, [member]);

    if (!isOpen || !member) return null;

    const handleToggle = (key) => {
        setPermissions(prev => ({
            ...prev,
            [key]: !prev[key]
        }));
    };

    const handleSave = async () => {
        setSaving(true);
        try {
            await onSave(member.id, permissions);
        } finally {
            setSaving(false);
        }
    };

    return (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
            <div className="bg-white rounded-lg p-6 max-w-lg w-full mx-4 shadow-xl">
                {/* Header */}
                <div className="flex items-center justify-between mb-6">
                    <div className="flex items-center gap-3">
                        <div className="p-2 bg-indigo-100 rounded-lg">
                            <FiShield className="w-6 h-6 text-indigo-600" />
                        </div>
                        <div>
                            <h2 className="text-xl font-bold text-gray-900">Member Permissions</h2>
                            <p className="text-sm text-gray-500">{member.email}</p>
                        </div>
                    </div>
                    <button onClick={onClose} className="p-2 text-gray-400 hover:text-gray-600 rounded-full hover:bg-gray-100">
                        <FiX className="w-5 h-5" />
                    </button>
                </div>

                {/* Permission Toggles */}
                <div className="space-y-4 mb-6">
                    {AVAILABLE_PERMISSIONS.map(perm => (
                        <div key={perm.key} className="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
                            <div>
                                <h4 className="text-sm font-medium text-gray-900">{perm.label}</h4>
                                <p className="text-xs text-gray-500 mt-0.5">{perm.description}</p>
                            </div>
                            <button
                                type="button"
                                onClick={() => handleToggle(perm.key)}
                                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${permissions[perm.key] ? 'bg-indigo-600' : 'bg-gray-300'
                                    }`}
                            >
                                <span
                                    className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${permissions[perm.key] ? 'translate-x-6' : 'translate-x-1'
                                        }`}
                                />
                            </button>
                        </div>
                    ))}
                </div>

                {/* Footer */}
                <div className="flex justify-end gap-3 pt-4 border-t">
                    <Button variant="secondary" onClick={onClose}>
                        Cancel
                    </Button>
                    <Button variant="primary" icon={<FiSave />} onClick={handleSave} disabled={saving}>
                        {saving ? 'Saving...' : 'Save Permissions'}
                    </Button>
                </div>
            </div>
        </div>
    );
};

export default MemberPermissionsModal;
