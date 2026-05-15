# WorkloadPlacement — Deprecated / Removed Components

These code blocks were removed from `WorkloadPlacement.jsx` as part of the UI
simplification pass (plan.md). They are preserved here for reference and can be
deleted once the removal is confirmed stable.

---

## 1. Unused import

```js
import { FiAlertCircle, FiRefreshCw } from 'react-icons/fi';
//                      ^^^^^^^^^^^^ removed — only used in the old timeline dots
```

---

## 2. `TIMELINE_LABELS` constant (replaced by `TIMELINE_STEPS`)

```js
const TIMELINE_LABELS = [
  'Drift Detected',
  'Action Queued',
  'Eviction Triggered',
  'Spot Scheduled',
  'Node Provisioning',
  'Resolved',
];
```

---

## 3. `distributeAcrossAz` helper (only called by `buildExpectedTopology`)

```js
function distributeAcrossAz(total, numAz) {
  if (!total || total <= 0 || numAz <= 0) return Array(numAz).fill(0);
  const base = Math.floor(total / numAz);
  const rem  = total % numAz;
  return Array.from({ length: numAz }, (_, i) => base + (i < rem ? 1 : 0));
}
```

---

## 4. `buildExpectedTopology` function (never called in JSX)

```js
function buildExpectedTopology(odTarget, spotTarget, numAz, realAzNames) {
  const azNames = Array.from({ length: numAz }, (_, i) =>
    realAzNames[i] || `AZ-${i + 1}`
  );
  const odPerAz   = distributeAcrossAz(odTarget   ?? 0, numAz);
  const spotPerAz = distributeAcrossAz(spotTarget ?? 0, numAz);
  return azNames.map((name, i) => ({
    name,
    od:   odPerAz[i],
    spot: spotPerAz[i],
    minNodes: (odPerAz[i] > 0 ? 1 : 0) + (spotPerAz[i] > 0 ? 1 : 0),
  }));
}
```

---

## 5. `numAz` state (only fed into `buildExpectedTopology`)

```js
const [numAz, setNumAz] = useState(2);
```

---

## 6. `lockFields` constant (replaced by `lockSummary()` 1-liner)

```js
const lockFields = [
  { l: 'PDB Blocked',    v: locks.pdb_active          ? 'True'   : 'False',                    warn: locks.pdb_active },
  { l: 'Action Cooldown',v: locks.cooldown_active      ? `Active (${locks.cooldown_expires_in}s)` : 'None', warn: locks.cooldown_active },
  { l: 'In-Flight',      v: `${locks.in_flight_actions || 0} Actions`,                          warn: (locks.in_flight_actions || 0) > 0 },
  { l: 'KEDA Scaling',   v: locks.keda_scaling_active  ? 'Active' : 'None',                     warn: locks.keda_scaling_active },
  { l: 'Rollout Blocked',v: locks.rollout_blocked      ? `Blocked (${locks.rollout_blocked_expires_in}s)` : 'None', warn: locks.rollout_blocked },
];
```

---

## 7. `Reconciliation Timeline` JSX block (replaced by compact Now/Next)

```jsx
{/* Reconciliation Timeline */}
<div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
  <h4 className="text-xs font-bold uppercase tracking-wider text-gray-400 mb-5">Reconciliation Timeline</h4>
  <div className="relative flex justify-between items-start">
    <div className="absolute top-3 left-5 right-5 h-0.5 bg-gray-100" />
    <div className="absolute top-3 left-5 h-0.5 bg-indigo-500 transition-all"
      style={{ width: `calc(${Math.min(w.timeline_step / 5, 1) * 90}%)` }} />
    {TIMELINE_LABELS.map((label, i) => {
      const step = w.timeline_step;
      const done   = i < step;
      const active = i === step;
      return (
        <div key={i} className="flex flex-col items-center gap-1.5 z-10 w-14">
          <div className={`w-6 h-6 rounded-full flex items-center justify-center border-2 text-[11px]
            ${done ? 'bg-indigo-600 border-indigo-600 text-white'
                   : active ? 'bg-white border-indigo-500 text-indigo-600'
                   : 'bg-gray-100 border-gray-200 text-gray-400'}`}>
            {done ? '✓' : active ? <FiRefreshCw className="w-3 h-3 animate-spin" /> : ''}
          </div>
          <span className={`text-center text-[9px] leading-tight ${done || active ? 'text-gray-800 font-medium' : 'text-gray-400'}`}>
            {label}
          </span>
        </div>
      );
    })}
  </div>
</div>
```

---

## 8. State Locks table JSX (replaced by `lockSummary()` 1-liner)

```jsx
<div className="space-y-2 text-xs">
  {lockFields.map(f => (
    <div key={f.l} className="flex justify-between items-center">
      <span className="text-gray-500">{f.l}</span>
      <span className={`font-mono font-medium ${f.warn ? 'text-amber-600' : 'text-gray-900'}`}>{f.v}</span>
    </div>
  ))}
</div>
```
