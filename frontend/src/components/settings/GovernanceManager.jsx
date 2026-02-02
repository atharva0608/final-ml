import React, { useState } from 'react';
import { FiArchive, FiTag, FiLayers, FiShield } from 'react-icons/fi';
import CleanupPolicies from '../policies/CleanupPolicies';
import TagPoliciesList from './TagPoliciesList';
import TagTemplateManager from './TagTemplateManager';

/**
 * GovernanceManager
 * 
 * Unified settings center for all governance-related policies:
 * 1. Cleanup Rules (Resource Lifecycle)
 * 2. Tag Policies (Compliance)
 * 3. Tag Templates (Presets)
 */
const GovernanceManager = () => {
    const [activeTab, setActiveTab] = useState('cleanup'); // 'cleanup' | 'tag_policies' | 'tag_templates'

    return (
        <div className="flex flex-col min-h-screen bg-gray-50">
            {/* Header / Tabs */}
            <div className="bg-white border-b border-gray-200 px-6 pt-4">
                <div className="flex space-x-8">
                    <button
                        onClick={() => setActiveTab('cleanup')}
                        className={`pb-4 px-1 flex items-center gap-2 text-sm font-medium border-b-2 transition-colors ${activeTab === 'cleanup'
                                ? 'border-purple-600 text-purple-600'
                                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                            }`}
                    >
                        <FiArchive className="w-4 h-4" />
                        Cleanup Rules
                    </button>
                    <button
                        onClick={() => setActiveTab('tag_policies')}
                        className={`pb-4 px-1 flex items-center gap-2 text-sm font-medium border-b-2 transition-colors ${activeTab === 'tag_policies'
                                ? 'border-red-600 text-red-600'
                                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                            }`}
                    >
                        <FiShield className="w-4 h-4" />
                        Tag Policies
                    </button>
                    <button
                        onClick={() => setActiveTab('tag_templates')}
                        className={`pb-4 px-1 flex items-center gap-2 text-sm font-medium border-b-2 transition-colors ${activeTab === 'tag_templates'
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
                {activeTab === 'cleanup' && (
                    <div className="p-6">
                        <CleanupPolicies />
                    </div>
                )}

                {activeTab === 'tag_policies' && (
                    <TagPoliciesList />
                )}

                {activeTab === 'tag_templates' && (
                    <TagTemplateManager />
                )}
            </div>
        </div>
    );
};

export default GovernanceManager;
