# Auth Components - Component Information

> **Last Updated**: 2025-12-31 12:36:00
> **Maintainer**: LLM Agent

## Folder Purpose
Authentication flow components including login, signup, and onboarding wizard.

## Planned Components
- **LoginPage.jsx**: Sign-up and sign-in forms (any-auth-form-reuse-dep-submit-signup, any-auth-form-reuse-dep-submit-signin)
- **AuthGateway.jsx**: Smart routing based on account status (any-auth-gateway-unique-indep-run-route)
- **ClientSetup.jsx**: Onboarding wizard (client-onboard-wizard-unique-indep-view-step1)

## APIs Used
- POST /api/auth/signup
- POST /api/auth/token
- GET /api/auth/me

## Schemas
- SCHEMA-AUTH-SignupRequest
- SCHEMA-AUTH-TokenResponse
- SCHEMA-AUTH-UserContext
