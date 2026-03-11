import re

with open('migrations/versions/20260307_0424_fe44504ae542_catch_all_columns_safer.py', 'r') as f:
    content = f.read()

# Make all newly added columns nullable so they don't break on existing populated tables
content = content.replace("nullable=False", "nullable=True")

with open('migrations/versions/20260307_0424_fe44504ae542_catch_all_columns_safest.py', 'w') as f:
    f.write(content)
