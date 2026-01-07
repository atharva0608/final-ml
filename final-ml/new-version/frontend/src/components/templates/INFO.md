# Template Components - Component Information

> **Last Updated**: 2025-12-31 12:36:00
> **Maintainer**: LLM Agent

## Folder Purpose
Node template management UI including template grid and creation wizard.

## Planned Components
- **NodeTemplates.jsx**: Template grid (client-tmpl-list-unique-indep-view-grid, client-tmpl-toggle-reuse-dep-click-default)
- **TemplateWizard.jsx**: Template creation wizard (client-tmpl-logic-unique-indep-run-validate)

## APIs Used
- GET /templates
- POST /templates
- PATCH /templates/{id}/default
- DELETE /templates/{id}
- POST /templates/validate

## Schemas
- SCHEMA-TEMPLATE-TmplList
- SCHEMA-TEMPLATE-NodeTemplate
- SCHEMA-TEMPLATE-TemplateValidation
