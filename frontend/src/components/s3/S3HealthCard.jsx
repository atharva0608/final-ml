/**
 * S3 Health Card Component
 * Dashboard widget showing S3 Intelligent-Tiering opportunities
 */
import React, { useState, useEffect } from 'react';
import { FiDatabase, FiAlertTriangle, FiCheckCircle, FiRefreshCw } from 'react-icons/fi';
import { Card, Button } from '../shared';
import { useNavigate } from 'react-router-dom';
import api from '../../services/api';

const S3HealthCard = () => {
    const navigate = useNavigate();
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        fetchS3Overview();
    }, []);

    const fetchS3Overview = async () => {
        try {
            setLoading(true);
            const response = await api.get('/api/v1/s3/overview');
            setData(response.data);
        } catch (error) {
            console.error('Failed to fetch S3 overview:', error);
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

    if (!data || data.total_buckets === 0) {
        return (
            <Card>
                <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-2">
                        <div className="p-2 bg-blue-100 rounded-lg">
                            <FiDatabase className="w-5 h-5 text-blue-600" />
                        </div>
                        <h3 className="font-semibold text-gray-900">S3 Health</h3>
                    </div>
                </div>
                <p className="text-gray-500 text-sm">No S3 buckets analyzed. Connect AWS accounts to detect savings.</p>
            </Card>
        );
    }

    return (
        <Card className="hover:shadow-lg transition-shadow">
            <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                    <div className={`p-2 rounded-lg ${data.buckets_needs_optimization > 0 ? 'bg-yellow-100 text-yellow-600' : 'bg-green-100 text-green-600'}`}>
                        <FiDatabase className="w-5 h-5" />
                    </div>
                    <h3 className="font-semibold text-gray-900">S3 Storage Health</h3>
                </div>
                <button
                    onClick={fetchS3Overview}
                    className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
                >
                    <FiRefreshCw className="w-4 h-4" />
                </button>
            </div>

            <div className="space-y-3">
                {/* Stats Grid */}
                <div className="grid grid-cols-2 gap-3">
                    <div className="bg-gray-50 rounded-lg p-3">
                        <p className="text-xs text-gray-500 uppercase tracking-wide">Total Buckets</p>
                        <p className="text-xl font-bold text-gray-900">{data.total_buckets}</p>
                    </div>
                    <div className={`rounded-lg p-3 ${data.buckets_needs_optimization > 0 ? 'bg-yellow-50' : 'bg-green-50'}`}>
                        <p className="text-xs text-gray-500 uppercase tracking-wide">Optimization Opps</p>
                        <p className={`text-xl font-bold ${data.buckets_needs_optimization > 0 ? 'text-yellow-600' : 'text-green-600'}`}>
                            {data.buckets_needs_optimization}
                        </p>
                    </div>
                </div>

                {/* Savings Potential */}
                {data.total_estimated_savings > 0 && (
                    <div className="bg-green-50 border border-green-100 rounded-lg p-3">
                        <p className="text-xs text-green-600 uppercase tracking-wide font-medium">Potential Monthly Savings</p>
                        <p className="text-2xl font-bold text-green-700">
                            {formatCurrency(data.total_estimated_savings)}
                        </p>
                        <p className="text-xs text-green-600 mt-1 flex items-center gap-1">
                            <FiCheckCircle className="w-3 h-3" />
                            Use Intelligent-Tiering
                        </p>
                    </div>
                )}

                {/* Top Opps */}
                {data.top_opportunities?.length > 0 && (
                    <div className="pt-2 border-t border-gray-100">
                        <p className="text-xs text-gray-500 uppercase tracking-wide mb-2">Top Opportunities</p>
                        <div className="space-y-1">
                            {data.top_opportunities.slice(0, 3).map((opp, index) => (
                                <div key={index} className="flex items-center justify-between text-sm">
                                    <span className="text-gray-700 text-xs truncate max-w-[140px]" title={opp.bucket_name}>
                                        {opp.bucket_name}
                                    </span>
                                    <span className="text-green-600 font-medium whitespace-nowrap">
                                        {formatCurrency(opp.estimated_savings)}/mo
                                    </span>
                                </div>
                            ))}
                        </div>
                    </div>
                )}
            </div>

            {/* Action Buttons */}
            <div className="mt-4 pt-3 border-t border-gray-100 flex gap-2">
                <Button
                    variant="outline"
                    size="sm"
                    className="flex-1"
                    onClick={() => navigate('/s3-analysis')}
                >
                    View Details
                </Button>
                {data.buckets_needs_optimization > 0 && (
                    <Button
                        variant="primary"
                        size="sm"
                        className="flex-1"
                        onClick={() => navigate('/s3-analysis')}
                    >
                        Optimize
                    </Button>
                )}
            </div>
        </Card>
    );
};

export default S3HealthCard;
