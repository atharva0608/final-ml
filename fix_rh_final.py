import os

TARGET_FILE = "frontend/src/components/cleanup/CleanupDashboard.jsx"
with open(TARGET_FILE, "r") as f:
    raw_code = f.read()

# Replace any lingering MOCK_RESOURCES.length with allResources.length
raw_code = raw_code.replace("MOCK_RESOURCES.length", "allResources.length")

replace_kpis = """
  // Aggregate KPIs based on API data
  const TOTAL_DISCOVERED = totalCost?.total_cost ? Number(totalCost.total_cost.toFixed(2)) : 0;
  const TOTAL_POTENTIAL  = scanResult?.summary?.total_potential_savings ? Number(scanResult.summary.total_potential_savings.toFixed(2)) : 0;
  const UNTAGGED         = allResources.filter(r => r.missingTags.length > 0).length;
  const TAG_HEALTH_PCT   = allResources.length > 0 ? Math.round((1 - UNTAGGED / allResources.length) * 100) : 100;
  const SAFETY_SAFE      = allResources.filter(r => r.status === "SAFE_TO_DELETE" || r.status === "STOPPED").length;
  const SAFETY_REVIEW    = allResources.filter(r => r.status === "ORPHANED" || r.status === "NOT_COMPLIANT").length;
  const SAFETY_RISKY     = allResources.filter(r => r.status === "RISK" || r.status === "UNAUTHORIZED").length;
"""

# Find where the API definition functions are, to inject the Sidebar Categories and KPI derivations 
# that I accidentally wiped out by placing them at the end of the functional component (they need to be accessible!)

raw_code = raw_code.replace("  const SIDEBAR_CATEGORIES = [", replace_kpis + "\n  const SIDEBAR_CATEGORIES = [")

with open(TARGET_FILE, "w") as f:
    f.write(raw_code)
