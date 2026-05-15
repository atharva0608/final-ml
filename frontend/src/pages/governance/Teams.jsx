import React, { useState } from 'react';
import { FiUsers, FiShield, FiLayout } from 'react-icons/fi';
import MembersTab from '../../components/teams/MembersTab';
import TeamsTab from '../../components/teams/TeamsTab';
import RolesPoliciesTopTab from '../../components/teams/RolesPoliciesTopTab';

const Tabs = ({ active, onChange }) => (
    <div className="flex bg-gray-100 p-1.5 rounded-xl w-fit mb-8">
        <button
            onClick={() => onChange('structure')}
            className={`px-5 py-2.5 rounded-lg text-sm font-bold flex items-center gap-2 transition-all ${active === 'structure' ? 'bg-white text-blue-600 shadow-sm' : 'text-gray-500 hover:text-gray-700'
                }`}>
            <FiLayout /> Team Structure
        </button>
        <button
            onClick={() => onChange('roles')}
            className={`px-5 py-2.5 rounded-lg text-sm font-bold flex items-center gap-2 transition-all ${active === 'roles' ? 'bg-white text-blue-600 shadow-sm' : 'text-gray-500 hover:text-gray-700'
                }`}>
            <FiShield /> Roles & Policies
        </button>
    </div>
);

const InnerTabs = ({ active, onChange }) => (
    <div className="flex border-b border-gray-200 mb-8 overflow-x-auto">
        <button
            onClick={() => onChange('members')}
            className={`px-6 py-3 text-base font-medium border-b-2 transition-colors whitespace-nowrap ${active === 'members' ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700'
                }`}>
            Members
        </button>
        <button
            onClick={() => onChange('teams')}
            className={`px-6 py-3 text-base font-medium border-b-2 transition-colors whitespace-nowrap ${active === 'teams' ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700'
                }`}>
            Teams
        </button>
    </div>
);

export default function Teams() {
    const [activeTab, setActiveTab] = useState('structure');
    const [structureTab, setStructureTab] = useState('members');

    return (
        <div className="p-6 max-w-7xl mx-auto">
            <div className="mb-6">
                <h1 className="text-2xl font-bold text-gray-900 tracking-tight">Teams & Permissions</h1>
                <p className="text-sm text-gray-500 mt-1">Manage your organization's members, teams, and access controls.</p>
            </div>

            <Tabs active={activeTab} onChange={setActiveTab} />

            {activeTab === 'structure' ? (
                <div className="animate-in fade-in slide-in-from-bottom-2 duration-300">
                    <InnerTabs active={structureTab} onChange={setStructureTab} />

                    {structureTab === 'members' && <MembersTab />}
                    {structureTab === 'teams' && <TeamsTab />}
                </div>
            ) : (
                <div className="animate-in fade-in slide-in-from-bottom-2 duration-300">
                    <RolesPoliciesTopTab />
                </div>
            )}
        </div>
    );
}
