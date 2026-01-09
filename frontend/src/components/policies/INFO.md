# Policy Components - Component Information

> **Last Updated**: 2025-12-31 12:36:00
> **Maintainer**: LLM Agent

## Folder Purpose
Optimization policy configuration UI.

## Planned Components
- **OptimizationPolicies.jsx**: Policy configuration (client-pol-toggle-reuse-dep-click-karpenter, client-pol-slider-reuse-dep-drag-binpack)

## APIs Used
- PATCH /policies/karpenter
- PATCH /policies/strategy
- PATCH /policies/binpack
- PATCH /policies/fallback
- PATCH /policies/exclusions

## Schemas
- SCHEMA-POLICY-PolState
- SCHEMA-POLICY-PolicyUpdate
