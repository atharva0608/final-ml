# Cluster Components - Component Information

> **Last Updated**: 2025-12-31 12:36:00
> **Maintainer**: LLM Agent

## Folder Purpose
Cluster management UI components including registry table and detail drawer.

## Planned Components
- **ClusterRegistry.jsx**: Cluster table and management (client-cluster-table-unique-indep-view-list, client-cluster-button-reuse-dep-click-connect, client-cluster-button-reuse-dep-click-opt)
- **ClusterDetailDrawer.jsx**: Cluster details drawer

## APIs Used
- GET /clusters
- GET /clusters/{id}
- POST /clusters/connect
- POST /clusters/{id}/optimize
- GET /clusters/{id}/verify

## Schemas
- SCHEMA-CLUSTER-ClusterList
- SCHEMA-CLUSTER-ClusterDetail
- SCHEMA-CLUSTER-AgentCmd
- SCHEMA-CLUSTER-JobId
