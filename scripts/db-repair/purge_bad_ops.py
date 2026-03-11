with open('./migrations/versions/20260307_0439_827fea8cbdd0_final_missing_tables.py', 'r') as f:
    lines = f.readlines()

new_lines = []
skip_until_paren = False
paren_count = 0

bad_ops = [
    "op.drop_table",
    "op.drop_column",
    "op.drop_index",
    "op.drop_constraint",
    "op.alter_column",
    "op.create_foreign_key",
    "op.create_index"
]

for line in lines:
    is_bad = any(op in line for op in bad_ops)
    
    if is_bad and not skip_until_paren:
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

with open('./migrations/versions/20260307_0439_827fea8cbdd0_final_missing_tables.py', 'w') as f:
    f.write(''.join(new_lines))
