import React, { useState, useEffect } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useAuthStore } from '../store/useStore';
import TeamManagement from '../components/settings/TeamManagement';
import Roles from './Roles';

const Teams = () => {
    const location = useLocation();
    const navigate = useNavigate();
    const { user } = useAuthStore();

    // Role checks
    const isOrgAdmin = user?.role === 'ORG_ADMIN' || user?.role === 'SUPER_ADMIN' || user?.role === 'CLIENT';
    const isTeamLead = user?.role === 'TEAM_LEAD';
    const isMember = user?.role === 'MEMBER';

    const [activeTab, setActiveTab] = useState('structure');

    // Sync tab state with URL query param for deep linking
    useEffect(() => {
        const params = new URLSearchParams(location.search);
        const tab = params.get('tab');
        if (tab && ['structure', 'roles'].includes(tab)) {
            // Only allow 'roles' tab for admins
            if (tab === 'roles' && !isOrgAdmin) {
                setActiveTab('structure');
            } else {
                setActiveTab(tab);
            }
        }
    }, [location, isOrgAdmin]);

    const handleTabChange = (tab) => {
        // Prevent non-admins from accessing roles tab
        if (tab === 'roles' && !isOrgAdmin) {
            return;
        }
        setActiveTab(tab);
        navigate(`/teams?tab=${tab}`, { replace: true });
    };

    return (
        <div className="space-y-6">
            <div className="flex justify-between items-center">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900">
                        {isOrgAdmin ? 'Organization & Governance' : 'My Team'}
                    </h1>
                    <p className="text-sm text-gray-500 mt-1">
                        {isOrgAdmin
                            ? 'Manage team structure, roles, and governance policies'
                            : 'View team members and structure'
                        }
                    </p>
                </div>
            </div>

            {/* Tabs - Only show Roles & Policies tab to Org Admins */}
            <div className="border-b border-gray-200">
                <nav className="-mb-px flex space-x-8">
                    <button
                        onClick={() => handleTabChange('structure')}
                        className={`${activeTab === 'structure'
                            ? 'border-blue-500 text-blue-600'
                            : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                            } whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm transition-colors`}
                    >
                        {isOrgAdmin ? 'Team Structure' : 'My Team'}
                    </button>

                    {/* Only show Roles & Policies tab for Org Admins */}
                    {isOrgAdmin && (
                        <button
                            onClick={() => handleTabChange('roles')}
                            className={`${activeTab === 'roles'
                                ? 'border-blue-500 text-blue-600'
                                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                                } whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm transition-colors`}
                        >
                            Roles & Policies
                        </button>
                    )}
                </nav>
            </div>

            {/* Tab Content */}
            <div className="mt-6">
                {activeTab === 'structure' ? (
                    <TeamManagement />
                ) : isOrgAdmin ? (
                    <Roles />
                ) : (
                    // Fallback - shouldn't happen due to guards above
                    <TeamManagement />
                )}
            </div>
        </div>
    );
};

export default Teams;
