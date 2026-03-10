import re

with open('migrations/versions/20260307_0422_a53a932ff96e_catch_all_missing.py', 'r') as f:
    lines = f.readlines()

with open('migrations/versions/20260307_0422_a53a932ff96e_catch_all_missing_safe.py', 'w') as f:
    for line in lines:
        if not re.search(r'op\.drop_table|op\.drop_column|op\.drop_index', line):
            f.write(line)
