with open('migrations/versions/20260307_0424_fe44504ae542_catch_all_columns_safe.py', 'r') as f:
    lines = f.readlines()

new_lines = []
skip_until_paren = False
paren_count = 0

for line in lines:
    is_create_index = "op.create_index" in line
    
    if is_create_index and not skip_until_paren:
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

with open('migrations/versions/20260307_0424_fe44504ae542_catch_all_columns_safer.py', 'w') as f:
    f.write(''.join(new_lines))
