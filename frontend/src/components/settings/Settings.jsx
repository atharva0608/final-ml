/**
 * Unified Settings Page
 * Tabbed interface for Account, Integrations, and Billing
 */
import React, { useState } from 'react';
import { FiUser, FiCloud, FiCreditCard } from 'react-icons/fi';
import AccountSettings from './AccountSettings';
import CloudIntegrations from './CloudIntegrations';
import { Card, Button } from '../shared';
import toast from 'react-hot-toast';
import { useAuth } from '../../hooks/useAuth';

const Settings = () => {
    const [activeTab, setActiveTab] = useState('account');
    const { user } = useAuth();

    const tabs = [
        { id: 'account', label: 'Account', icon: FiUser },
        { id: 'integrations', label: 'Cloud Integrations', icon: FiCloud },
        { id: 'billing', label: 'Billing', icon: FiCreditCard },
    ];

    const renderTabContent = () => {
        switch (activeTab) {
            case 'account':
                return <AccountSettings />;
            case 'integrations':
                return <CloudIntegrations />;
            case 'billing':
                return <BillingTab />;
            default:
                return <AccountSettings />;
        }
    };

    return (
        <div className="min-h-screen">
            {/* Header */}
            <div className="mb-6">
                <h1 className="text-3xl font-bold text-gray-900">Settings</h1>
                <p className="text-gray-600 mt-1">Manage your account, integrations, and preferences</p>
            </div>

            {/* Tabs */}
            <div className="border-b border-gray-200 mb-6">
                <nav className="-mb-px flex space-x-8">
                    {tabs.map(tab => (
                        <button
                            key={tab.id}
                            onClick={() => setActiveTab(tab.id)}
                            className={`flex items-center gap-2 py-4 px-1 border-b-2 font-medium text-sm transition-colors ${activeTab === tab.id
                                ? 'border-blue-500 text-blue-600'
                                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                                }`}
                        >
                            <tab.icon className="w-5 h-5" />
                            {tab.label}
                        </button>
                    ))}
                </nav>
            </div>

            {/* Tab Content */}
            <div>{renderTabContent()}</div>
        </div>
    );
};

// Billing Tab Component
const BillingTab = () => {
    const billingInfo = {
        plan: 'Professional',
        billing_cycle: 'Monthly',
        next_billing: 'Feb 1, 2026',
        amount: 299.00,
        payment_method: '**** **** **** 4242',
    };

    const usageStats = [
        { label: 'Clusters Managed', value: 5, limit: 10 },
        { label: 'Nodes Optimized', value: 47, limit: 100 },
        { label: 'API Requests', value: 12450, limit: 50000 },
    ];

    return (
        <div className="space-y-6">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Current Plan */}
                <Card>
                    <h3 className="text-lg font-semibold text-gray-900 mb-4">Current Plan</h3>
                    <div className="p-4 bg-gradient-to-br from-blue-50 to-white rounded-lg border border-blue-100">
                        <div className="flex justify-between items-start">
                            <div>
                                <p className="text-2xl font-bold text-gray-900">{billingInfo.plan}</p>
                                <p className="text-sm text-gray-600">{billingInfo.billing_cycle} billing</p>
                            </div>
                            <div className="text-right">
                                <p className="text-2xl font-bold text-blue-600">${billingInfo.amount}</p>
                                <p className="text-sm text-gray-500">per month</p>
                            </div>
                        </div>
                        <div className="mt-4 pt-4 border-t border-blue-100 text-sm text-gray-600">
                            Next billing date: <span className="font-medium">{billingInfo.next_billing}</span>
                        </div>
                    </div>
                    <div className="mt-4 flex gap-2">
                        <Button variant="outline" size="sm">Change Plan</Button>
                        <Button variant="outline" size="sm">Cancel Subscription</Button>
                    </div>
                </Card>

                {/* Payment Method */}
                <Card>
                    <h3 className="text-lg font-semibold text-gray-900 mb-4">Payment Method</h3>
                    <div className="flex items-center gap-4 p-4 bg-gray-50 rounded-lg">
                        <div className="w-12 h-8 bg-gradient-to-r from-blue-600 to-blue-800 rounded flex items-center justify-center text-white text-xs font-bold">
                            VISA
                        </div>
                        <div>
                            <p className="font-medium text-gray-900">{billingInfo.payment_method}</p>
                            <p className="text-sm text-gray-500">Expires 12/28</p>
                        </div>
                    </div>
                    <Button variant="outline" size="sm" className="mt-4">Update Payment Method</Button>
                </Card>
            </div>

            {/* Usage */}
            <Card>
                <h3 className="text-lg font-semibold text-gray-900 mb-4">Current Usage</h3>
                <div className="space-y-4">
                    {usageStats.map(stat => (
                        <div key={stat.label}>
                            <div className="flex justify-between text-sm mb-1">
                                <span className="text-gray-700">{stat.label}</span>
                                <span className="font-medium text-gray-900">{stat.value.toLocaleString()} / {stat.limit.toLocaleString()}</span>
                            </div>
                            <div className="w-full bg-gray-200 rounded-full h-2">
                                <div
                                    className="bg-blue-600 h-2 rounded-full transition-all"
                                    style={{ width: `${(stat.value / stat.limit) * 100}%` }}
                                />
                            </div>
                        </div>
                    ))}
                </div>
            </Card>
        </div>
    );
};

export default Settings;
