import re

with open('migrations/versions/20260307_0422_a53a932ff96e_catch_all_missing_safe.py', 'r') as f:
    lines = f.readlines()

with open('migrations/versions/20260307_0422_a53a932ff96e_catch_all_missing_safer.py', 'w') as f:
    skip = False
    for line in lines:
        if "op.alter_column('approvals', 'type'" in line or "op.alter_column('approvals', 'status'" in line or "op.alter_column('accounts', 'status'" in line or "op.alter_column('tag_policies', 'enforcement_level'" in line or "op.alter_column('tag_policies', 'value_mode'" in line:
            skip = True
        elif skip and "type_=" in line and ");" in line:
             skip = False
             continue
        elif skip and ");" in line:
            skip = False
            continue
        elif skip and ")" in line and "type_=" not in line:
            skip = False
            continue
            
        # Simplified stripping since alembic often uses a multiline alter_column
        pass

# Let's just use regex to strip all op.alter_column entirely since it causes most issues
with open('migrations/versions/20260307_0422_a53a932ff96e_catch_all_missing_safer.py', 'w') as f:
    content = "".join(lines)
    # Removing all alter_column blocks. We only care about added tables, indices, and columns.
    safe_content = re.sub(r"    op\.alter_column\([^)]+\)", "", content, flags=re.MULTILINE | re.DOTALL)
    f.write(safe_content)
