import React, { useState } from 'react';
import {
    FiServer, FiHardDrive, FiCamera, FiGlobe,
    FiShare2, FiLink, FiDatabase, FiUsers, FiFolder,
    FiTrendingUp, FiArchive, FiActivity, FiChevronDown, FiChevronRight
} from 'react-icons/fi';

const CleanupSidebar = ({ activeTab, onTabChange, scanResult }) => {
    // Logical Groups
    const groups = [
        {
            title: 'Compute',
            items: [
                { type: 'INSTANCE', label: 'Instances', icon: FiServer },
                { type: 'RI_WASTE', label: 'Reserved Instances', icon: FiTrendingUp, isNew: true },
            ]
        },
        {
            title: 'Storage',
            items: [
                { type: 'VOLUME', label: 'EBS Volumes', icon: FiHardDrive },
                { type: 'SNAPSHOT', label: 'Snapshots', icon: FiCamera },
                { type: 'S3_BUCKET', label: 'S3 Buckets', icon: FiFolder },
                { type: 'S3_LIFECYCLE', label: 'S3 Lifecycle', icon: FiArchive, isNew: true },
            ]
        },
        {
            title: 'Databases',
            items: [
                { type: 'RDS_DB', label: 'RDS Instances', icon: FiDatabase },
                { type: 'RDS_MULTIAZ', label: 'Multi-AZ', icon: FiDatabase, isNew: true },
            ]
        },
        {
            title: 'Network',
            items: [
                { type: 'ELASTIC_IP', label: 'Elastic IPs', icon: FiGlobe },
                { type: 'LOAD_BALANCER', label: 'Load Balancers', icon: FiShare2 },
                { type: 'NETWORK_INTERFACE', label: 'Interfaces', icon: FiLink },
                { type: 'DATA_TRANSFER', label: 'Data Transfer', icon: FiActivity, isNew: true },
            ]
        },
        {
            title: 'Identity',
            items: [
                { type: 'IAM_USER', label: 'IAM Users', icon: FiUsers },
            ]
        }
    ];

    const [isCollapsed, setIsCollapsed] = useState(false);

    // State for collapsible groups (all open by default)
    const [openGroups, setOpenGroups] = useState(groups.map(g => g.title));

    const toggleGroup = (title) => {
        setOpenGroups(prev => prev.includes(title)
            ? prev.filter(t => t !== title)
            : [...prev, title]
        );
    };

    return (
        <div className={`transition-all duration-300 flex-shrink-0 bg-white border-r border-gray-200 h-full flex flex-col relative z-20 ${isCollapsed ? 'w-16' : 'w-64'}`}>
            <div className={`flex items-center px-4 py-4 ${isCollapsed ? 'justify-center' : 'justify-between'}`}>
                {!isCollapsed && <h2 className="text-xs font-bold text-gray-400 uppercase tracking-wider">Resources</h2>}
                <button
                    onClick={() => setIsCollapsed(!isCollapsed)}
                    className="p-1 text-gray-400 hover:text-gray-600 rounded hover:bg-gray-100"
                    title={isCollapsed ? "Expand Sidebar" : "Collapse Sidebar"}
                >
                    {isCollapsed ? <FiChevronRight /> : <FiChevronRight className="transform rotate-180" />}
                </button>
            </div>

            <div className="space-y-1 overflow-y-auto flex-1 py-2">
                {groups.map(group => {
                    const isOpen = openGroups.includes(group.title);
                    return (
                        <div key={group.title}>
                            {!isCollapsed && (
                                <button
                                    onClick={() => toggleGroup(group.title)}
                                    className="w-full flex items-center justify-between px-4 py-2 text-xs font-semibold text-gray-500 uppercase hover:text-gray-700 transition-colors"
                                >
                                    {group.title}
                                    {isOpen ? <FiChevronDown /> : <FiChevronRight />}
                                </button>
                            )}

                            {(isOpen || isCollapsed) && (
                                <div className={`${!isCollapsed ? 'mt-1 mb-2 space-y-0.5' : 'space-y-2 px-2'}`}>
                                    {group.items.map(item => {
                                        const isActive = activeTab === item.type;
                                        const count = scanResult?.resources?.filter(r => r.type === item.type && !r.is_authorized).length || 0;

                                        return (
                                            <button
                                                key={item.type}
                                                onClick={() => onTabChange(item.type)}
                                                title={isCollapsed ? item.label : ''}
                                                className={`
                                                    flex items-center transition-all group border-l-2
                                                    ${isCollapsed
                                                        ? 'justify-center w-full aspect-square rounded-lg border-2 border-transparent relative hover:border-gray-200'
                                                        : 'w-full justify-between pl-4 pr-3 py-2.5 text-sm rounded-r-full mr-2'
                                                    }
                                                    ${isActive
                                                        ? (isCollapsed ? 'bg-indigo-50 text-indigo-700 border-indigo-200 shadow-sm' : 'border-l-4 border-indigo-600 bg-indigo-50 text-indigo-800 font-semibold shadow-sm')
                                                        : (isCollapsed ? 'text-gray-500 hover:bg-gray-50' : 'border-l-4 border-transparent text-gray-500 hover:bg-gray-50 hover:text-gray-900')
                                                    }
                                                `}
                                            >
                                                <div className={`flex items-center gap-3 ${isCollapsed ? 'justify-center' : ''}`}>
                                                    <item.icon className={`w-4 h-4 ${isActive ? 'text-blue-600' : 'text-gray-400 group-hover:text-gray-500'}`} />
                                                    {!isCollapsed && <span>{item.label}</span>}
                                                </div>

                                                {/* Badges */}
                                                {!isCollapsed && (
                                                    <div className="flex items-center gap-2">
                                                        {item.isNew && !isActive && (
                                                            <span className="w-1.5 h-1.5 rounded-full bg-purple-500" title="New Feature"></span>
                                                        )}
                                                        {count > 0 && (
                                                            <span className={`text-xs px-1.5 rounded-md ${isActive ? 'bg-blue-200 text-blue-800' : 'bg-gray-100 text-gray-500'}`}>
                                                                {count}
                                                            </span>
                                                        )}
                                                    </div>
                                                )}
                                                {/* Small dot for notification in collapsed mode */}
                                                {isCollapsed && count > 0 && (
                                                    <span className="absolute top-0 right-0 w-2 h-2 rounded-full bg-red-500 block"></span>
                                                )}
                                            </button>
                                        );
                                    })}
                                </div>
                            )}
                        </div>
                    );
                })}
            </div>
        </div>
    );
};

export default CleanupSidebar;
