import re

with open('./migrations/versions/20260307_0439_827fea8cbdd0_final_missing_tables.py', 'r') as f:
    content = f.read()

# Clean up any botched replacements
content = content.replace("sa.Enum(create_type=False, ", "sa.Enum(")
content = content.replace("postgresql.ENUM(create_type=False, ", "postgresql.ENUM(")
content = content.replace(", create_type=False, name=", ", name=")

# Now safely apply create_type=False to ALL Enums exactly once
content = content.replace(", name=", ", create_type=False, name=")

# Upgrade sa.Enum to postgresql.ENUM so create_table respects create_type=False
content = content.replace("sa.Enum(", "postgresql.ENUM(")

with open('./migrations/versions/20260307_0439_827fea8cbdd0_final_missing_tables.py', 'w') as f:
    f.write(content)
