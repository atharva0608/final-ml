# Utils - Component Information

> **Last Updated**: 2025-12-31 12:36:00
> **Maintainer**: LLM Agent

---

## Folder Purpose
Contains utility functions and helper modules for cryptography, validation, and common operations used across the backend.

---

## Component Table (Planned)

| File Name | Purpose | Key Functions | Dependencies | Status |
|-----------|---------|---------------|--------------|--------|
| crypto.py | Cryptography utilities | hash_password(), verify_password(), generate_token() | bcrypt, PyJWT | Pending |
| validators.py | Input validation | validate_email(), validate_aws_arn(), validate_cron() | re, email-validator | Pending |
| helpers.py | Common helpers | calculate_savings(), format_currency(), parse_schedule_matrix() | None | Pending |

---

## Recent Changes

### [2025-12-31 12:36:00] - Initial Utils Structure Created
**Changed By**: LLM Agent
**Reason**: Create organized folder structure for utility functions
**Impact**: Created backend/utils/ directory for helper functions
**Files Modified**:
- Created backend/utils/
- Created backend/utils/INFO.md (this file)
**Feature IDs Affected**: N/A (Infrastructure setup)
**Breaking Changes**: No

---

## Dependencies

- **Crypto**: bcrypt, PyJWT, secrets
- **Validation**: email-validator, re (regex)
- **Date/Time**: datetime, pytz

---

## Utility Categories

### crypto.py:
- Password hashing with bcrypt
- JWT token generation and validation
- API key generation
- SHA-256 hashing for audit checksums

### validators.py:
- Email format validation
- AWS ARN validation
- CRON expression validation
- Instance type validation
- Region validation

### helpers.py:
- Savings calculation formulas
- Currency formatting
- Schedule matrix parsing (168 elements)
- Timezone conversion
- Date range generation

---

## Testing Requirements

- Unit tests for all functions
- Edge case tests
- Performance tests
- Security tests (crypto functions)
