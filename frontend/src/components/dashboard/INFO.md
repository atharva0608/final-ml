# Dashboard Components - Component Information

> **Last Updated**: 2025-12-31 12:36:00
> **Maintainer**: LLM Agent

## Folder Purpose
Dashboard UI components including KPI cards, charts, and activity feed.

## Planned Components
- **Dashboard.jsx**: Main dashboard (client-home-kpi-reuse-indep-view-spend, client-home-chart-unique-indep-view-proj)
- **KPICard.jsx**: Reusable KPI card component
- **ActivityFeed.jsx**: Real-time activity feed (client-home-feed-unique-indep-view-live)

## APIs Used
- GET /metrics/kpi
- GET /metrics/projection
- GET /metrics/composition
- GET /activity/live

## Schemas
- SCHEMA-METRIC-KPISet
- SCHEMA-METRIC-ChartData
- SCHEMA-METRIC-PieData
- SCHEMA-METRIC-FeedData
