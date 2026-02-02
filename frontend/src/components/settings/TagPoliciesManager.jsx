import React, { useState } from 'react';
import TagPoliciesList from './TagPoliciesList';
import TagTemplateManager from './TagTemplateManager';
import { FiShield, FiLayers } from 'react-icons/fi';

/**
 * TagPoliciesManager (Unified Wrapper)
 * 
 * Consolidates "Governance Policies" and "Tag Templates" into a single view.
 * This resolves the issue of having duplicate sidebar items for related functionality.
 */
const TagPoliciesManager = () => {
    const [activeTab, setActiveTab] = useState('policies');

    return (
        <div className="flex flex-col min-h-screen bg-gray-50">
            {/* Unified Tabs Header */}
            <div className="bg-white border-b border-gray-200 px-6 pt-4">
                <div className="flex space-x-8">
                    <button
                        onClick={() => setActiveTab('policies')}
                        className={`pb-4 px-1 flex items-center gap-2 text-sm font-medium border-b-2 transition-colors ${activeTab === 'policies'
                                ? 'border-red-600 text-red-600'
                                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                            }`}
                    >
                        <FiShield className="w-4 h-4" />
                        Governance Policies
                    </button>
                    <button
                        onClick={() => setActiveTab('templates')}
                        className={`pb-4 px-1 flex items-center gap-2 text-sm font-medium border-b-2 transition-colors ${activeTab === 'templates'
                                ? 'border-blue-600 text-blue-600'
                                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                            }`}
                    >
                        <FiLayers className="w-4 h-4" />
                        Tag Templates
                    </button>
                </div>
            </div>

            {/* Content Area */}
            <div className="flex-1">
                {/* Note: Sub-components handle their own padding (usually p-6) */}
                {activeTab === 'policies' ? (
                    <TagPoliciesList />
                ) : (
                    <TagTemplateManager />
                )}
            </div>
        </div>
    );
};

export default TagPoliciesManager;
