import React, { useState } from 'react';

// API: GET /api/v1/overview/summary
// TODO: Replace all mock data below with real API integration

const STATS = [
  { label: 'Monthly Spend',    value: '$18,420', sub: '$420 vs last mo',     subColor: 'text-red-600',  subIcon: '↑' },
  { label: 'Spot Savings',     value: '$6,840',  sub: '+$1,200',             subColor: 'text-green-600',subIcon: '+' },
  { label: 'Spot Coverage',    value: '64%',     sub: '+3%',                 subColor: 'text-green-600',subIcon: '↑' },
  { label: 'Active Nodes',     value: '24',      sub: '2 terminating',       subColor: 'text-gray-500', subIcon: '' },
  { label: 'Active Workloads', value: '312',     sub: 'pods, 14 namespaces', subColor: 'text-gray-500', subIcon: '' },
  { label: 'Pending Actions',  value: '3',       sub: 'AMBER',               subColor: 'text-amber-600',subIcon: '' },
];

const CLUSTERS = [
  { name: 'prod-us-east', nodes: 24, spot: 64, cpu: 34, mem: 51, spend: '$12,400', status: 'Healthy',    statusColor: 'bg-green-500' },
  { name: 'prod-eu-west', nodes: 11, spot: 45, cpu: 28, mem: 62, spend: '$4,200',  status: 'Suboptimal', statusColor: 'bg-amber-500' },
  { name: 'staging',      nodes: 3,  spot: 20, cpu: 12, mem: 18, spend: '$1,820',  status: 'Healthy',    statusColor: 'bg-green-500' },
];

const ACTIVITY = [
  { dot: 'bg-green-500',  title: 'Terminated unattached EBS volume',                                     detail: 'Saved $42/mo • 10 mins ago • prod-us-east' },
  { dot: 'bg-blue-600',   title: 'Replaced On-Demand with Spot c6g.4xlarge',                             detail: 'Saved $119/mo • 2 hours ago • prod-eu-west' },
  { dot: 'bg-gray-300',   title: 'Scaled down underutilized deployment frontend-api',                     detail: 'Saved $28/mo • 5 hours ago • staging' },
  { dot: 'bg-blue-600',   title: 'Right-sized container requests',                                        detail: 'Released 12 CPU, 32GB Mem • 1 day ago • prod-us-east' },
  { dot: 'bg-green-500',  title: 'Terminated idle cluster',                                               detail: 'Saved $350/mo • 2 days ago • dev-sandbox' },
];

const COST_DRIVERS = [
  { name: 'production',   pct: 45, spend: '$8,420' },
  { name: 'kube-system',  pct: 17, spend: '$3,200' },
  { name: 'data-pipeline',pct: 12, spend: '$2,210' },
  { name: 'ml-training',  pct:  8, spend: '$1,450' },
  { name: 'monitoring',   pct:  5, spend: '$940'   },
];

const CHART_BARS = [
  { spend: 72, savings: 38 }, { spend: 68, savings: 34 }, { spend: 75, savings: 40 },
  { spend: 65, savings: 35 }, { spend: 80, savings: 42 }, { spend: 70, savings: 38 },
  { spend: 60, savings: 32 }, { spend: 78, savings: 44 }, { spend: 85, savings: 48 },
  { spend: 72, savings: 40 }, { spend: 68, savings: 36 }, { spend: 74, savings: 42 },
  { spend: 70, savings: 38 }, { spend: 76, savings: 44 }, { spend: 82, savings: 46 },
  { spend: 66, savings: 34 }, { spend: 72, savings: 40 }, { spend: 78, savings: 44 },
  { spend: 74, savings: 42 }, { spend: 80, savings: 46 }, { spend: 68, savings: 36 },
  { spend: 64, savings: 32 }, { spend: 70, savings: 38 }, { spend: 76, savings: 43 },
  { spend: 72, savings: 40 }, { spend: 78, savings: 45 }, { spend: 84, savings: 48 },
  { spend: 70, savings: 39 }, { spend: 66, savings: 35 }, { spend: 72, savings: 40 },
];

const X_LABELS = ['Oct 1', 'Oct 8', 'Oct 15', 'Oct 22', 'Oct 29'];
const Y_LABELS = ['$25k', '$20k', '$15k', '$10k', '$5k', '0'];

export default function Overview() {
  const [costView, setCostView] = useState('Namespace');

  return (
    <div className="flex flex-col bg-gray-50 min-h-full w-full">
      <div className="p-6 flex flex-col gap-6 max-w-[1600px] mx-auto w-full">

        {/* ── Row 1: Stat Strip ── */}
        <section className="w-full bg-white border border-gray-200 rounded-xl overflow-hidden grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 divide-y md:divide-y-0 md:divide-x divide-gray-100 shadow-sm">
          {STATS.map(s => (
            <div key={s.label} className="p-4 flex flex-col gap-1">
              <span className="text-[11px] uppercase tracking-widest text-gray-400 font-semibold">{s.label}</span>
              <span className="text-2xl font-bold text-gray-900 font-mono tracking-tight">{s.value}</span>
              <div className={`flex items-center text-[12px] font-medium ${s.subColor}`}>
                {s.subIcon && <span className="mr-0.5">{s.subIcon}</span>}
                {s.label === 'Pending Actions'
                  ? <span className="px-2 py-0.5 bg-amber-100 text-amber-700 text-[11px] font-semibold rounded-full uppercase tracking-wider">{s.sub}</span>
                  : <span>{s.sub}</span>
                }
              </div>
            </div>
          ))}
        </section>

        {/* ── Row 2: Chart + Fleet ── */}
        <section className="flex flex-col lg:flex-row gap-5">

          {/* Spend vs Savings Chart */}
          <div className="flex-[3] bg-white rounded-xl border border-gray-200 p-5 shadow-sm flex flex-col">
            <div className="flex justify-between items-center mb-5">
              <h2 className="text-sm font-semibold text-gray-900">Spend vs Savings (30 Days)</h2>
              <div className="flex items-center gap-4 text-xs">
                <div className="flex items-center gap-1.5">
                  <div className="w-3 h-3 rounded-sm bg-blue-200 border border-blue-600" />
                  <span className="text-gray-500">Spend</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <div className="w-3 h-3 rounded-sm bg-green-100 border border-green-500" />
                  <span className="text-gray-500">Savings</span>
                </div>
              </div>
            </div>

            {/* SVG Area Chart */}
            {(() => {
              const W = 460, H = 200;
              const PL = 44, PR = 10, PT = 8, PB = 28;
              const CW = W - PL - PR, CH = H - PT - PB;
              const n = CHART_BARS.length;

              const pts = CHART_BARS.map((b, i) => ({
                x:  PL + (i / (n - 1)) * CW,
                sy: PT + CH * (1 - (5000 + ((b.spend   - 60) / 25) * 6500) / 25000),
                vy: PT + CH * (1 - Math.max(0, 200 + ((b.savings - 32) / 16) * 3800) / 25000),
              }));

              const makeLine = key => {
                let d = `M${pts[0].x},${pts[0][key]}`;
                for (let i = 1; i < n; i++) {
                  const a = pts[i - 1], b = pts[i];
                  const cx = (a.x + b.x) / 2;
                  d += ` C${cx},${a[key]} ${cx},${b[key]} ${b.x},${b[key]}`;
                }
                return d;
              };

              const baseY = PT + CH;
              const close = line => `${line} L${pts[n-1].x},${baseY} L${PL},${baseY} Z`;
              const spendLine   = makeLine('sy');
              const savingsLine = makeLine('vy');

              return (
                <div className="flex-1 min-h-[220px] mt-1">
                  <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-full" preserveAspectRatio="none">
                    <defs>
                      <linearGradient id="ov_spend" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%"   stopColor="#bfdbfe" stopOpacity="0.85"/>
                        <stop offset="100%" stopColor="#bfdbfe" stopOpacity="0.04"/>
                      </linearGradient>
                      <linearGradient id="ov_savings" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%"   stopColor="#99f6e4" stopOpacity="0.75"/>
                        <stop offset="100%" stopColor="#99f6e4" stopOpacity="0.04"/>
                      </linearGradient>
                    </defs>

                    {/* Horizontal grid lines + Y labels */}
                    {Y_LABELS.map((lbl, i) => {
                      const y = PT + (i / (Y_LABELS.length - 1)) * CH;
                      return (
                        <g key={lbl}>
                          <line x1={PL} y1={y} x2={W - PR} y2={y} stroke="#f3f4f6" strokeWidth="0.8"/>
                          <text x={PL - 5} y={y + 3.5} textAnchor="end" fontSize="9" fill="#9ca3af" fontFamily="monospace">{lbl}</text>
                        </g>
                      );
                    })}

                    {/* Spend area + stroke */}
                    <path d={close(spendLine)}   fill="url(#ov_spend)"/>
                    <path d={spendLine}           fill="none" stroke="#93c5fd" strokeWidth="1.5" strokeLinejoin="round"/>

                    {/* Savings area + stroke */}
                    <path d={close(savingsLine)} fill="url(#ov_savings)"/>
                    <path d={savingsLine}         fill="none" stroke="#5eead4" strokeWidth="1.5" strokeLinejoin="round"/>

                    {/* X axis baseline */}
                    <line x1={PL} y1={baseY} x2={W - PR} y2={baseY} stroke="#e5e7eb" strokeWidth="0.8"/>

                    {/* X labels */}
                    {[0, 7, 14, 21, 28].map((idx, i) => (
                      <text key={i} x={PL + (idx / (n - 1)) * CW} y={H - 7}
                        textAnchor="middle" fontSize="9" fill="#9ca3af" fontFamily="monospace">
                        {X_LABELS[i]}
                      </text>
                    ))}
                  </svg>
                </div>
              );
            })()}
          </div>

          {/* Fleet Composition */}
          <div className="flex-[2] bg-white rounded-xl border border-gray-200 p-5 shadow-sm flex flex-col items-center gap-6">
            <h2 className="text-sm font-semibold text-gray-900 w-full">Fleet Composition</h2>

            {/* Donut */}
            <div className="relative w-36 h-36 flex items-center justify-center">
              <svg className="w-full h-full -rotate-90" viewBox="0 0 36 36">
                <path className="text-gray-200" fill="none" stroke="currentColor" strokeWidth="4"
                  d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" />
                <path className="text-blue-600" fill="none" stroke="currentColor" strokeWidth="4"
                  strokeDasharray="64, 100"
                  d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" />
              </svg>
              <div className="absolute flex flex-col items-center">
                <span className="text-2xl font-bold text-gray-900 font-mono leading-none">64%</span>
                <span className="text-[10px] uppercase tracking-widest text-gray-400 font-semibold mt-1">Spot</span>
              </div>
            </div>

            {/* Gauges */}
            <div className="flex w-full justify-around gap-4">
              {[{ label: 'Avg CPU', pct: 34, dash: 17 }, { label: 'Avg Mem', pct: 51, dash: 25.5 }].map(g => (
                <div key={g.label} className="flex flex-col items-center gap-2">
                  <div className="relative w-20 h-10 overflow-hidden">
                    <svg className="w-full h-full" viewBox="0 0 36 18">
                      <path className="text-gray-200" fill="none" stroke="currentColor" strokeWidth="4"
                        d="M2 18 A 16 16 0 0 1 34 18" />
                      <path className="text-blue-600" fill="none" stroke="currentColor" strokeWidth="4"
                        strokeDasharray={`${g.dash}, 100`}
                        d="M2 18 A 16 16 0 0 1 34 18" />
                    </svg>
                    <span className="absolute bottom-0 w-full text-center text-[13px] font-bold font-mono text-gray-900">{g.pct}%</span>
                  </div>
                  <span className="text-[11px] text-gray-400 font-medium">{g.label}</span>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ── Row 3: Cluster Health Table ── */}
        <section className="w-full bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
          <div className="px-5 py-4 border-b border-gray-100 bg-white flex justify-between items-center">
            <h2 className="text-sm font-semibold text-gray-900">Cluster Health</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-gray-100 text-[10px] uppercase tracking-widest text-gray-400 bg-gray-50">
                  {['Cluster', 'Nodes', 'Spot %', 'CPU Util', 'Mem Util', 'Monthly Spend', 'Status'].map((h, i) => (
                    <th key={h} className={`px-5 py-3 font-semibold ${i > 0 && i < 3 ? 'text-right' : ''}`}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50 font-mono">
                {CLUSTERS.map(c => (
                  <tr key={c.name} className="hover:bg-gray-50 transition-colors">
                    <td className="px-5 py-3.5 font-semibold text-gray-900">{c.name}</td>
                    <td className="px-5 py-3.5 text-right text-gray-700">{c.nodes}</td>
                    <td className="px-5 py-3.5 text-right text-gray-700">{c.spot}%</td>
                    <td className="px-5 py-3.5">
                      <div className="flex items-center gap-2">
                        <div className="w-20 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                          <div className="h-full bg-green-500 rounded-full" style={{ width: `${c.cpu}%` }} />
                        </div>
                        <span className="text-gray-500 text-[11px]">{c.cpu}%</span>
                      </div>
                    </td>
                    <td className="px-5 py-3.5 text-right text-gray-700">{c.mem}%</td>
                    <td className="px-5 py-3.5 text-right text-gray-700">{c.spend}</td>
                    <td className="px-5 py-3.5">
                      <div className="flex items-center gap-2 text-[12px] font-sans">
                        <span className={`w-2 h-2 rounded-full ${c.statusColor}`} />
                        <span className="text-gray-700">{c.status}</span>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {/* ── Row 4: Activity + Cost Drivers ── */}
        <section className="flex flex-col lg:flex-row gap-5">

          {/* Optimization Activity Feed */}
          <div className="flex-1 bg-white rounded-xl border border-gray-200 p-5 shadow-sm flex flex-col">
            <h2 className="text-sm font-semibold text-gray-900 mb-5">Optimization Activity</h2>
            <div className="flex flex-col relative pl-4 border-l border-gray-100 ml-2 gap-5">
              {ACTIVITY.map((a, i) => (
                <div key={i} className="relative">
                  <div className={`absolute -left-[21px] top-1 w-2.5 h-2.5 rounded-full ${a.dot} ring-4 ring-white`} />
                  <div className="flex flex-col">
                    <span className="text-xs text-gray-800 font-medium">{a.title}</span>
                    <span className="text-[11px] text-gray-400 mt-0.5">{a.detail}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Top Cost Drivers */}
          <div className="flex-1 bg-white rounded-xl border border-gray-200 p-5 shadow-sm flex flex-col">
            <div className="flex justify-between items-center mb-5">
              <h2 className="text-sm font-semibold text-gray-900">Top Cost Drivers</h2>
              <div className="flex bg-gray-100 rounded p-0.5 border border-gray-200">
                {['Namespace', 'Workload'].map(v => (
                  <button key={v} onClick={() => setCostView(v)}
                    className={`px-3 py-1 text-[11px] font-medium rounded transition-colors ${costView === v ? 'bg-white shadow-sm text-gray-800' : 'text-gray-500 hover:text-gray-700'}`}>
                    {v}
                  </button>
                ))}
              </div>
            </div>
            <div className="flex flex-col gap-4">
              {COST_DRIVERS.map((d, i) => (
                <div key={d.name} className="flex flex-col gap-1">
                  <div className="flex justify-between text-xs font-mono">
                    <span className="text-gray-800 font-semibold">{d.name}</span>
                    <div className="flex items-center gap-2">
                      <span className="text-gray-400">{d.pct}%</span>
                      <span className="text-gray-800">{d.spend}</span>
                    </div>
                  </div>
                  <div className="w-full bg-gray-100 h-2 rounded-full overflow-hidden">
                    <div className="bg-blue-600 h-full rounded-full" style={{ width: `${d.pct}%`, opacity: 1 - i * 0.15 }} />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ── Row 5: What-If Strip ── */}
        <section className="w-full bg-blue-50 border-l-4 border-blue-600 rounded-xl p-4 flex flex-col md:flex-row items-start md:items-center justify-between gap-4 border border-blue-100">
          <div className="flex items-center gap-3">
            <span className="text-blue-700 text-lg">🧠</span>
            <span className="text-xs font-semibold text-blue-800 tracking-tight">Projected impact if all scheduled optimizations complete</span>
          </div>
          <div className="flex flex-wrap items-center gap-5 font-mono text-xs">
            {[
              { label: 'Spend', from: '$18,420', to: '$12,800', strike: true },
              { label: 'Spot%', from: '64%',     to: '81%',     strike: false },
              { label: 'Nodes', from: '24',       to: '17',      strike: false },
            ].map((item, i) => (
              <React.Fragment key={item.label}>
                {i > 0 && <div className="w-px h-4 bg-blue-300 hidden md:block" />}
                <div className="flex items-center gap-1.5">
                  <span className="text-gray-500">{item.label}</span>
                  <span className={`text-gray-800 ${item.strike ? 'line-through decoration-red-400 decoration-2' : ''}`}>{item.from}</span>
                  <span className="text-gray-400">→</span>
                  <span className="text-green-600 font-bold">{item.to}</span>
                </div>
              </React.Fragment>
            ))}
            <div className="w-px h-4 bg-blue-300 hidden md:block" />
            <div className="flex items-center gap-1.5 bg-white px-2 py-0.5 rounded border border-blue-100 text-[11px] font-sans font-semibold text-gray-700 shadow-sm">
              <span className="w-2 h-2 rounded-full bg-green-500" />
              Low Risk
            </div>
          </div>
        </section>

      </div>
    </div>
  );
}