import React, { useState, useEffect } from 'react';
import { api } from '../../services/api';
import { FiShield, FiToggleLeft, FiToggleRight, FiSave, FiCloud, FiServer, FiHardDrive, FiCamera, FiGlobe } from 'react-icons/fi';
import toast from 'react-hot-toast';

/**
 * TeamGovernance - Team-Specific Approval Policies
 * 
 * Allows Team Leads to configure which actions require their approval for team members.
 * This gives granular control over approval workflows at the team level.
 */

const ACTION_TYPES = [
    {
        key: 'CONNECT_ACCOUNT',
        label: 'Connect AWS Account',
        desc: 'Require approval when a member adds a new cloud account.',
        icon: FiCloud,
        color: 'blue'
    },
    {
        key: 'TERMINATE_INSTANCE',
        label: 'Terminate Instance',
        desc: 'Require approval to terminate EC2 instances.',
        icon: FiServer,
        color: 'red'
    },
    {
        key: 'DELETE_VOLUME',
        label: 'Delete Volume',
        desc: 'Require approval to delete EBS volumes.',
        icon: FiHardDrive,
        color: 'yellow'
    },
    {
        key: 'DELETE_SNAPSHOT',
        label: 'Delete Snapshot',
        desc: 'Require approval to delete snapshots.',
        icon: FiCamera,
        color: 'purple'
    },
    {
        key: 'RELEASE_IP',
        label: 'Release Elastic IP',
        desc: 'Require approval to release static IPs.',
        icon: FiGlobe,
        color: 'green'
    },
];

const TeamGovernance = ({ teamId, teamName }) => {
    const [config, setConfig] = useState({});
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);

    useEffect(() => {
        if (teamId) {
            fetchConfig();
        }
    }, [teamId]);

    const fetchConfig = async () => {
        try {
            const res = await api.get(`/api/v1/teams/${teamId}`);
            setConfig(res.data.governance_config || {});
        } catch (err) {
            console.error('Failed to load team governance config', err);
            toast.error('Failed to load team policies');
        } finally {
            setLoading(false);
        }
    };

    const handleToggle = (key) => {
        setConfig(prev => ({
            ...prev,
            [key]: !prev[key]
        }));
    };

    const saveChanges = async () => {
        setSaving(true);
        try {
            await api.put(`/api/v1/teams/${teamId}/governance`, config);
            toast.success('Team policies updated');
        } catch (err) {
            console.error(err);
            toast.error(err.response?.data?.detail || 'Failed to update policies');
        } finally {
            setSaving(false);
        }
    };

    if (loading) {
        return (
            <div className="flex justify-center items-center h-32">
                <div className="animate-spin h-6 w-6 border-4 border-indigo-500 border-t-transparent rounded-full"></div>
            </div>
        );
    }

    return (
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
            {/* Header */}
            <div className="p-4 bg-gradient-to-r from-purple-50 to-indigo-50 border-b border-gray-200">
                <div className="flex justify-between items-center">
                    <div className="flex items-center gap-3">
                        <div className="bg-purple-100 p-2 rounded-full">
                            <FiShield className="text-purple-600 w-5 h-5" />
                        </div>
                        <div>
                            <h2 className="text-lg font-bold text-gray-900">
                                Team Approval Policies
                            </h2>
                            <p className="text-sm text-gray-500">
                                {teamName ? `Configure policies for ${teamName}` : 'Select which actions require your approval'}
                            </p>
                        </div>
                    </div>
                    <button
                        onClick={saveChanges}
                        disabled={saving}
                        className="flex items-center gap-2 bg-indigo-600 text-white px-4 py-2 rounded-md hover:bg-indigo-700 disabled:opacity-50 transition-colors text-sm font-medium"
                    >
                        <FiSave className={saving ? 'animate-spin' : ''} />
                        {saving ? 'Saving...' : 'Save Policies'}
                    </button>
                </div>
            </div>

            {/* Policy Toggles */}
            <div className="divide-y divide-gray-100">
                {ACTION_TYPES.map(action => {
                    const Icon = action.icon;
                    const isEnabled = !!config[action.key];

                    return (
                        <div
                            key={action.key}
                            className={`p-4 flex justify-between items-center hover:bg-gray-50 transition-colors ${isEnabled ? 'bg-green-50/50' : ''}`}
                        >
                            <div className="flex items-center gap-4">
                                <div className={`p-2 rounded-lg bg-${action.color}-100`}>
                                    <Icon className={`text-${action.color}-600 w-5 h-5`} />
                                </div>
                                <div>
                                    <h3 className="font-medium text-gray-900">{action.label}</h3>
                                    <p className="text-sm text-gray-500">{action.desc}</p>
                                </div>
                            </div>
                            <button
                                onClick={() => handleToggle(action.key)}
                                className={`text-3xl transition-colors ${isEnabled ? 'text-green-500' : 'text-gray-300 hover:text-gray-400'}`}
                                title={isEnabled ? 'Approval Required' : 'No Approval Needed'}
                            >
                                {isEnabled ? <FiToggleRight /> : <FiToggleLeft />}
                            </button>
                        </div>
                    );
                })}
            </div>

            {/* Footer Info */}
            <div className="p-4 bg-gray-50 border-t border-gray-200">
                <p className="text-xs text-gray-500 text-center">
                    When enabled, members must request approval before performing these actions.
                    You'll receive notifications in the <strong>Approval Center</strong>.
                </p>
            </div>
        </div>
    );
};

export default TeamGovernance;
