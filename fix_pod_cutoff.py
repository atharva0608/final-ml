import re

with open("backend/api/optimize_routes.py", "r") as f:
    content = f.read()

# Fix _cutoff (used for _pod_count_rows)
content = re.sub(
    r'_cutoff = _dt.utcnow\(\) - _td\(minutes=30\)',
    r'_cutoff = _dt.utcnow() - _td(minutes=3)',
    content
)

# Fix _cutoff_w (used for _pod_rows_w)
content = re.sub(
    r'_cutoff_w = _dt.utcnow\(\) - _td\(minutes=15\)',
    r'_cutoff_w = _dt.utcnow() - _td(minutes=3)',
    content
)

with open("backend/api/optimize_routes.py", "w") as f:
    f.write(content)

print("Updated cutoffs to 3 minutes.")
