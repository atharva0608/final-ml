# Frontend Lib Module

## Purpose

Utility functions and helper libraries.

**Last Updated**: 2025-12-25
**Authority Level**: LOW-MEDIUM

---

## Files

### utils.js
**Purpose**: Common utility functions used across the app
**Lines**: ~20
**Key Functions**:
- `cn(...classes)` - Conditional className utility (likely using clsx or classnames)
- String formatting helpers
- Date/time utilities
- Number formatting (currency, percentages)

**Example Functions**:
```javascript
// Conditional className merge
export function cn(...classes) {
  return classes.filter(Boolean).join(' ');
}

// Format currency
export function formatCurrency(amount) {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD'
  }).format(amount);
}

// Format percentage
export function formatPercentage(value) {
  return `${(value * 100).toFixed(2)}%`;
}
```

**Dependencies**:
- clsx or classnames (likely)
- Built-in JavaScript APIs

**Recent Changes**: None recent

---

## Common Utility Patterns

### ClassName Merging
```javascript
import { cn } from '../lib/utils';

<div className={cn(
  'base-class',
  isActive && 'active-class',
  isDisabled && 'disabled-class'
)} />
```

### Currency Formatting
```javascript
import { formatCurrency } from '../lib/utils';

const cost = formatCurrency(123.45); // "$123.45"
```

---

## Dependencies

### Depends On:
- clsx or classnames (optional)
- JavaScript built-in APIs

### Depended By:
- All components using utility functions
- Styling utilities

**Impact Radius**: LOW-MEDIUM (helper functions)

---

## Recent Changes

### 2025-12-25: Governance Structure Establishment
**Files Changed**: None (metadata only)
**Reason**: Document existing utilities
**Impact**: No code changes, documentation baseline
**Reference**: `/index/recent_changes.md`

---

## Usage

### Import Utilities
```javascript
import { cn, formatCurrency, formatPercentage } from '../lib/utils';

function MyComponent({ cost, savings }) {
  return (
    <div className={cn('card', cost > 100 && 'expensive')}>
      <p>Cost: {formatCurrency(cost)}</p>
      <p>Savings: {formatPercentage(savings)}</p>
    </div>
  );
}
```

---

## Known Issues

### None

Lib module is stable as of 2025-12-25.

---

_Last Updated: 2025-12-25_
_Authority: LOW-MEDIUM - Utilities_
