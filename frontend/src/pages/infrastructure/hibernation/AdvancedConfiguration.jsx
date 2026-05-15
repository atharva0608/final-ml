import React from 'react';
import { useHibernationStore } from '../../../store/useHibernationStore';
import { Card, Input, Button, Switch } from '../../../components/shared';
import { FiSave, FiAlertTriangle, FiTrash2 } from 'react-icons/fi';

const AdvancedConfiguration = () => {
    const { schedule, updateScheduleLocal, saveSchedule } = useHibernationStore();

    if (!schedule) return null;

    return (
        <div className="space-y-6">
            <Card title="General Settings">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div>
                        <Input
                            label="Timezone"
                            value={schedule.timezone}
                            onChange={(e) => updateScheduleLocal({ timezone: e.target.value })}
                            helpText="All schedule times are based on this timezone"
                        />
                    </div>
                    <div>
                        <Input
                            label="Pre-warm Minutes"
                            type="number"
                            value={schedule.pre_warm_minutes}
                            onChange={(e) => updateScheduleLocal({ pre_warm_minutes: parseInt(e.target.value) || 0 })}
                            min="0"
                            max="60"
                            helpText="Wake cluster before scheduled time to ensure readiness"
                        />
                    </div>
                </div>
            </Card>

            <Card title="Safety & Compliance">
                <div className="space-y-4">
                    <div className="flex items-center justify-between py-3 border-b border-gray-100">
                        <div>
                            <h4 className="font-medium text-gray-900">Block on Active Pipelines</h4>
                            <p className="text-sm text-gray-500">Prevent hibernation if CI/CD jobs are running</p>
                        </div>
                        <Switch checked={true} onChange={() => { }} />
                    </div>
                    <div className="flex items-center justify-between py-3 border-b border-gray-100">
                        <div>
                            <h4 className="font-medium text-gray-900">Respect PDBs</h4>
                            <p className="text-sm text-gray-500">Ensure Pod Disruption Budgets are honored during drain</p>
                        </div>
                        <Switch checked={true} onChange={() => { }} />
                    </div>
                    <div className="flex items-center justify-between py-3">
                        <div>
                            <h4 className="font-medium text-gray-900">Snapshot Retention</h4>
                            <p className="text-sm text-gray-500">Keep snapshots for 7 days after wake</p>
                        </div>
                        <Input type="number" value={7} className="w-20" />
                    </div>
                </div>
            </Card>

            <Card className="border-red-200 bg-red-50">
                <h3 className="text-lg font-semibold text-red-700 mb-2 flex items-center gap-2">
                    <FiAlertTriangle /> Danger Zone
                </h3>
                <p className="text-sm text-red-600 mb-4">
                    Deleting the schedule will stop all automated hibernation. The cluster will remain in its current state.
                </p>
                <Button variant="danger" icon={<FiTrash2 />}>
                    Delete Schedule
                </Button>
            </Card>

            <div className="flex justify-end">
                <Button variant="primary" icon={<FiSave />} onClick={saveSchedule}>
                    Save Configuration
                </Button>
            </div>
        </div>
    );
};

export default AdvancedConfiguration;
