/**
 * RI Analysis Page
 * Full Reserved Instance utilization analysis with recommendations
 */
import React, { useState, useEffect } from 'react';
import {
    FiDollarSign, FiAlertTriangle, FiTrendingDown, FiRefreshCw,
    FiFilter, FiDownload, FiExternalLink, FiChevronRight,
    FiCheckCircle, FiXCircle, FiClock, FiInfo
} from 'react-icons/fi';
import { Card, Button } from '../shared';
import api from '../../services/api';
import toast from 'react-hot-toast';

// Risk Level Badge Component
const RiskBadge = ({ level }) => {
    const styles = {
        healthy: 'bg-green-100 text-green-700 border-green-200',
        warning: 'bg-yellow-100 text-yellow-700 border-yellow-200',
        critical: 'bg-red-100 text-red-700 border-red-200',
        unused: 'bg-gray-100 text-gray-700 border-gray-200'
    };

    const labels = {
        healthy: 'Healthy',
        warning: 'Warning',
        critical: 'Critical',
        unused: 'Unused'
    };

    return (
        <span className={`px-2 py-1 text-xs font-medium rounded-full border ${styles[level] || styles.warning}`}>
            {labels[level] || level}
        </span>
    );
};

// Recommendation Card Component
const RecommendationCard = ({ recommendation, onAction }) => {
    if (!recommendation) return null;

    const priorityColors = {
        critical: 'border-red-300 bg-red-50',
        high: 'border-orange-300 bg-orange-50',
        medium: 'border-yellow-300 bg-yellow-50',
        low: 'border-green-300 bg-green-50'
    };

    return (
        <div className={`border-l-4 rounded-lg p-4 ${priorityColors[recommendation.priority] || 'border-gray-300 bg-gray-50'}`}>
            <div className="flex items-start justify-between">
                <div>
                    <h4 className="font-semibold text-gray-900">{recommendation.title}</h4>
                    <p className="text-sm text-gray-600 mt-1">{recommendation.description}</p>
                </div>
                {recommendation.monthly_impact > 0 && (
                    <div className="text-right">
                        <p className="text-xs text-gray-500">Monthly Impact</p>
                        <p className="text-lg font-bold text-red-600">
                            ${recommendation.monthly_impact.toFixed(0)}
                        </p>
                    </div>
                )}
            </div>

            {recommendation.actions?.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-2">
                    {recommendation.actions.map((action, index) => (
                        <button
                            key={index}
                            onClick={() => onAction(action.action)}
                            className="px-3 py-1.5 text-sm font-medium rounded-lg bg-white border border-gray-200 hover:bg-gray-50 transition-colors"
                        >
                            {action.label}
                        </button>
                    ))}
                </div>
            )}
        </div>
    );
};

// RI Detail Modal Component
const RIDetailModal = ({ ri, onClose, onAction }) => {
    if (!ri) return null;

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
            <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} />
            <div className="relative bg-white rounded-2xl shadow-2xl w-full max-w-2xl mx-4 max-h-[90vh] overflow-y-auto">
                <div className="p-6 border-b border-gray-100">
                    <div className="flex items-center justify-between">
                        <div>
                            <h2 className="text-xl font-bold text-gray-900">Reserved Instance Details</h2>
                            <p className="text-sm text-gray-500 font-mono">{ri.reservation_id}</p>
                        </div>
                        <button
                            onClick={onClose}
                            className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg"
                        >
                            <FiXCircle className="w-5 h-5" />
                        </button>
                    </div>
                </div>

                <div className="p-6 space-y-6">
                    {/* RI Info Grid */}
                    <div className="grid grid-cols-2 gap-4">
                        <div className="bg-gray-50 rounded-lg p-4">
                            <p className="text-xs text-gray-500 uppercase">Instance Type</p>
                            <p className="text-lg font-semibold text-gray-900">{ri.instance_type}</p>
                        </div>
                        <div className="bg-gray-50 rounded-lg p-4">
                            <p className="text-xs text-gray-500 uppercase">Region</p>
                            <p className="text-lg font-semibold text-gray-900">{ri.region}</p>
                        </div>
                        <div className="bg-gray-50 rounded-lg p-4">
                            <p className="text-xs text-gray-500 uppercase">Utilization</p>
                            <p className={`text-lg font-semibold ${ri.utilization_percentage < 70 ? 'text-red-600' : 'text-green-600'}`}>
                                {ri.utilization_percentage?.toFixed(1)}%
                            </p>
                        </div>
                        <div className="bg-gray-50 rounded-lg p-4">
                            <p className="text-xs text-gray-500 uppercase">Monthly Cost</p>
                            <p className="text-lg font-semibold text-gray-900">${ri.monthly_cost?.toFixed(0)}</p>
                        </div>
                    </div>

                    {/* Waste Calculation */}
                    {ri.monthly_waste > 0 && (
                        <div className="bg-red-50 border border-red-100 rounded-lg p-4">
                            <div className="flex items-center gap-2 mb-2">
                                <FiAlertTriangle className="w-5 h-5 text-red-500" />
                                <h4 className="font-semibold text-red-700">Waste Analysis</h4>
                            </div>
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <p className="text-sm text-red-600">Monthly Waste</p>
                                    <p className="text-2xl font-bold text-red-700">${ri.monthly_waste?.toFixed(0)}</p>
                                </div>
                                <div>
                                    <p className="text-sm text-red-600">Annual Projection</p>
                                    <p className="text-2xl font-bold text-red-700">${(ri.monthly_waste * 12)?.toFixed(0)}</p>
                                </div>
                            </div>
                        </div>
                    )}

                    {/* Recommendation */}
                    {ri.recommendation && (
                        <div>
                            <h4 className="font-semibold text-gray-900 mb-3">Recommendation</h4>
                            <RecommendationCard
                                recommendation={ri.recommendation}
                                onAction={(action) => onAction(ri.id, action)}
                            />
                        </div>
                    )}

                    {/* Expiration Info */}
                    {ri.expires_at && (
                        <div className="flex items-center gap-2 text-sm text-gray-600">
                            <FiClock className="w-4 h-4" />
                            <span>Expires: {new Date(ri.expires_at).toLocaleDateString()}</span>
                            {ri.days_remaining > 0 && (
                                <span className="text-gray-400">({ri.days_remaining} days remaining)</span>
                            )}
                        </div>
                    )}
                </div>

                <div className="p-6 border-t border-gray-100 flex justify-end gap-3">
                    <Button variant="outline" onClick={onClose}>Close</Button>
                    <a
                        href="https://console.aws.amazon.com/ec2/home#ReservedInstances"
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-2 px-4 py-2 bg-gray-900 text-white rounded-lg hover:bg-gray-800"
                    >
                        <FiExternalLink className="w-4 h-4" />
                        Open AWS Console
                    </a>
                </div>
            </div>
        </div>
    );
};

// Main RI Analysis Page
const RIAnalysis = () => {
    const [overview, setOverview] = useState(null);
    const [ris, setRIs] = useState([]);
    const [loading, setLoading] = useState(true);
    const [analyzing, setAnalyzing] = useState(false);
    const [selectedRI, setSelectedRI] = useState(null);
    const [filter, setFilter] = useState('all'); // all, underutilized, unused

    useEffect(() => {
        fetchData();
    }, [filter]);

    const fetchData = async () => {
        try {
            setLoading(true);
            const [overviewRes, listRes] = await Promise.all([
                api.get('/api/v1/ri/overview'),
                api.get('/api/v1/ri/list', {
                    params: { underutilized_only: filter === 'underutilized' }
                })
            ]);
            setOverview(overviewRes.data);
            setRIs(listRes.data.ris || []);
        } catch (error) {
            console.error('Failed to fetch RI data:', error);
            toast.error('Failed to load RI analysis');
        } finally {
            setLoading(false);
        }
    };

    const handleAnalyze = async () => {
        try {
            setAnalyzing(true);
            toast.loading('Analyzing Reserved Instances...', { id: 'ri-analyze' });
            await api.post('/api/v1/ri/analyze');
            toast.success('Analysis complete!', { id: 'ri-analyze' });
            fetchData();
        } catch (error) {
            toast.error('Analysis failed: ' + (error.response?.data?.detail || error.message), { id: 'ri-analyze' });
        } finally {
            setAnalyzing(false);
        }
    };

    const handleAction = async (riId, actionType) => {
        try {
            const response = await api.post(`/api/v1/ri/${riId}/action/${actionType}`);
            toast.success(response.data.message);

            // Show next steps
            if (response.data.next_steps?.length > 0) {
                console.log('Next steps:', response.data.next_steps);
            }
        } catch (error) {
            toast.error('Action failed: ' + (error.response?.data?.detail || error.message));
        }
    };

    const formatCurrency = (amount) => {
        return new Intl.NumberFormat('en-US', {
            style: 'currency',
            currency: 'USD',
            minimumFractionDigits: 0
        }).format(amount || 0);
    };

    if (loading && !overview) {
        return (
            <div className="flex items-center justify-center h-96">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            {/* Page Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900">Reserved Instance Analysis</h1>
                    <p className="text-gray-500">Detect waste and optimize your RI portfolio</p>
                </div>
                <div className="flex gap-3">
                    <Button
                        variant="outline"
                        icon={<FiRefreshCw className={analyzing ? 'animate-spin' : ''} />}
                        onClick={handleAnalyze}
                        disabled={analyzing}
                    >
                        {analyzing ? 'Analyzing...' : 'Run Analysis'}
                    </Button>
                    <Button
                        variant="outline"
                        icon={<FiDownload />}
                    >
                        Export
                    </Button>
                </div>
            </div>

            {/* Overview Cards */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <Card className="bg-gradient-to-br from-blue-50 to-white">
                    <div className="flex items-center gap-3">
                        <div className="p-3 bg-blue-100 rounded-xl">
                            <FiDollarSign className="w-6 h-6 text-blue-600" />
                        </div>
                        <div>
                            <p className="text-sm text-gray-500">Total RIs</p>
                            <p className="text-2xl font-bold text-gray-900">{overview?.total_ris || 0}</p>
                        </div>
                    </div>
                </Card>

                <Card className={`bg-gradient-to-br ${overview?.underutilized_count > 0 ? 'from-red-50' : 'from-green-50'} to-white`}>
                    <div className="flex items-center gap-3">
                        <div className={`p-3 rounded-xl ${overview?.underutilized_count > 0 ? 'bg-red-100' : 'bg-green-100'}`}>
                            <FiTrendingDown className={`w-6 h-6 ${overview?.underutilized_count > 0 ? 'text-red-600' : 'text-green-600'}`} />
                        </div>
                        <div>
                            <p className="text-sm text-gray-500">Underutilized</p>
                            <p className={`text-2xl font-bold ${overview?.underutilized_count > 0 ? 'text-red-600' : 'text-green-600'}`}>
                                {overview?.underutilized_count || 0}
                            </p>
                        </div>
                    </div>
                </Card>

                <Card className="bg-gradient-to-br from-red-50 to-white">
                    <div className="flex items-center gap-3">
                        <div className="p-3 bg-red-100 rounded-xl">
                            <FiAlertTriangle className="w-6 h-6 text-red-600" />
                        </div>
                        <div>
                            <p className="text-sm text-gray-500">Monthly Waste</p>
                            <p className="text-2xl font-bold text-red-600">
                                {formatCurrency(overview?.wasted_spend_monthly)}
                            </p>
                        </div>
                    </div>
                </Card>

                <Card className="bg-gradient-to-br from-purple-50 to-white">
                    <div className="flex items-center gap-3">
                        <div className="p-3 bg-purple-100 rounded-xl">
                            <FiCheckCircle className="w-6 h-6 text-purple-600" />
                        </div>
                        <div>
                            <p className="text-sm text-gray-500">Annual Impact</p>
                            <p className="text-2xl font-bold text-purple-600">
                                {formatCurrency(overview?.wasted_spend_annual)}
                            </p>
                        </div>
                    </div>
                </Card>
            </div>

            {/* Filter Tabs */}
            <div className="flex items-center gap-4 border-b border-gray-200">
                <button
                    onClick={() => setFilter('all')}
                    className={`pb-3 px-1 text-sm font-medium border-b-2 transition-colors ${filter === 'all' ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700'
                        }`}
                >
                    All RIs ({overview?.total_ris || 0})
                </button>
                <button
                    onClick={() => setFilter('underutilized')}
                    className={`pb-3 px-1 text-sm font-medium border-b-2 transition-colors ${filter === 'underutilized' ? 'border-red-600 text-red-600' : 'border-transparent text-gray-500 hover:text-gray-700'
                        }`}
                >
                    Underutilized ({overview?.underutilized_count || 0})
                </button>
            </div>

            {/* RI Table */}
            <Card>
                <div className="overflow-x-auto">
                    <table className="w-full">
                        <thead>
                            <tr className="border-b border-gray-100">
                                <th className="text-left p-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">Instance</th>
                                <th className="text-left p-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">Region</th>
                                <th className="text-left p-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">Utilization</th>
                                <th className="text-left p-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">Monthly Cost</th>
                                <th className="text-left p-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">Waste</th>
                                <th className="text-left p-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">Risk</th>
                                <th className="text-left p-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">Action</th>
                            </tr>
                        </thead>
                        <tbody>
                            {ris.length === 0 ? (
                                <tr>
                                    <td colSpan="7" className="p-8 text-center text-gray-500">
                                        <div className="flex flex-col items-center gap-2">
                                            <FiInfo className="w-8 h-8 text-gray-300" />
                                            <p>No Reserved Instances found</p>
                                            <p className="text-sm">Run analysis to fetch RI data from your AWS accounts</p>
                                        </div>
                                    </td>
                                </tr>
                            ) : (
                                ris.map((ri) => (
                                    <tr key={ri.id} className="border-b border-gray-50 hover:bg-gray-50/50 transition-colors">
                                        <td className="p-4">
                                            <div>
                                                <p className="font-medium text-gray-900">{ri.instance_type}</p>
                                                <p className="text-xs text-gray-500 font-mono">{ri.reservation_id?.substring(0, 12)}...</p>
                                            </div>
                                        </td>
                                        <td className="p-4 text-gray-600">{ri.region}</td>
                                        <td className="p-4">
                                            <div className="flex items-center gap-2">
                                                <div className="flex-1 h-2 bg-gray-200 rounded-full max-w-20">
                                                    <div
                                                        className={`h-2 rounded-full ${ri.utilization_percentage < 70 ? 'bg-red-500' : 'bg-green-500'}`}
                                                        style={{ width: `${Math.min(100, ri.utilization_percentage)}%` }}
                                                    />
                                                </div>
                                                <span className={`text-sm font-medium ${ri.utilization_percentage < 70 ? 'text-red-600' : 'text-green-600'}`}>
                                                    {ri.utilization_percentage?.toFixed(0)}%
                                                </span>
                                            </div>
                                        </td>
                                        <td className="p-4 text-gray-900 font-medium">
                                            {formatCurrency(ri.monthly_cost)}
                                        </td>
                                        <td className="p-4">
                                            {ri.monthly_waste > 0 ? (
                                                <span className="text-red-600 font-medium">{formatCurrency(ri.monthly_waste)}</span>
                                            ) : (
                                                <span className="text-green-600">—</span>
                                            )}
                                        </td>
                                        <td className="p-4">
                                            <RiskBadge level={ri.risk_level} />
                                        </td>
                                        <td className="p-4">
                                            <button
                                                onClick={() => setSelectedRI(ri)}
                                                className="flex items-center gap-1 text-blue-600 hover:text-blue-700 text-sm font-medium"
                                            >
                                                View <FiChevronRight className="w-4 h-4" />
                                            </button>
                                        </td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>
            </Card>

            {/* RI Detail Modal */}
            {selectedRI && (
                <RIDetailModal
                    ri={selectedRI}
                    onClose={() => setSelectedRI(null)}
                    onAction={handleAction}
                />
            )}
        </div>
    );
};

export default RIAnalysis;
