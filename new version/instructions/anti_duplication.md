# Anti-Duplication Policy

## Core Rule

> **"If functionality exists, extend it. Never recreate."**

This is the **most critical** rule for maintaining system integrity at scale.

---

## Why Duplication is Catastrophic

### The Duplication Death Spiral

```
Developer creates duplicate_function_v2()
  ↓
Bug found in original_function()
  ↓
Bug fixed in original_function()
  ↓
duplicate_function_v2() still has bug
  ↓
User encounters bug again
  ↓
Developer creates duplicate_function_v3()
  ↓
System now has 3 versions of same logic
  ↓
Maintenance becomes impossible
```

### Real-World Impact

- **Security**: Bug fixes don't propagate to duplicates
- **Maintenance**: Must update N versions instead of 1
- **Confusion**: Developers don't know which version to use
- **Drift**: Duplicates diverge over time
- **Testing**: Must test N implementations
- **Documentation**: Must document N versions

---

## Duplication Detection Protocol

### Before Creating ANY:

#### 1. Database Tables/Schemas

**Check**:
- `/index/feature_index.md` → Database Tables section
- Existing schema files
- Database models in `database/models.py`

**Ask**:
- Does a table with similar purpose exist?
- Can I add columns to existing table?
- Can I use table relationships instead of duplication?

**Example**:
```python
# ❌ WRONG: Creating duplicate user table
class ClientUser(Base):
    id = Column(Integer, primary_key=True)
    username = Column(String)
    email = Column(String)

# ✅ CORRECT: Extending existing User table
class User(Base):
    id = Column(Integer, primary_key=True)
    username = Column(String)
    email = Column(String)
    role = Column(String)  # Added field instead of new table
```

#### 2. API Endpoints

**Check**:
- `/index/feature_index.md` → API Endpoints section
- `backend/api/` modules
- Module `info.md` files

**Ask**:
- Does an endpoint with similar purpose exist?
- Can I add parameters to existing endpoint?
- Can I version existing endpoint instead?

**Example**:
```python
# ❌ WRONG: Creating duplicate endpoint
@router.get("/client/accounts/list")
async def list_client_accounts():
    # Same as /client/accounts
    pass

# ✅ CORRECT: Using existing endpoint
# /client/accounts already exists - use that!
```

#### 3. Functions/Classes

**Check**:
- Module `info.md` → Functions/Classes section
- Grep for similar function names
- Related utility files

**Ask**:
- Does a function with similar logic exist?
- Can I add a parameter instead of duplicating?
- Can I refactor existing function to handle both cases?

**Example**:
```python
# ❌ WRONG: Duplicating validation logic
def validate_email_for_login(email):
    return re.match(r"[^@]+@[^@]+\.[^@]+", email)

def validate_email_for_signup(email):
    return re.match(r"[^@]+@[^@]+\.[^@]+", email)

# ✅ CORRECT: Single function with parameters
def validate_email(email, context="general"):
    pattern = r"[^@]+@[^@]+\.[^@]+"
    is_valid = re.match(pattern, email)
    # Add context-specific logic if needed
    return is_valid
```

#### 4. React Components

**Check**:
- `/index/feature_index.md` → Frontend Components section
- `frontend/src/components/info.md`
- Similar component names

**Ask**:
- Does a component with similar UI exist?
- Can I use props instead of duplicating?
- Can I compose existing components?

**Example**:
```jsx
// ❌ WRONG: Duplicating button component
function GreenButton({ text }) {
  return <button className="green">{text}</button>;
}

function BlueButton({ text }) {
  return <button className="blue">{text}</button>;
}

// ✅ CORRECT: Single component with props
function Button({ text, color = "blue" }) {
  return <button className={color}>{text}</button>;
}
```

---

## Allowed Duplication (Exceptions)

### When Duplication IS Acceptable

1. **Different Domains**: User authentication vs API key authentication
   - Different purposes, different security models
   - OK to have separate implementations

2. **Different Layers**: Database model vs API response model
   - Different purposes (storage vs transfer)
   - OK to have separate definitions

3. **Performance**: Critical path optimization
   - Must document WHY in `info.md`
   - Must reference original implementation

4. **Legacy Migration**: Temporary duplicate during refactor
   - Must have sunset date in `info.md`
   - Must be documented in `/progress/progress_tracker.md`

### Documentation Required for Exceptions

If you create an exception, **MUST** document:

```markdown
## Intentional Duplication

### Function: `fast_validate_email()`
**Reason**: Performance-critical path (10x faster)
**Original**: `validate_email()`
**Trade-off**: Duplicates validation logic for 10x speed improvement
**Maintenance**: Must sync with `validate_email()` on changes
**Review Date**: 2026-01-01
**Justification**: [Link to performance benchmark]
```

---

## Extension vs Duplication

### Pattern 1: Adding Parameters

```python
# Instead of creating new function:
def get_user_by_id(user_id):
    return db.query(User).filter(User.id == user_id).first()

# Extend existing with optional parameter:
def get_user(id=None, username=None, email=None):
    query = db.query(User)
    if id:
        query = query.filter(User.id == id)
    elif username:
        query = query.filter(User.username == username)
    elif email:
        query = query.filter(User.email == email)
    return query.first()
```

### Pattern 2: Composition Over Duplication

```python
# Instead of duplicating logic:
def send_email_to_client(client_id, subject, body):
    client = get_client(client_id)
    send_email(client.email, subject, body)
    log_email(client_id, "sent")

# Compose smaller functions:
def send_email(to, subject, body):
    # Email sending logic
    pass

def send_email_to_user(user, subject, body):
    send_email(user.email, subject, body)
    log_email(user.id, "sent")
```

### Pattern 3: Inheritance/Interfaces

```python
# Instead of duplicating class structure:
class AdminUser:
    username: str
    password: str
    admin_level: int

class ClientUser:
    username: str
    password: str
    company_name: str

# Use inheritance:
class User(Base):
    username: str
    password: str
    role: str

class AdminUser(User):
    admin_level: int

class ClientUser(User):
    company_name: str
```

---

## Duplication Detection Checklist

Before implementing, ask:

- [ ] Have I checked `/index/feature_index.md`?
- [ ] Have I read relevant module `info.md`?
- [ ] Have I grepped for similar function names?
- [ ] Have I checked database models?
- [ ] Have I reviewed existing API endpoints?
- [ ] Have I looked for similar React components?
- [ ] Can I extend existing code instead?
- [ ] If duplicating, is it in the exception list?
- [ ] If duplicating, have I documented WHY?

**If ANY answer is "No", STOP and verify before proceeding.**

---

## Enforcement

### Code Review Failures

Any PR with duplication **MUST**:
1. Justify why extension wasn't possible
2. Document in module `info.md`
3. Add entry to `/progress/progress_tracker.md`
4. Set review/sunset date

### Remediation

If duplication is found:
1. Document in `/problems/problems_log.md`
2. Create consolidation task
3. Update `/index/dependency_index.md` to show duplication
4. Plan migration

---

_Last Updated: 2025-12-25_
_Authority Level: HIGHEST_
