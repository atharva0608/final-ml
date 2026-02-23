import os

TARGET_FILE = "frontend/src/components/cleanup/CleanupDashboard.jsx"
with open(TARGET_FILE, "r") as f:
    raw_code = f.read()

# Fix 3: The Sidebar component doesn't have activeType/setActiveType anymore, it expects categories
# Wait, Sidebar DOES have them in the props but they were not defined in CleanupDashboard.
# Let's add them back to CleanupDashboard.

missing_state = """
  const [activeType, setActiveType]     = useState("instance");
  const [selected, setSelected]         = useState(new Set());
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [search, setSearch]             = useState("");
"""
raw_code = raw_code.replace("export default function CleanupDashboard() {", "export default function CleanupDashboard() {\n" + missing_state)

with open(TARGET_FILE, "w") as f:
    f.write(raw_code)
