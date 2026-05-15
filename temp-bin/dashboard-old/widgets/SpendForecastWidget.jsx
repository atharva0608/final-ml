/**
 * Spend Forecast Widget
 * Shows projected end-of-month spend based on current burn rate
 */
import React, { useState, useEffect } from 'react';
import { FiTrendingUp, FiDollarSign, FiAlertTriangle } from 'react-icons/fi';
import { metricAPI } from '../../../services/api';

const SpendForecastWidget = ({ data: externalData, widgetKey }) => {
    const [internalData, setInternalData] = useState(null);
    const [loading, setLoading] = useState(!externalData);

    useEffect(() => {
        if (externalData) {
            setLoading(false);
            return;
        }

        const fetchData = async () => {
            try {
                // Fetch cost timeseries for current month
                const startOfMonth = new Date();
                startOfMonth.setDate(1);
                startOfMonth.setHours(0, 0, 0, 0);

                const res = await metricAPI.getCostTimeSeries({
                    start_date: startOfMonth.toISOString(),
                    end_date: new Date().toISOString()
                });

                // Calculate forecast
                const data = res.data;
                if (data.data_points && data.data_points.length > 0) {
                    const currentDayOfMonth = new Date().getDate();
                    const daysInMonth = new Date(new Date().getFullYear(), new Date().getMonth() + 1, 0).getDate();

                    // Sum current spend
                    const currentSpend = data.data_points.reduce((sum, point) => sum + (point.value || 0), 0);

                    // Calculate daily burn rate
                    const dailyBurnRate = currentSpend / currentDayOfMonth;

                    // Project to end of month
                    const projectedSpend = dailyBurnRate * daysInMonth;

                    setInternalData({
                        current_spend: currentSpend,
                        projected_spend: projectedSpend,
                        daily_burn_rate: dailyBurnRate,
                        days_remaining: daysInMonth - currentDayOfMonth
                    });
                } else {
                    setInternalData({
                        current_spend: 0,
                        projected_spend: 0,
                        daily_burn_rate: 0,
                        days_remaining: 0
                    });
                }
            } catch (err) {
                console.error('Failed to fetch spend forecast:', err);
                setInternalData({
                    current_spend: 0,
                    projected_spend: 0,
                    daily_burn_rate: 0,
                    days_remaining: 0
                });
            } finally {
                setLoading(false);
            }
        };

        fetchData();
        // Refresh every 5 minutes
        const interval = setInterval(fetchData, 300000);
        return () => clearInterval(interval);
    }, [externalData]);

    if (loading) {
        return (
            <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
                <div className="animate-pulse space-y-3">
                    <div className="h-4 bg-gray-200 rounded w-1/2"></div>
                    <div className="h-8 bg-gray-200 rounded w-3/4"></div>
                    <div className="h-4 bg-gray-200 rounded w-1/3"></div>
                </div>
            </div>
        );
    }

    const forecast = externalData || internalData;
    if (!forecast) return null;

    const currentSpend = forecast.current_spend || 0;
    const projectedSpend = forecast.projected_spend || 0;
    const variance = projectedSpend - currentSpend;
    const variancePct = currentSpend > 0 ? ((variance / currentSpend) * 100) : 0;

    // Determine color based on variance
    const getVarianceColor = () => {
        if (variancePct < 10) return 'text-green-600';
        if (variancePct < 25) return 'text-yellow-600';
        return 'text-red-600';
    };

    const getVarianceBgColor = () => {
        if (variancePct < 10) return 'bg-green-50';
        if (variancePct < 25) return 'bg-yellow-50';
        return 'bg-red-50';
    };

    return (
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 hover:shadow-md transition-shadow">
            <div className="flex items-center justify-between mb-4">
                <div>
                    <h3 className="text-lg font-semibold text-gray-900">Spend Forecast</h3>
                    <p className="text-sm text-gray-500">Projected end-of-month spend</p>
                </div>
                <div className={`p-2 rounded-lg ${getVarianceBgColor()}`}>
                    <FiTrendingUp className={`w-5 h-5 ${getVarianceColor()}`} />
                </div>
            </div>

            <div className="space-y-4">
                {/* Current Spend */}
                <div className="flex items-baseline gap-2">
                    <FiDollarSign className="w-4 h-4 text-gray-400 mt-1" />
                    <div>
                        <p className="text-sm text-gray-500">Current Spend (MTD)</p>
                        <p className="text-2xl font-bold text-gray-900">
                            ${currentSpend.toFixed(2)}
                        </p>
                    </div>
                </div>

                {/* Projected Spend */}
                <div className="flex items-baseline gap-2">
                    <FiTrendingUp className={`w-4 h-4 mt-1 ${getVarianceColor()}`} />
                    <div className="flex-1">
                        <p className="text-sm text-gray-500">Projected Spend (EOM)</p>
                        <p className={`text-2xl font-bold ${getVarianceColor()}`}>
                            ${projectedSpend.toFixed(2)}
                        </p>
                    </div>
                </div>

                {/* Variance Indicator */}
                {variance > 0 && (
                    <div className={`flex items-start gap-2 p-3 rounded-lg ${getVarianceBgColor()}`}>
                        <FiAlertTriangle className={`w-4 h-4 flex-shrink-0 mt-0.5 ${getVarianceColor()}`} />
                        <div className="text-xs">
                            <p className={`font-semibold ${getVarianceColor()}`}>
                                +${variance.toFixed(2)} above current ({variancePct.toFixed(1)}%)
                            </p>
                            <p className="text-gray-600 mt-1">
                                Based on current burn rate of ${(forecast.daily_burn_rate || 0).toFixed(2)}/day
                            </p>
                        </div>
                    </div>
                )}

                {/* Days Remaining */}
                <div className="text-xs text-gray-500 text-center pt-2 border-t border-gray-100">
                    {forecast.days_remaining || 0} days remaining in billing period
                </div>
            </div>
        </div>
    );
};

export default SpendForecastWidget;
