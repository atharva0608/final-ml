import React, { useState, useEffect } from 'react';
import { decisionEngineAPI } from '../../services/api';
import { FiPieChart, FiAlertTriangle } from 'react-icons/fi';

const DiversityGauge = ({ clusterId }) => {
    const [diversity, setDiversity] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const fetchDiversity = async () => {
            try {
                const response = await decisionEngineAPI.getDiversityStatus(clusterId);
                setDiversity(response.data);
            } catch (err) {
                console.error('Failed to fetch diversity status:', err);
            } finally {
                setLoading(false);
            }
        };

        fetchDiversity();
        const interval = setInterval(fetchDiversity, 30000);
        return () => clearInterval(interval);
    }, [clusterId]);

    if (loading) {
        return (
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 animate-pulse">
                <div className="h-6 bg-gray-200 rounded w-1/3 mb-4"></div>
                <div className="space-y-3">
                    <div className="h-4 bg-gray-200 rounded"></div>
                    <div className="h-4 bg-gray-200 rounded w-5/6"></div>
                </div>
            </div>
        );
    }

    if (!diversity || diversity.total_nodes === 0) {
        return (
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
                <h3 className="text-lg font-semibold text-gray-900 mb-4 flex items-center">
                    <FiPieChart className="mr-2 text-indigo-600" />
                    Diversity Distribution
                </h3>
                <p className="text-sm text-gray-500">No node data available</p>
            </div>
        );
    }

    const familyEntries = Object.entries(diversity.family_percentages || {});
    const azEntries = Object.entries(diversity.az_percentages || {});

    // Check for concentration violations (>40% for family, >50% for AZ)
    const familyViolations = familyEntries.filter(([, pct]) => pct > 0.4);
    const azViolations = azEntries.filter(([, pct]) => pct > 0.5);

    return (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
            <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold text-gray-900 flex items-center">
                    <FiPieChart className="mr-2 text-indigo-600" />
                    Diversity Distribution
                </h3>
                <span className="text-sm text-gray-500">{diversity.total_nodes} nodes</span>
            </div>

            {(familyViolations.length > 0 || azViolations.length > 0) && (
                <div className="mb-4 p-3 bg-orange-50 border border-orange-200 rounded-lg flex items-start">
                    <FiAlertTriangle className="text-orange-600 mt-0.5 mr-2 flex-shrink-0" />
                    <div className="text-sm text-orange-800">
                        <strong>Concentration Alert:</strong> Some families or AZs exceed recommended thresholds
                    </div>
                </div>
            )}

            {/* Family Distribution */}
            <div className="mb-6">
                <h4 className="text-sm font-semibold text-gray-700 mb-3">Instance Family Distribution</h4>
                <div className="space-y-2">
                    {familyEntries.map(([family, percentage]) => {
                        const count = diversity.family_distribution[family];
                        const isViolation = percentage > 0.4;
                        return (
                            <div key={family}>
                                <div className="flex items-center justify-between text-sm mb-1">
                                    <span className={`font-medium ${isViolation ? 'text-orange-700' : 'text-gray-700'}`}>
                                        {family}
                                    </span>
                                    <span className={`${isViolation ? 'text-orange-600 font-semibold' : 'text-gray-600'}`}>
                                        {(percentage * 100).toFixed(1)}% ({count})
                                    </span>
                                </div>
                                <div className="w-full bg-gray-200 rounded-full h-2">
                                    <div
                                        className={`h-2 rounded-full ${isViolation ? 'bg-orange-500' : 'bg-indigo-600'}`}
                                        style={{ width: `${percentage * 100}%` }}
                                    ></div>
                                </div>
                            </div>
                        );
                    })}
                </div>
            </div>

            {/* AZ Distribution */}
            <div>
                <h4 className="text-sm font-semibold text-gray-700 mb-3">Availability Zone Distribution</h4>
                <div className="space-y-2">
                    {azEntries.map(([az, percentage]) => {
                        const count = diversity.az_distribution[az];
                        const isViolation = percentage > 0.5;
                        return (
                            <div key={az}>
                                <div className="flex items-center justify-between text-sm mb-1">
                                    <span className={`font-medium ${isViolation ? 'text-orange-700' : 'text-gray-700'}`}>
                                        {az}
                                    </span>
                                    <span className={`${isViolation ? 'text-orange-600 font-semibold' : 'text-gray-600'}`}>
                                        {(percentage * 100).toFixed(1)}% ({count})
                                    </span>
                                </div>
                                <div className="w-full bg-gray-200 rounded-full h-2">
                                    <div
                                        className={`h-2 rounded-full ${isViolation ? 'bg-orange-500' : 'bg-blue-600'}`}
                                        style={{ width: `${percentage * 100}%` }}
                                    ></div>
                                </div>
                            </div>
                        );
                    })}
                </div>
            </div>

            <div className="mt-4 pt-4 border-t border-gray-200">
                <p className="text-xs text-gray-500">
                    Recommended limits: <strong>Family ≤40%</strong>, <strong>AZ ≤50%</strong>
                </p>
            </div>
        </div>
    );
};

export default DiversityGauge;
