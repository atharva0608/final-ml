/**
 * Transfer Analysis Page
 * Detailed Data Transfer analysis and optimization recommendations
 */
import React, { useState, useEffect } from 'react';
import {
    FiGlobe, FiAlertTriangle, FiCheckCircle, FiRefreshCw,
    FiInfo
} from 'react-icons/fi';
import { Card, Button } from '../shared';
import api from '../../services/api';
import toast from 'react-hot-toast';

const TransferAnalysis = () => {
    const [overview, setOverview] = useState(null);
    const [items, setItems] = useState([]);
    const [loading, setLoading] = useState(true);
    const [analyzing, setAnalyzing] = useState(false);

    useEffect(() => {
        fetchData();
    }, []);

    const fetchData = async () => {
        try {
            setLoading(true);
            const response = await api.get('/api/v1/transfer/overview');
            setOverview(response.data);
            setItems(response.data.top_opportunities || []);
        } catch (error) {
            console.error('Failed to load transfer analysis:', error);
            toast.error('Failed to load transfer data');
        } finally {
            setLoading(false);
        }
    };

    const handleAnalyze = async () => {
        try {
            setAnalyzing(true);
            toast.loading('Scanning Data Transfer costs...', { id: 'transfer-analyze' });
            const response = await api.post('/api/v1/transfer/analyze');
            toast.success(`Analyzed ${response.data.items_analyzed} items`, { id: 'transfer-analyze' });
            fetchData();
        } catch (error) {
            toast.error('Analysis failed: ' + (error.response?.data?.detail || error.message), { id: 'transfer-analyze' });
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
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-purple-600"></div>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900">Data Transfer Analysis</h1>
                    <p className="text-gray-500">Optimize network costs and inter-region traffic</p>
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
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <Card className="bg-gradient-to-br from-purple-50 to-white">
                    <div className="flex items-center gap-3">
                        <div className="p-3 bg-purple-100 rounded-xl">
                            <FiGlobe className="w-6 h-6 text-purple-600" />
                        </div>
                        <div>
                            <p className="text-sm text-gray-500">Monthly Transfer Cost</p>
                            <p className="text-2xl font-bold text-gray-900">{formatCurrency(overview?.total_monthly_transfer_cost)}</p>
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

            {/* Opportunities List */}
            <Card>
                <div className="flex items-center justify-between mb-4">
                    <h3 className="text-lg font-semibold text-gray-900">High Cost Transfers</h3>
                </div>

                <div className="overflow-x-auto">
                    <table className="w-full">
                        <thead>
                            <tr className="border-b border-gray-100">
                                <th className="text-left p-4 text-xs font-semibold text-gray-500 uppercase">Transfer Type</th>
                                <th className="text-left p-4 text-xs font-semibold text-gray-500 uppercase">Monthly Cost</th>
                                <th className="text-left p-4 text-xs font-semibold text-gray-500 uppercase">Est. Savings</th>
                                <th className="text-left p-4 text-xs font-semibold text-gray-500 uppercase">Recommendation</th>
                            </tr>
                        </thead>
                        <tbody>
                            {items.length === 0 ? (
                                <tr>
                                    <td colSpan="4" className="p-8 text-center text-gray-500">
                                        <div className="flex flex-col items-center gap-2">
                                            <FiInfo className="w-8 h-8 text-gray-300" />
                                            <p>No high-cost transfer patterns found.</p>
                                        </div>
                                    </td>
                                </tr>
                            ) : (
                                items.map((item) => (
                                    <tr key={item.id} className="border-b border-gray-50 hover:bg-gray-50/50">
                                        <td className="p-4 font-medium text-gray-900">{item.type}</td>
                                        <td className="p-4 text-gray-600">{formatCurrency(item.cost)}</td>
                                        <td className="p-4 font-bold text-green-600">{formatCurrency(item.savings)}</td>
                                        <td className="p-4">
                                            <span className="px-2 py-1 bg-blue-100 text-blue-700 rounded text-xs font-medium">
                                                {item.recommendation?.replace(/_/g, ' ') || 'Monitor'}
                                            </span>
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

export default TransferAnalysis;
