/**
 * Cost KPI Card Widget
 * Displays monthly cloud spend
 */
import React from 'react';
import { FiDollarSign, FiTrendingUp, FiTrendingDown } from 'react-icons/fi';
import { formatCurrency } from '../../../utils/formatters';

const CostKPICard = ({ data = {}, widgetKey }) => {
    const {
        current_spend = 0,
        previous_spend = 0,
        label = 'Monthly Spend'
    } = data;

    const change = previous_spend > 0
        ? ((current_spend - previous_spend) / previous_spend * 100).toFixed(1)
        : 0;
    const isIncrease = change > 0;

    return (
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 hover:shadow-md transition-shadow">
            <div className="flex items-center justify-between">
                <div>
                    <p className="text-sm font-medium text-gray-500">{label}</p>
                    <p className="text-3xl font-bold text-gray-900 mt-1">
                        {formatCurrency(current_spend)}
                    </p>
                </div>
                <div className="p-3 bg-blue-50 rounded-xl">
                    <FiDollarSign className="w-6 h-6 text-blue-600" />
                </div>
            </div>

            <div className="mt-4 flex items-center">
                {isIncrease ? (
                    <FiTrendingUp className="w-4 h-4 text-red-500 mr-1" />
                ) : (
                    <FiTrendingDown className="w-4 h-4 text-green-500 mr-1" />
                )}
                <span className={`text-sm font-medium ${isIncrease ? 'text-red-600' : 'text-green-600'}`}>
                    {Math.abs(change)}%
                </span>
                <span className="text-sm text-gray-500 ml-1">vs last month</span>
            </div>
        </div>
    );
};

export default CostKPICard;
