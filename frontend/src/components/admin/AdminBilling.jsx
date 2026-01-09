import React, { useState, useEffect } from 'react';
import { Card, Button } from '../shared';
import { FiDollarSign, FiCreditCard, FiUsers, FiTrendingUp, FiExternalLink } from 'react-icons/fi';

import { adminAPI } from '../../services/api'; // Import adminAPI
import toast from 'react-hot-toast';

const AdminBilling = () => {
    const [billingData, setBillingData] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        fetchBillingData();
    }, []);

    const fetchBillingData = async () => {
        try {
            const response = await adminAPI.getBilling();
            setBillingData(response.data);
        } catch (error) {
            toast.error('Failed to load billing info');
        } finally {
            setLoading(false);
        }
    };

    if (loading) return <div className="p-6">Loading billing data...</div>;
    if (!billingData) return <div className="p-6">No data available</div>;

    const { stats, plans, upsell_opportunities } = billingData;

    return (
        <div className="space-y-6">
            <div className="flex justify-between items-center">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900">Billing & Plans</h1>
                    <p className="text-gray-600">Monetization management and Revenue Ops</p>
                </div>
                <Button variant="outline" icon={<FiExternalLink />} onClick={() => window.open('https://dashboard.stripe.com', '_blank')}>
                    Open Stripe Dashboard
                </Button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                {/* Stats */}
                <Card className="p-6">
                    <div className="flex items-center space-x-3 text-gray-500 mb-2">
                        <FiDollarSign className="w-5 h-5" />
                        <span className="text-sm font-medium">Monthly Recurring Revenue</span>
                    </div>
                    <div className="flex items-baseline space-x-2">
                        <h2 className="text-3xl font-bold text-gray-900">{stats.mrr}</h2>
                        <span className="text-sm text-green-600 flex items-center">
                            <FiTrendingUp className="mr-1" /> {stats.mrr_growth}
                        </span>
                    </div>
                </Card>
                <Card className="p-6">
                    <div className="flex items-center space-x-3 text-gray-500 mb-2">
                        <FiUsers className="w-5 h-5" />
                        <span className="text-sm font-medium">Active Subscriptions</span>
                    </div>
                    <div className="flex items-baseline space-x-2">
                        <h2 className="text-3xl font-bold text-gray-900">{stats.active_subs}</h2>
                        <span className="text-sm text-green-600 flex items-center">
                            <FiTrendingUp className="mr-1" /> {stats.subs_growth}
                        </span>
                    </div>
                </Card>
                <Card className="p-6">
                    <div className="flex items-center space-x-3 text-gray-500 mb-2">
                        <FiCreditCard className="w-5 h-5" />
                        <span className="text-sm font-medium">Failed Charges (Last 24h)</span>
                    </div>
                    <div className="flex items-baseline space-x-2">
                        <h2 className="text-3xl font-bold text-red-600">{stats.failed_charges}</h2>
                        <span className="text-sm text-gray-500">Requires attention</span>
                    </div>
                </Card>
            </div>

            {/* Plan Configuration */}
            <Card className="p-6">
                <div className="flex justify-between items-center mb-6">
                    <h2 className="text-lg font-bold text-gray-900">Plan Configuration</h2>
                    <Button size="sm">Add New Plan</Button>
                </div>

                <div className="overflow-x-auto">
                    <table className="w-full text-left">
                        <thead>
                            <tr className="border-b border-gray-200 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                                <th className="pb-3 text-left">Plan Name</th>
                                <th className="pb-3 text-left">Price (Monthly)</th>
                                <th className="pb-3 text-center">Node Limit</th>
                                <th className="pb-3 text-center">Clients</th>
                                <th className="pb-3 text-right">Actions</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-100">
                            {plans.map((plan, i) => (
                                <tr key={i} className="hover:bg-gray-50 transition-colors">
                                    <td className="py-4 text-sm font-medium text-gray-900">{plan.name}</td>
                                    <td className="py-4 text-sm text-gray-600">{plan.price}</td>
                                    <td className="py-4 text-sm text-center text-gray-600">{plan.nodes}</td>
                                    <td className="py-4 text-sm text-center text-gray-600">{plan.clients}</td>
                                    <td className="py-4 text-right">
                                        <button className="text-blue-600 hover:text-blue-800 text-sm font-medium">Edit</button>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </Card>

            {/* Usage Report / Upsell Opportunities */}
            <Card className="p-6">
                <div className="flex justify-between items-center mb-4">
                    <h2 className="text-lg font-bold text-gray-900">Upsell Opportunities</h2>
                    <p className="text-sm text-gray-500">Clients approaching plan limits</p>
                </div>
                <div className="space-y-4">
                    {upsell_opportunities.map((opp, i) => (
                        <div key={i} className="flex items-center justify-between p-3 bg-yellow-50 border border-yellow-100 rounded-lg">
                            <div className="flex items-center space-x-3">
                                <div className="w-8 h-8 rounded-full bg-yellow-200 text-yellow-800 flex items-center justify-center font-bold text-xs">{opp.client_initial}</div>
                                <div>
                                    <h4 className="font-semibold text-gray-900 text-sm">{opp.client}</h4>
                                    <p className="text-xs text-gray-500">{opp.plan} • {opp.usage} usage</p>
                                </div>
                            </div>
                            <Button size="sm" variant="outline">Contact Sales</Button>
                        </div>
                    ))}
                </div>
            </Card>
        </div>
    );
};

export default AdminBilling;
