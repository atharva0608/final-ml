/**
 * Role-based default dashboard layouts
 * These are used when a user has no saved preferences
 */

export const ROLE_DEFAULTS = {
    SUPER_ADMIN: ['platform_health', 'tenant_list', 'global_audit', 'revenue_chart'],
    ORG_ADMIN: ['cost_kpi', 'savings_kpi', 'spend_forecast', 'agent_status', 'ri_health', 's3_health', 'rds_health', 'transfer_health', 'savings_chart', 'fleet_composition', 'activity_feed'],
    CLIENT: ['cost_kpi', 'savings_kpi', 'spend_forecast', 'agent_status', 'ri_health', 's3_health', 'rds_health', 'transfer_health', 'savings_chart', 'fleet_composition', 'activity_feed'],
    TEAM_LEAD: ['team_budget', 'pending_approvals', 'spend_forecast', 'cost_kpi', 'ri_health', 'rds_health', 'savings_kpi', 'activity_feed'],
    MEMBER: ['cost_kpi', 'savings_kpi', 'my_tickets', 'activity_feed']
};

/**
 * Widget metadata for customization UI
 */
export const WIDGET_METADATA = {
    // Super Admin widgets
    platform_health: {
        name: 'Platform Health',
        description: 'System status and performance metrics',
        roles: ['SUPER_ADMIN'],
        icon: 'FiActivity'
    },
    tenant_list: {
        name: 'Tenant Overview',
        description: 'List of all organizations',
        roles: ['SUPER_ADMIN'],
        icon: 'FiBriefcase'
    },
    global_audit: {
        name: 'Global Audit Feed',
        description: 'Platform-wide activity logs',
        roles: ['SUPER_ADMIN'],
        icon: 'FiFileText'
    },
    revenue_chart: {
        name: 'Revenue Chart',
        description: 'MRR and billing metrics',
        roles: ['SUPER_ADMIN'],
        icon: 'FiDollarSign'
    },

    // Cost & Savings widgets (Multi-role)
    cost_kpi: {
        name: 'Monthly Spend',
        description: 'Current month cloud costs',
        roles: ['SUPER_ADMIN', 'ORG_ADMIN', 'CLIENT', 'TEAM_LEAD', 'MEMBER'],
        icon: 'FiDollarSign'
    },
    savings_kpi: {
        name: 'Net Savings',
        description: 'Total savings achieved',
        roles: ['SUPER_ADMIN', 'ORG_ADMIN', 'CLIENT', 'TEAM_LEAD', 'MEMBER'],
        icon: 'FiTrendingDown'
    },
    savings_chart: {
        name: 'Savings Projection',
        description: 'Optimized vs unoptimized comparison',
        roles: ['SUPER_ADMIN', 'ORG_ADMIN', 'CLIENT', 'TEAM_LEAD'],
        icon: 'FiBarChart2'
    },
    fleet_composition: {
        name: 'Fleet Composition',
        description: 'Instance type distribution',
        roles: ['SUPER_ADMIN', 'ORG_ADMIN', 'CLIENT', 'TEAM_LEAD'],
        icon: 'FiPieChart'
    },
    spend_forecast: {
        name: 'Spend Forecast',
        description: 'End-of-month spend projection with burn rate',
        roles: ['ORG_ADMIN', 'CLIENT', 'TEAM_LEAD'],
        icon: 'FiTrendingUp'
    },
    agent_status: {
        name: 'Agent Status',
        description: 'Live agent heartbeat monitoring',
        roles: ['ORG_ADMIN', 'CLIENT', 'TEAM_LEAD'],
        icon: 'FiActivity'
    },
    cluster_health: {
        name: 'Cluster Health',
        description: 'Kubernetes cluster status',
        roles: ['SUPER_ADMIN', 'ORG_ADMIN', 'CLIENT', 'TEAM_LEAD'],
        icon: 'FiServer'
    },
    activity_feed: {
        name: 'Activity Feed',
        description: 'Recent actions and events',
        roles: ['SUPER_ADMIN', 'ORG_ADMIN', 'CLIENT', 'TEAM_LEAD', 'MEMBER'],
        icon: 'FiClock'
    },
    ri_health: {
        name: 'RI Health',
        description: 'Reserved Instance optimization',
        roles: ['ORG_ADMIN', 'CLIENT', 'TEAM_LEAD'],
        icon: 'FiTrendingUp'
    },
    s3_health: {
        name: 'S3 Health',
        description: 'Storage tiering opportunities',
        roles: ['ORG_ADMIN', 'CLIENT', 'TEAM_LEAD'],
        icon: 'FiDatabase'
    },
    rds_health: {
        name: 'RDS Health',
        description: 'Multi-AZ optimization',
        roles: ['ORG_ADMIN', 'CLIENT', 'TEAM_LEAD'],
        icon: 'FiServer'
    },
    transfer_health: {
        name: 'Data Transfer',
        description: 'Network cost optimization',
        roles: ['ORG_ADMIN', 'CLIENT', 'TEAM_LEAD'],
        icon: 'FiGlobe'
    },

    // Team Lead widgets
    team_budget: {
        name: 'Team Budget',
        description: 'Team cost allocation',
        roles: ['ORG_ADMIN', 'CLIENT', 'TEAM_LEAD'],
        icon: 'FiUsers'
    },
    pending_approvals: {
        name: 'Pending Approvals',
        description: 'Tickets awaiting action',
        roles: ['SUPER_ADMIN', 'ORG_ADMIN', 'CLIENT', 'TEAM_LEAD'],
        icon: 'FiAlertCircle'
    },
    member_list: {
        name: 'Team Members',
        description: 'Team member overview',
        roles: ['TEAM_LEAD'],
        icon: 'FiUsers'
    },

    // Member widgets
    my_tickets: {
        name: 'My Tickets',
        description: 'Your access requests',
        roles: ['MEMBER'],
        icon: 'FiFileText'
    },
    my_resources: {
        name: 'My Resources',
        description: 'Resources you have access to',
        roles: ['MEMBER'],
        icon: 'FiServer'
    }
};

/**
 * Get available widgets for a specific role
 */
export const getWidgetsForRole = (role) => {
    return Object.entries(WIDGET_METADATA)
        .filter(([key, meta]) => meta.roles.includes(role))
        .map(([key, meta]) => ({ key, ...meta }));
};

/**
 * Get default layout for a role
 */
export const getDefaultLayout = (role) => {
    return ROLE_DEFAULTS[role] || ROLE_DEFAULTS.MEMBER;
};
