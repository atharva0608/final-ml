import React, { useState, useEffect } from 'react';
import { teamAPI } from '../../services/api';
import { Card, Switch, Button, Badge } from '../shared';
import toast from 'react-hot-toast';
import { FiAlertCircle, FiCheck, FiShield } from 'react-icons/fi';

const ACTION_TYPES = [
    { key: 'CONNECT_ACCOUNT', label: 'Connect AWS Account', desc: 'Require approval when a member adds a new cloud account.' },
    { key: 'TERMINATE_INSTANCE', label: 'Terminate Instance', desc: 'Require approval to delete EC2 instances.' },
    { key: 'DELETE_VOLUME', label: 'Delete Volume', desc: 'Require approval to delete EBS volumes.' },
    { key: 'DELETE_SNAPSHOT', label: 'Delete Snapshot', desc: 'Require approval to delete snapshots.' },
    { key: 'RELEASE_IP', label: 'Release Elastic IP', desc: 'Require approval to release static IPs.' },
];

const TeamGovernance = ({ teamId }) => {
    const [config, setConfig] = useState({});
    const [loading, setLoading] = useState(false);
    const [fetching, setFetching] = useState(true);

    useEffect(() => {
        fetchConfig();
    }, [teamId]);

    const fetchConfig = async () => {
        try {
            setFetching(true);
            const res = await teamAPI.get(teamId);
            setConfig(res.data.governance_config || {});
        } catch (err) {
            console.error(err);
            toast.error("Failed to load policies");
        } finally {
            setFetching(false);
        }
    };

    const handleToggle = (key) => {
        setConfig(prev => ({
            ...prev,
            [key]: !prev[key]
        }));
    };

    const saveChanges = async () => {
        setLoading(true);
        try {
            await teamAPI.updateGovernance(teamId, config);
            toast.success("Team policies updated successfully");
        } catch (err) {
            console.error(err);
            toast.error("Failed to update policies");
        } finally {
            setLoading(false);
        }
    };

    return (
        <Card className="p-6 border-l-4 border-l-blue-500">
            <div className="flex justify-between items-center mb-6">
                <div>
                    <div className="flex items-center gap-2">
                        <FiShield className="text-blue-600 w-5 h-5" />
                        <h2 className="text-xl font-bold text-gray-900">Team Approval Policies</h2>
                    </div>
                    <p className="text-gray-500 text-sm mt-1">Configure which actions require Team Lead approval.</p>
                </div>
                <Button onClick={saveChanges} loading={loading} variant="primary">Save Changes</Button>
            </div>

            <div className="space-y-4">
                {ACTION_TYPES.map(action => {
                    const isEnabled = !!config[action.key];
                    return (
                        <div key={action.key} className={`flex justify-between items-center p-4 rounded-lg border ${isEnabled ? 'bg-blue-50 border-blue-100' : 'bg-white border-gray-100'}`}>
                            <div>
                                <div className="flex items-center gap-2">
                                    <h3 className="font-semibold text-gray-900">{action.label}</h3>
                                    {isEnabled && <Badge color="blue" size="sm">Approval Required</Badge>}
                                </div>
                                <p className="text-sm text-gray-500 mt-1">{action.desc}</p>
                            </div>
                            <div className="flex items-center gap-3">
                                <span className={`text-sm font-medium ${isEnabled ? 'text-blue-700' : 'text-gray-400'}`}>
                                    {isEnabled ? 'Restricted' : 'Allowed'}
                                </span>
                                <Switch
                                    checked={isEnabled}
                                    onChange={() => handleToggle(action.key)}
                                />
                            </div>
                        </div>
                    );
                })}
            </div>

            <div className="mt-6 flex items-start gap-3 bg-yellow-50 p-4 rounded-md text-sm text-yellow-800">
                <FiAlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
                <p>
                    Enabling approval means members of this team cannot perform the action directly.
                    Their request will be queued in the <strong>Approvals</strong> dashboard for your review.
                </p>
            </div>
        </Card>
    );
};

export default TeamGovernance;
