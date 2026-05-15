import React from 'react';
import { useHibernationStore } from '../../../store/useHibernationStore';
import { Card } from '../../../components/shared';
import { FiActivity, FiServer, FiLayers, FiAlertCircle, FiCheckCircle, FiClock, FiDollarSign } from 'react-icons/fi';

const ClusterOverview = () => {
    const { metrics, schedule } = useHibernationStore();

    // Determine status color/icon
    const isHibernating = metrics.status === 'hibernating';
    const StatusIcon = isHibernating ? FiClock : FiActivity;
    const statusColor = isHibernating ? 'text-yellow-600' : 'text-green-600';
    const statusBg = isHibernating ? 'bg-yellow-100' : 'bg-green-100';

    return (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
            {/* Card 1: Current Status */}
            <Card className="relative overflow-hidden group">
                <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
                    <StatusIcon className="w-24 h-24 text-gray-500" />
                </div>
                <div className="relative z-10">
                    <div className="flex items-center gap-3 mb-2">
                        <div className={`p-2 rounded-lg ${statusBg}`}>
                            <StatusIcon className={`w-6 h-6 ${statusColor}`} />
                        </div>
                        <h3 className="font-semibold text-gray-700">Cluster Status</h3>
                    </div>
                    <div className="mt-2">
                        <p className={`text-2xl font-bold ${statusColor} capitalize`}>
                            {metrics.status || 'Active'}
                        </p>
                        <p className="text-sm text-gray-500 mt-1">
                            {isHibernating ? 'Wake scheduled: 08:00 AM' : 'Running for 5h 32m'}
                        </p>
                    </div>
                    <div className="mt-4 flex gap-2">
                        <button className="text-xs font-medium text-blue-600 hover:text-blue-800 transition-colors">
                            {isHibernating ? 'Wake Now' : 'Hibernate Now'}
                        </button>
                    </div>
                </div>
            </Card>

            {/* Card 2: Resource Health */}
            <Card>
                <div className="flex items-center gap-3 mb-4">
                    <div className="p-2 bg-blue-50 rounded-lg text-blue-600">
                        <FiServer className="w-6 h-6" />
                    </div>
                    <h3 className="font-semibold text-gray-700">Resource Health</h3>
                </div>
                <div className="space-y-3">
                    <div className="flex justify-between items-center text-sm">
                        <span className="text-gray-600">Nodes</span>
                        <div className="flex items-center gap-2">
                            <div className="w-20 h-2 bg-gray-100 rounded-full overflow-hidden">
                                <div className="h-full bg-green-500 w-full"></div>
                            </div>
                            <span className="font-medium">5/5</span>
                        </div>
                    </div>
                    <div className="flex justify-between items-center text-sm">
                        <span className="text-gray-600">Pods</span>
                        <div className="flex items-center gap-2">
                            <div className="w-20 h-2 bg-gray-100 rounded-full overflow-hidden">
                                <div className="h-full bg-green-500 w-[97%]"></div>
                            </div>
                            <span className="font-medium">97%</span>
                        </div>
                    </div>
                    <div className="flex items-center gap-2 text-xs text-yellow-600 bg-yellow-50 p-2 rounded border border-yellow-100 mt-2">
                        <FiAlertCircle className="w-3 h-3" />
                        <span>2 pods unhealthy (PDB risk)</span>
                    </div>
                </div>
            </Card>

            {/* Card 3: Cost Analysis */}
            <Card className="bg-gradient-to-br from-indigo-50 to-white">
                <div className="flex items-center gap-3 mb-2">
                    <div className="p-2 bg-indigo-100 rounded-lg text-indigo-600">
                        <FiDollarSign className="w-6 h-6" />
                    </div>
                    <h3 className="font-semibold text-gray-700">Cost Rate</h3>
                </div>
                <div className="mt-2">
                    <div className="flex items-baseline gap-1">
                        <span className="text-2xl font-bold text-gray-900">${metrics.hourlyCost.toFixed(2)}</span>
                        <span className="text-sm text-gray-500">/ hour</span>
                    </div>
                    <div className="mt-3 text-sm">
                        <div className="flex justify-between py-1 border-b border-gray-100">
                            <span className="text-gray-500">Projected Monthly</span>
                            <span className="font-medium">${(metrics.hourlyCost * 730).toFixed(0)}</span>
                        </div>
                        <div className="flex justify-between py-1 text-green-700 font-medium">
                            <span>Potential Savings</span>
                            <span>-${metrics.monthlySavings.toFixed(0)} ({metrics.savingsPct}%)</span>
                        </div>
                    </div>
                </div>
            </Card>

            {/* Card 4: Readiness */}
            <Card>
                <div className="flex items-center gap-3 mb-4">
                    <div className="p-2 bg-green-50 rounded-lg text-green-600">
                        <FiCheckCircle className="w-6 h-6" />
                    </div>
                    <h3 className="font-semibold text-gray-700">Readiness</h3>
                </div>
                <div className="space-y-2">
                    <div className="flex items-center gap-2 text-sm text-gray-700">
                        <FiCheckCircle className="text-green-500" />
                        <span>No critical jobs running</span>
                    </div>
                    <div className="flex items-center gap-2 text-sm text-gray-700">
                        <FiCheckCircle className="text-green-500" />
                        <span>All PDBs allow disruption</span>
                    </div>
                    <div className="flex items-center gap-2 text-sm text-gray-700">
                        <FiAlertCircle className="text-yellow-500" />
                        <span>1 active CI/CD pipeline</span>
                    </div>
                    <button className="w-full mt-3 py-1.5 text-xs font-medium text-gray-500 hover:text-gray-700 border border-gray-200 rounded hover:bg-gray-50 transition-colors">
                        View Pre-flight Checks
                    </button>
                </div>
            </Card>
        </div>
    );
};

export default ClusterOverview;
