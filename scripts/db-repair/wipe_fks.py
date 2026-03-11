with open('migrations/versions/20260307_0424_fe44504ae542_catch_all_columns_safest.py', 'r') as f:
    lines = f.readlines()

new_lines = []
for line in lines:
    if "op.create_foreign_key" not in line and "op.drop_constraint" not in line:
        new_lines.append(line)

with open('migrations/versions/20260307_0424_fe44504ae542_catch_all_columns_ultimate.py', 'w') as f:
    f.write(''.join(new_lines))
