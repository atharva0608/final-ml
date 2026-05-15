/**
 * LEGACY SIDEBAR ROUTE MAPPINGS — moved to temp-bin 2026-04-26
 *
 * These routeMap keys were removed from MainLayout.jsx because they are NOT
 * referenced as item `id` values in the current NAV_STRUCTURE.
 * They came from the old flat sidebar architecture (pre-restructure).
 *
 * Safe to delete after confirming no external code references these IDs.
 */

const LEGACY_ROUTE_MAP = {
  // Old dashboard tab routes (pre-restructure — single page with tabs)
  "dashboard-cost": "/dashboard?tab=cost",
  "dashboard-infra": "/dashboard?tab=infra",
  "dashboard-gov": "/dashboard?tab=governance",

  // Old ASCP AI routes (tab-based navigation, pre-restructure)
  "ascpai": "/ascp-ai",
  "ascpai-dashboard": "/ascp-ai?tab=dashboard",
  "ascpai-decision-engine-v3": "/ascp-ai?tab=decision-engine-v3",
  "ascpai-rankings": "/ascp-ai?tab=rankings",
  "ascpai-heatmap": "/ascp-ai?tab=heatmap",
  "ascpai-rebalancing": "/ascp-ai?tab=rebalancing",

  // Old right-sizing tab routes (pre-restructure — single page with tabs)
  "rightsizing": "/right-sizing",
  "rs-karpenter": "/right-sizing?tab=karpenter",
  "rs-workload": "/right-sizing?tab=workload",
  "rs-placement": "/right-sizing?tab=placement",
  "rs-config": "/right-sizing?tab=config",
  "rs-history": "/right-sizing?tab=history",
  "rs-savings": "/right-sizing?tab=savings",

  // Old hygiene route (superseded by cost-hygiene → /cost-savings/resource-hygiene)
  "resource-hygiene": "/hygiene",

  // Short-form keys that are now redundant (replaced by prefixed section-aware keys)
  "clusters": "/clusters",           // → use infra-clusters
  "node-templates": "/node-templates", // → use infra-node-templates
  "approvals": "/approvals",           // → use gov-approvals
  "tag-governance": "/tagging-policies", // → use gov-tags
  "audit": "/audit",                   // → use settings-audit
  "placement-advisor": "/placement-advisor", // → use opt-placement / workload-placement
  "ri-analysis": "/ri-analysis",       // → use cost-ri
  "s3-analysis": "/s3-analysis",       // → use cost-s3
  "rds-analysis": "/rds-analysis",     // → use cost-rds
  "transfer-analysis": "/transfer-analysis", // → use cost-transfer
  "policies": "/policies",             // → use gov-policies
  "gov-roles": "/roles",               // → NAV_STRUCTURE sub-item id is "roles", not "gov-roles"

  // Cost items with no dedicated page (placeholder tab targets)
  "cost-forecast": "/dashboard?tab=cost",
  "cost-impact": "/right-sizing?tab=savings",

  // Workload sub-item that points to ASCP AI tab (no dedicated page)
  "workload-heatmap": "/ascp-ai?tab=heatmap",
};

export default LEGACY_ROUTE_MAP;
