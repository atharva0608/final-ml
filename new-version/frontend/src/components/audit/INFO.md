# Audit Components - Component Information

> **Last Updated**: 2025-12-31 12:36:00
> **Maintainer**: LLM Agent

## Folder Purpose
Audit log and compliance UI including logs table and diff viewer.

## Planned Components
- **AuditLogs.jsx**: Audit logs table (client-audit-table-unique-indep-view-ledger, client-audit-drawer-unique-dep-view-diff)

## APIs Used
- GET /audit
- GET /audit/export
- GET /audit/{id}/diff

## Schemas
- SCHEMA-AUDIT-AuditLogList
- SCHEMA-AUDIT-AuditLog
- SCHEMA-AUDIT-DiffData
