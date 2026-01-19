/**
 * S3 Analysis Page
 * Detailed S3 storage analysis and intelligent tiering recommendations
 */
import React, { useState, useEffect } from 'react';
import {
    FiDatabase, FiAlertTriangle, FiCheckCircle, FiRefreshCw,
    FiFilter, FiDownload, FiExternalLink, FiChevronRight,
    FiInfo, FiSearch
} from 'react-icons/fi';
import { Card, Button } from '../shared';
import api from '../../services/api';
import toast from 'react-hot-toast';

// Storage Class Badge
const StorageBadge = ({ type, percentage }) => {
    const colors = {
        Standard: 'bg-red-100 text-red-700',
        'Standard-IA': 'bg-yellow-100 text-yellow-700',
        Glacier: 'bg-blue-100 text-blue-700',
        'Intelligent-Tiering': 'bg-green-100 text-green-700'
    };

    return (
        <span className={`px-2 py-1 text-xs font-medium rounded-full ${colors[type] || 'bg-gray-100 text-gray-700'}`}>
            {type}: {percentage}%
        </span>
    );
};

const S3Analysis = () => {
    const [overview, setOverview] = useState(null);
    const [buckets, setBuckets] = useState([]); // This would come from detailed list endpoint if separated
    const [loading, setLoading] = useState(true);
    const [analyzing, setAnalyzing] = useState(false);

    // Note: Since overview endpoint returns everything for now (simplified service), 
    // we use it for both overview and list. In prod, list should be paginated.

    useEffect(() => {
        fetchData();
    }, []);

    const fetchData = async () => {
        try {
            setLoading(true);
            const response = await api.get('/api/v1/s3/overview');
            setOverview(response.data);

            // For now, overview endpoint returns summary. 
            // We need a list endpoint. Actually, I only implemented overview in backend service.
            // Let me update backend to return list too, or add list endpoint.
            // Wait, analyze_all_buckets returns details. 
            // So on first load if we have data ensuring we rely on 'overview' endpoint to return list is better?
            // "get_overview" in service only returns aggregation + top opps.
            // I should have implemented a list endpoint.

            // IMPORTANT: I missed creating a list endpoint in backend. 
            // I'll fix this in the next step. For now, I'll mock the list or just use top opportunities.

            // Actually, I can use top opportunities to show SOMETHING.
            setBuckets(response.data.top_opportunities || []);

        } catch (error) {
            console.error('Failed to load S3 analysis:', error);
            toast.error('Failed to load S3 data');
        } finally {
            setLoading(false);
        }
    };

    const handleAnalyze = async () => {
        try {
            setAnalyzing(true);
            toast.loading('Scanning S3 buckets...', { id: 's3-analyze' });
            const response = await api.post('/api/v1/s3/analyze');
            toast.success(`Analyzed ${response.data.buckets_analyzed} buckets`, { id: 's3-analyze' });

            // The analyze response contains full details!
            if (response.data.details) {
                // But wait, analyze is POST. We shouldn't rely on it for view.
                // I need to add that GET endpoint.
                // For now, reload overview.
                fetchData();
            }
        } catch (error) {
            toast.error('Analysis failed: ' + (error.response?.data?.detail || error.message), { id: 's3-analyze' });
        } finally {
            setAnalyzing(false);
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
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900">S3 Storage Analysis</h1>
                    <p className="text-gray-500">Intelligent Tiering audit and lifecycle optimization</p>
                </div>
                <div className="flex gap-3">
                    <Button
                        variant="outline"
                        icon={<FiRefreshCw className={analyzing ? 'animate-spin' : ''} />}
                        onClick={handleAnalyze}
                        disabled={analyzing}
                    >
                        {analyzing ? 'Scanning...' : 'Run Scan'}
                    </Button>
                </div>
            </div>

            {/* Overview Cards */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <Card className="bg-gradient-to-br from-blue-50 to-white">
                    <div className="flex items-center gap-3">
                        <div className="p-3 bg-blue-100 rounded-xl">
                            <FiDatabase className="w-6 h-6 text-blue-600" />
                        </div>
                        <div>
                            <p className="text-sm text-gray-500">Total Buckets</p>
                            <p className="text-2xl font-bold text-gray-900">{overview?.total_buckets || 0}</p>
                        </div>
                    </div>
                </Card>

                <Card className={`bg-gradient-to-br ${overview?.buckets_needs_optimization > 0 ? 'from-yellow-50' : 'from-green-50'} to-white`}>
                    <div className="flex items-center gap-3">
                        <div className={`p-3 rounded-xl ${overview?.buckets_needs_optimization > 0 ? 'bg-yellow-100' : 'bg-green-100'}`}>
                            <FiAlertTriangle className={`w-6 h-6 ${overview?.buckets_needs_optimization > 0 ? 'text-yellow-600' : 'text-green-600'}`} />
                        </div>
                        <div>
                            <p className="text-sm text-gray-500">Opportunities</p>
                            <p className={`text-2xl font-bold ${overview?.buckets_needs_optimization > 0 ? 'text-yellow-600' : 'text-green-600'}`}>
                                {overview?.buckets_needs_optimization || 0}
                            </p>
                        </div>
                    </div>
                </Card>

                <Card className="bg-gradient-to-br from-green-50 to-white">
                    <div className="flex items-center gap-3">
                        <div className="p-3 bg-green-100 rounded-xl">
                            <FiCheckCircle className="w-6 h-6 text-green-600" />
                        </div>
                        <div>
                            <p className="text-sm text-gray-500">Potential Savings</p>
                            <p className="text-2xl font-bold text-green-600">
                                {formatCurrency(overview?.total_estimated_savings)}
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
                            <p className="text-sm text-gray-500">No Lifecycle</p>
                            <p className="text-2xl font-bold text-red-600">
                                {overview?.buckets_no_lifecycle || 0}
                            </p>
                        </div>
                    </div>
                </Card>
            </div>

            {/* Buckets List */}
            <Card>
                <div className="flex items-center justify-between mb-4">
                    <h3 className="text-lg font-semibold text-gray-900">Optimization Opportunities</h3>
                    <div className="relative">
                        <FiSearch className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                        <input
                            type="text"
                            placeholder="Search buckets..."
                            className="pl-10 pr-4 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                        />
                    </div>
                </div>

                <div className="overflow-x-auto">
                    <table className="w-full">
                        <thead>
                            <tr className="border-b border-gray-100">
                                <th className="text-left p-4 text-xs font-semibold text-gray-500 uppercase">Bucket Name</th>
                                <th className="text-left p-4 text-xs font-semibold text-gray-500 uppercase">Current Cost</th>
                                <th className="text-left p-4 text-xs font-semibold text-gray-500 uppercase">Est. Savings</th>
                                <th className="text-left p-4 text-xs font-semibold text-gray-500 uppercase">Recommendation</th>
                                <th className="text-right p-4 text-xs font-semibold text-gray-500 uppercase">Action</th>
                            </tr>
                        </thead>
                        <tbody>
                            {buckets.length === 0 ? (
                                <tr>
                                    <td colSpan="5" className="p-8 text-center text-gray-500">
                                        <div className="flex flex-col items-center gap-2">
                                            <FiInfo className="w-8 h-8 text-gray-300" />
                                            <p>No optimization opportunities found.</p>
                                            <p className="text-sm">Run a scan or check if your buckets are already optimized.</p>
                                        </div>
                                    </td>
                                </tr>
                            ) : (
                                buckets.map((bucket) => (
                                    <tr key={bucket.id} className="border-b border-gray-50 hover:bg-gray-50/50">
                                        <td className="p-4 font-medium text-gray-900">{bucket.bucket_name}</td>
                                        <td className="p-4 text-gray-600">{formatCurrency(bucket.monthly_cost)}</td>
                                        <td className="p-4 font-bold text-green-600">{formatCurrency(bucket.estimated_savings)}</td>
                                        <td className="p-4">
                                            <span className="px-2 py-1 bg-blue-100 text-blue-700 rounded text-xs font-medium">
                                                {bucket.recommendation?.replace(/_/g, ' ') || 'Optimize'}
                                            </span>
                                        </td>
                                        <td className="p-4 text-right">
                                            <a
                                                href={`https://s3.console.aws.amazon.com/s3/buckets/${bucket.bucket_name}?tab=management`}
                                                target="_blank"
                                                rel="noreferrer"
                                                className="text-blue-600 hover:text-blue-800 text-sm font-medium inline-flex items-center gap-1"
                                            >
                                                Configure <FiExternalLink className="w-3 h-3" />
                                            </a>
                                        </td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>
            </Card>
        </div>
    );
};

export default S3Analysis;
