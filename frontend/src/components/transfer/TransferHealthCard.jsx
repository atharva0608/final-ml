/**
 * Transfer Health Card Component
 * Dashboard widget showing Data Transfer optimization opportunities
 */
import React, { useState, useEffect } from 'react';
import { FiGlobe, FiAlertTriangle, FiCheckCircle, FiRefreshCw, FiArrowRight } from 'react-icons/fi';
import { Card, Button } from '../shared';
import { useNavigate } from 'react-router-dom';
import api from '../../services/api';

const TransferHealthCard = () => {
    const navigate = useNavigate();
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        fetchTransferOverview();
    }, []);

    const fetchTransferOverview = async () => {
        try {
            setLoading(true);
            const response = await api.get('/api/v1/transfer/overview');
            setData(response.data);
        } catch (error) {
            console.error('Failed to fetch transfer overview:', error);
        } finally {
            setLoading(false);
        }
    };

    const formatCurrency = (amount) => {
        return new Intl.NumberFormat('en-US', {
            style: 'currency',
            currency: 'USD',
            minimumFractionDigits: 0,
            maximumFractionDigits: 0
        }).format(amount);
    };

    if (loading) {
        return (
            <Card className="animate-pulse">
                <div className="h-32 bg-gray-200 rounded"></div>
            </Card>
        );
    }

    if (!data || data.total_monthly_transfer_cost === 0) {
        return (
            <Card>
                <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-2">
                        <div className="p-2 bg-purple-100 rounded-lg">
                            <FiGlobe className="w-5 h-5 text-purple-600" />
                        </div>
                        <h3 className="font-semibold text-gray-900">Data Transfer</h3>
                    </div>
                </div>
                <p className="text-gray-500 text-sm">No significant transfer costs detected yet.</p>
            </Card>
        );
    }

    return (
        <Card className="hover:shadow-lg transition-shadow">
            <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                    <div className={`p-2 rounded-lg ${data.total_estimated_savings > 10 ? 'bg-yellow-100 text-yellow-600' : 'bg-green-100 text-green-600'}`}>
                        <FiGlobe className="w-5 h-5" />
                    </div>
                    <h3 className="font-semibold text-gray-900">Data Transfer Health</h3>
                </div>
                <button
                    onClick={fetchTransferOverview}
                    className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
                >
                    <FiRefreshCw className="w-4 h-4" />
                </button>
            </div>

            <div className="space-y-3">
                {/* Stats Grid */}
                <div className="grid grid-cols-2 gap-3">
                    <div className="bg-gray-50 rounded-lg p-3">
                        <p className="text-xs text-gray-500 uppercase tracking-wide">Monthly Cost</p>
                        <p className="text-xl font-bold text-gray-900">{formatCurrency(data.total_monthly_transfer_cost)}</p>
                    </div>
                    <div className={`rounded-lg p-3 ${data.total_estimated_savings > 0 ? 'bg-yellow-50' : 'bg-green-50'}`}>
                        <p className="text-xs text-gray-500 uppercase tracking-wide">Optimization Opps</p>
                        <p className={`text-xl font-bold ${data.total_estimated_savings > 0 ? 'text-yellow-600' : 'text-green-600'}`}>
                            {formatCurrency(data.total_estimated_savings)}
                        </p>
                    </div>
                </div>

                {/* Recommendation Snippet */}
                {data.total_estimated_savings > 0 && (
                    <div className="bg-green-50 border border-green-100 rounded-lg p-3">
                        <p className="text-xs text-green-600 uppercase tracking-wide font-medium">Recommendation</p>
                        <p className="text-sm font-medium text-green-700 mt-1 flex items-center gap-1">
                            <FiCheckCircle className="w-3 h-3" />
                            {data.top_opportunities[0]?.recommendation === 'use_vpc_endpoint' ? 'Use VPC Endpoints' : 'Consolidate AZs'}
                        </p>
                    </div>
                )}
            </div>

            {/* Action Buttons */}
            <div className="mt-4 pt-3 border-t border-gray-100 flex gap-2">
                <Button
                    variant="outline"
                    size="sm"
                    className="flex-1"
                    onClick={() => navigate('/transfer-analysis')}
                >
                    View Details
                </Button>
            </div>
        </Card>
    );
};

export default TransferHealthCard;
