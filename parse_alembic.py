import ast

with open('migrations/versions/20260307_0424_fe44504ae542_catch_all_columns.py', 'r') as f:
    code = f.read()

import re

# We will use text replacement but very carefully directed at specific full statements.
# Instead of regex, let's just comment out lines that contain forbidden ops.
# Since python statements can span multiple lines, we'll look for the start of the forbidden op
# and comment out everything until the closing parenthesis.

forbidden_ops = [
    "op.drop_table",
    "op.drop_column",
    "op.drop_index",
    "op.alter_column"
]

lines = code.split('\n')
new_lines = []
skip_until_paren = False
paren_count = 0

for line in lines:
    is_forbidden_start = any(op in line for op in forbidden_ops)
    
    if is_forbidden_start and not skip_until_paren:
        skip_until_paren = True
        paren_count = line.count('(') - line.count(')')
        new_lines.append(f"# {line}")
        if paren_count <= 0:
            skip_until_paren = False
        continue
        
    if skip_until_paren:
        paren_count += line.count('(') - line.count(')')
        new_lines.append(f"# {line}")
        if paren_count <= 0:
            skip_until_paren = False
    else:
        new_lines.append(line)

with open('migrations/versions/20260307_0424_fe44504ae542_catch_all_columns_safe.py', 'w') as f:
    f.write('\n'.join(new_lines))

