/**
 * Savings KPI Card Widget
 * Displays net savings achieved
 */
import React from 'react';
import { FiTrendingDown, FiArrowUp } from 'react-icons/fi';
import { formatCurrency, formatPercentage } from '../../../utils/formatters';

const SavingsKPICard = ({ data = {}, widgetKey }) => {
    const {
        net_savings = 0,
        savings_percentage = 0,
        label = 'Net Savings'
    } = data;

    return (
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 hover:shadow-md transition-shadow">
            <div className="flex items-center justify-between">
                <div>
                    <p className="text-sm font-medium text-gray-500">{label}</p>
                    <p className="text-3xl font-bold text-emerald-600 mt-1">
                        {formatCurrency(net_savings)}
                    </p>
                </div>
                <div className="p-3 bg-emerald-50 rounded-xl">
                    <FiTrendingDown className="w-6 h-6 text-emerald-600" />
                </div>
            </div>

            <div className="mt-4 flex items-center">
                <div className="flex items-center bg-emerald-50 px-2 py-1 rounded-full">
                    <FiArrowUp className="w-3 h-3 text-emerald-600 mr-1" />
                    <span className="text-sm font-medium text-emerald-700">
                        {formatPercentage(savings_percentage)}
                    </span>
                </div>
                <span className="text-sm text-gray-500 ml-2">savings rate</span>
            </div>
        </div>
    );
};

export default SavingsKPICard;
