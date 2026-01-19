/**
 * RDS Analysis Page
 * Detailed RDS analysis and Multi-AZ optimization recommendations
 */
import React, { useState, useEffect } from 'react';
import {
    FiServer, FiAlertTriangle, FiCheckCircle, FiRefreshCw,
    FiFilter, FiExternalLink, FiSearch, FiInfo
} from 'react-icons/fi';
import { Card, Button } from '../shared';
import api from '../../services/api';
import toast from 'react-hot-toast';

const RDSAnalysis = () => {
    const [overview, setOverview] = useState(null);
    const [instances, setInstances] = useState([]);
    const [loading, setLoading] = useState(true);
    const [analyzing, setAnalyzing] = useState(false);

    useEffect(() => {
        fetchData();
    }, []);

    const fetchData = async () => {
        try {
            setLoading(true);
            const response = await api.get('/api/v1/rds/overview');
            setOverview(response.data);

            // Note: Currently reusing top_opportunities as the list source.
            // Ideally we need a full list endpoint for pagination.
            setInstances(response.data.top_opportunities || []);

        } catch (error) {
            console.error('Failed to load RDS analysis:', error);
            toast.error('Failed to load RDS data');
        } finally {
            setLoading(false);
        }
    };

    const handleAnalyze = async () => {
        try {
            setAnalyzing(true);
            toast.loading('Scanning RDS instances...', { id: 'rds-analyze' });
            const response = await api.post('/api/v1/rds/analyze');
            toast.success(`Analyzed ${response.data.instances_analyzed} instances`, { id: 'rds-analyze' });
            fetchData();
        } catch (error) {
            toast.error('Analysis failed: ' + (error.response?.data?.detail || error.message), { id: 'rds-analyze' });
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
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600"></div>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900">RDS Database Analysis</h1>
                    <p className="text-gray-500">Multi-AZ optimization for non-production environments</p>
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
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <Card className="bg-gradient-to-br from-indigo-50 to-white">
                    <div className="flex items-center gap-3">
                        <div className="p-3 bg-indigo-100 rounded-xl">
                            <FiServer className="w-6 h-6 text-indigo-600" />
                        </div>
                        <div>
                            <p className="text-sm text-gray-500">Total Instances</p>
                            <p className="text-2xl font-bold text-gray-900">{overview?.total_instances || 0}</p>
                        </div>
                    </div>
                </Card>

                <Card className={`bg-gradient-to-br ${overview?.multi_az_non_prod_count > 0 ? 'from-yellow-50' : 'from-green-50'} to-white`}>
                    <div className="flex items-center gap-3">
                        <div className={`p-3 rounded-xl ${overview?.multi_az_non_prod_count > 0 ? 'bg-yellow-100' : 'bg-green-100'}`}>
                            <FiAlertTriangle className={`w-6 h-6 ${overview?.multi_az_non_prod_count > 0 ? 'text-yellow-600' : 'text-green-600'}`} />
                        </div>
                        <div>
                            <p className="text-sm text-gray-500">Optimization Opps</p>
                            <p className={`text-2xl font-bold ${overview?.multi_az_non_prod_count > 0 ? 'text-yellow-600' : 'text-green-600'}`}>
                                {overview?.multi_az_non_prod_count || 0}
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
            </div>

            {/* Instances List */}
            <Card>
                <div className="flex items-center justify-between mb-4">
                    <h3 className="text-lg font-semibold text-gray-900">Optimization Opportunities</h3>
                    <div className="relative">
                        <FiSearch className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                        <input
                            type="text"
                            placeholder="Search instances..."
                            className="pl-10 pr-4 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                        />
                    </div>
                </div>

                <div className="overflow-x-auto">
                    <table className="w-full">
                        <thead>
                            <tr className="border-b border-gray-100">
                                <th className="text-left p-4 text-xs font-semibold text-gray-500 uppercase">Instance ID</th>
                                <th className="text-left p-4 text-xs font-semibold text-gray-500 uppercase">Engine</th>
                                <th className="text-left p-4 text-xs font-semibold text-gray-500 uppercase">Est. Savings</th>
                                <th className="text-left p-4 text-xs font-semibold text-gray-500 uppercase">Recommendation</th>
                                <th className="text-right p-4 text-xs font-semibold text-gray-500 uppercase">Action</th>
                            </tr>
                        </thead>
                        <tbody>
                            {instances.length === 0 ? (
                                <tr>
                                    <td colSpan="5" className="p-8 text-center text-gray-500">
                                        <div className="flex flex-col items-center gap-2">
                                            <FiInfo className="w-8 h-8 text-gray-300" />
                                            <p>No optimization opportunities found.</p>
                                            <p className="text-sm">Great job! Your RDS instances are optimized.</p>
                                        </div>
                                    </td>
                                </tr>
                            ) : (
                                instances.map((instance) => (
                                    <tr key={instance.id} className="border-b border-gray-50 hover:bg-gray-50/50">
                                        <td className="p-4 font-medium text-gray-900">{instance.identifier}</td>
                                        <td className="p-4 text-gray-600">{instance.engine}</td>
                                        <td className="p-4 font-bold text-green-600">{formatCurrency(instance.savings)}</td>
                                        <td className="p-4">
                                            <span className="px-2 py-1 bg-yellow-100 text-yellow-700 rounded text-xs font-medium">
                                                Convert to Single-AZ
                                            </span>
                                        </td>
                                        <td className="p-4 text-right">
                                            <a
                                                href={`https://console.aws.amazon.com/rds/home#database:id=${instance.identifier};is-cluster=false`}
                                                target="_blank"
                                                rel="noreferrer"
                                                className="text-indigo-600 hover:text-indigo-800 text-sm font-medium inline-flex items-center gap-1"
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

export default RDSAnalysis;
