import os

TARGET_FILE = "frontend/src/components/cleanup/CleanupDashboard.jsx"

with open(TARGET_FILE, "r") as f:
    raw_code = f.read()

# Fix 1: Add useMemo back to import if missing (It's already there but just in case)
raw_code = raw_code.replace("import React, { useState, useEffect, useMemo } from 'react';", "import React, { useState, useEffect, useMemo } from 'react';")

# Fix 2: Move STATUS_META to the top (it's used by StatusPill but defined below if at all)
status_meta = """// --- STATUS META ---
const STATUS_META = {
  SAFE_TO_DELETE: { label: "Safe to Delete", dot: C.green,  bg: C.greenBg,  border: C.greenBorder },
  ORPHANED:       { label: "Orphaned",        dot: C.amber,  bg: C.amberBg,  border: C.amberBorder },
  STOPPED:        { label: "Stopped",         dot: C.blue,   bg: C.blueBg,   border: C.blueBorder  },
  RISK:           { label: "Risk",            dot: C.red,    bg: C.redBg,    border: C.redBorder   },
  UNAUTHORIZED:   { label: "Unauthorized",    dot: C.purple, bg: C.purpleBg, border: C.purpleBorder},
  NOT_COMPLIANT:  { label: "Not Compliant",   dot: C.orange, bg: C.orangeBg, border: C.orangeBorder},
};
"""
raw_code = raw_code.replace("// ─── TINY COMPONENTS ─────────────────────────────────────────────────────────", status_meta + "\n// ─── TINY COMPONENTS ─────────────────────────────────────────────────────────")

with open(TARGET_FILE, "w") as f:
    f.write(raw_code)
