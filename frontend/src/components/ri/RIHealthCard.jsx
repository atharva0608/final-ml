/**
 * RI Health Card Component
 * Dashboard widget showing Reserved Instance utilization overview
 */
import React, { useState, useEffect } from 'react';
import { FiDollarSign, FiAlertTriangle, FiTrendingDown, FiRefreshCw } from 'react-icons/fi';
import { Card, Button } from '../shared';
import { useNavigate } from 'react-router-dom';
import api from '../../services/api';
import toast from 'react-hot-toast';

const RIHealthCard = () => {
    const navigate = useNavigate();
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        fetchRIOverview();
    }, []);

    const fetchRIOverview = async () => {
        try {
            setLoading(true);
            const response = await api.get('/api/v1/ri/overview');
            setData(response.data);
        } catch (error) {
            console.error('Failed to fetch RI overview:', error);
        } finally {
            setLoading(false);
        }
    };

    const getHealthColor = (status) => {
        switch (status) {
            case 'healthy':
                return 'text-green-600 bg-green-100';
            case 'warning':
                return 'text-yellow-600 bg-yellow-100';
            case 'critical':
                return 'text-red-600 bg-red-100';
            default:
                return 'text-gray-600 bg-gray-100';
        }
    };

    const getHealthIcon = (status) => {
        switch (status) {
            case 'healthy':
                return <FiDollarSign className="w-5 h-5" />;
            case 'warning':
                return <FiTrendingDown className="w-5 h-5" />;
            case 'critical':
                return <FiAlertTriangle className="w-5 h-5" />;
            default:
                return <FiDollarSign className="w-5 h-5" />;
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

    if (!data || data.total_ris === 0) {
        return (
            <Card>
                <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-2">
                        <div className="p-2 bg-purple-100 rounded-lg">
                            <FiDollarSign className="w-5 h-5 text-purple-600" />
                        </div>
                        <h3 className="font-semibold text-gray-900">RI Health</h3>
                    </div>
                </div>
                <p className="text-gray-500 text-sm">No Reserved Instances found. Connect AWS accounts to analyze RI utilization.</p>
            </Card>
        );
    }

    return (
        <Card className="hover:shadow-lg transition-shadow">
            <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                    <div className={`p-2 rounded-lg ${getHealthColor(data.health_status)}`}>
                        {getHealthIcon(data.health_status)}
                    </div>
                    <h3 className="font-semibold text-gray-900">Reserved Instance Health</h3>
                </div>
                <button
                    onClick={fetchRIOverview}
                    className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
                >
                    <FiRefreshCw className="w-4 h-4" />
                </button>
            </div>

            <div className="space-y-3">
                {/* Stats Grid */}
                <div className="grid grid-cols-2 gap-3">
                    <div className="bg-gray-50 rounded-lg p-3">
                        <p className="text-xs text-gray-500 uppercase tracking-wide">Total RIs</p>
                        <p className="text-xl font-bold text-gray-900">{data.total_ris}</p>
                    </div>
                    <div className={`rounded-lg p-3 ${data.underutilized_count > 0 ? 'bg-red-50' : 'bg-green-50'}`}>
                        <p className="text-xs text-gray-500 uppercase tracking-wide">Underutilized</p>
                        <p className={`text-xl font-bold ${data.underutilized_count > 0 ? 'text-red-600' : 'text-green-600'}`}>
                            {data.underutilized_count}
                            <span className="text-sm font-normal text-gray-500 ml-1">
                                ({data.underutilized_percentage?.toFixed(0) || 0}%)
                            </span>
                        </p>
                    </div>
                </div>

                {/* Waste Amount */}
                {data.wasted_spend_monthly > 0 && (
                    <div className="bg-red-50 border border-red-100 rounded-lg p-3">
                        <p className="text-xs text-red-600 uppercase tracking-wide font-medium">Wasted Spend/Month</p>
                        <p className="text-2xl font-bold text-red-700">
                            {formatCurrency(data.wasted_spend_monthly)}
                        </p>
                        <p className="text-xs text-red-500">
                            {formatCurrency(data.wasted_spend_annual)} annually
                        </p>
                    </div>
                )}

                {/* Top Opportunities */}
                {data.top_opportunities?.length > 0 && (
                    <div className="pt-2 border-t border-gray-100">
                        <p className="text-xs text-gray-500 uppercase tracking-wide mb-2">Top Opportunities</p>
                        <div className="space-y-1">
                            {data.top_opportunities.slice(0, 3).map((opp, index) => (
                                <div key={index} className="flex items-center justify-between text-sm">
                                    <span className="text-gray-700 font-mono text-xs truncate">
                                        {opp.instance_type}
                                    </span>
                                    <span className="text-red-600 font-medium">
                                        {formatCurrency(opp.monthly_waste)}/mo
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
                    onClick={() => navigate('/ri-analysis')}
                >
                    View Details
                </Button>
                {data.underutilized_count > 0 && (
                    <Button
                        variant="primary"
                        size="sm"
                        className="flex-1"
                        onClick={() => navigate('/ri-analysis?filter=underutilized')}
                    >
                        Fix Now
                    </Button>
                )}
            </div>
        </Card>
    );
};

export default RIHealthCard;
