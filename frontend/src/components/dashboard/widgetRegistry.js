/**
 * Widget Registry - Maps widget keys to React components
 * Central registry for all dashboard widgets
 */
import React from 'react';

// Import widget components (will be created)
import CostKPICard from './widgets/CostKPICard';
import SavingsKPICard from './widgets/SavingsKPICard';
import SavingsChart from './widgets/SavingsChart';
import FleetComposition from './widgets/FleetComposition';
import ActivityFeed from './widgets/ActivityFeed';
import ClusterHealthCard from './widgets/ClusterHealthCard';
import PendingApprovalsCard from './widgets/PendingApprovalsCard';
import PlatformHealthCard from './widgets/PlatformHealthCard';
import TenantListCard from './widgets/TenantListCard';
import RIHealthCard from '../ri/RIHealthCard';
import S3HealthCard from '../s3/S3HealthCard';
import RDSHealthCard from '../rds/RDSHealthCard';
import TransferHealthCard from '../transfer/TransferHealthCard';

/**
 * Widget Registry
 * Maps widget keys to their component implementations
 */
export const WIDGET_REGISTRY = {
    // Cost & Savings
    cost_kpi: CostKPICard,
    savings_kpi: SavingsKPICard,
    savings_chart: SavingsChart,
    fleet_composition: FleetComposition,

    // Optimization
    ri_health: RIHealthCard,
    s3_health: S3HealthCard,
    rds_health: RDSHealthCard,
    transfer_health: TransferHealthCard,

    // Operations
    activity_feed: ActivityFeed,
    cluster_health: ClusterHealthCard,
    pending_approvals: PendingApprovalsCard,

    // Super Admin
    platform_health: PlatformHealthCard,
    tenant_list: TenantListCard,
    global_audit: ActivityFeed, // Reuse with different props
    revenue_chart: SavingsChart,  // Placeholder - reuse

    // Team widgets (use same components with different props)
    team_budget: CostKPICard,
    member_list: TenantListCard,
    my_tickets: PendingApprovalsCard,
    my_resources: ClusterHealthCard,
    team_activity: ActivityFeed
};

/**
 * Render a widget by key
 * @param {string} widgetKey - The widget key from roleDefaults
 * @param {object} props - Props to pass to the widget
 * @returns {React.Element|null}
 */
export const renderWidget = (widgetKey, props = {}) => {
    const WidgetComponent = WIDGET_REGISTRY[widgetKey];

    if (!WidgetComponent) {
        console.warn(`Widget not found in registry: ${widgetKey}`);
        return null;
    }

    return <WidgetComponent key={widgetKey} widgetKey={widgetKey} {...props} />;
};

export default WIDGET_REGISTRY;
