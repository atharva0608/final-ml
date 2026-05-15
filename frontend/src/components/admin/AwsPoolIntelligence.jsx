import React, { useState, useCallback } from 'react';
import { adminAPI } from '../../services/api';
import { FiRefreshCw, FiAlertTriangle, FiAlertCircle, FiSlash, FiDatabase, FiFilter, FiGlobe } from 'react-icons/fi';

// ── All regions the platform supports ────────────────────────────────────────
const ALL_REGIONS = [
  { id: 'ap-south-1',    label: 'Mumbai',       flag: '🇮🇳' },
  { id: 'ap-southeast-1',label: 'Singapore',    flag: '🇸🇬' },
  { id: 'ap-southeast-2',label: 'Sydney',       flag: '🇦🇺' },
  { id: 'ap-northeast-1',label: 'Tokyo',        flag: '🇯🇵' },
  { id: 'ap-northeast-2',label: 'Seoul',        flag: '🇰🇷' },
  { id: 'us-east-1',     label: 'N. Virginia',  flag: '🇺🇸' },
  { id: 'us-east-2',     label: 'Ohio',         flag: '🇺🇸' },
  { id: 'us-west-1',     label: 'N. California',flag: '🇺🇸' },
  { id: 'us-west-2',     label: 'Oregon',       flag: '🇺🇸' },
  { id: 'eu-west-1',     label: 'Ireland',      flag: '🇮🇪' },
  { id: 'eu-west-2',     label: 'London',       flag: '🇬🇧' },
  { id: 'eu-central-1',  label: 'Frankfurt',    flag: '🇩🇪' },
  { id: 'eu-north-1',    label: 'Stockholm',    flag: '🇸🇪' },
  { id: 'ca-central-1',  label: 'Canada',       flag: '🇨🇦' },
  { id: 'sa-east-1',     label: 'São Paulo',    flag: '🇧🇷' },
];

// ── Severity colours ──────────────────────────────────────────────────────────
const SEV = {
  critical: { bg: '#fef2f2', border: '#fecaca', text: '#dc2626', badge: '#dc2626' },
  high:     { bg: '#fff7ed', border: '#fed7aa', text: '#ea580c', badge: '#ea580c' },
  medium:   { bg: '#fefce8', border: '#fde68a', text: '#ca8a04', badge: '#ca8a04' },
  risky:    { bg: '#fdf4ff', border: '#e9d5ff', text: '#9333ea', badge: '#9333ea' },
};

// ── Small helpers ─────────────────────────────────────────────────────────────
const Bar = ({ value, max, color = '#3b82f6' }) => {
  const pct = max > 0 ? Math.min(100, Math.round((value / max) * 100)) : 0;
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <div style={{ flex: 1, height: 6, background: '#e5e7eb', borderRadius: 3 }}>
        <div style={{ width: `${pct}%`, height: '100%', background: color, borderRadius: 3, transition: 'width 0.4s' }} />
      </div>
      <span style={{ fontSize: 11, color: '#6b7280', minWidth: 32, textAlign: 'right' }}>{pct}%</span>
    </div>
  );
};

const Num = ({ n, color }) => (
  <span style={{ fontWeight: 700, color: color || '#111827' }}>{(n ?? 0).toLocaleString()}</span>
);

const Tag = ({ label, color }) => (
  <span style={{
    display: 'inline-block', padding: '1px 7px', borderRadius: 10,
    fontSize: 11, fontWeight: 600, background: color + '22', color, border: `1px solid ${color}44`,
  }}>{label}</span>
);

// ── Pipeline step row ─────────────────────────────────────────────────────────
const StepRow = ({ step, label, count, maxCount, color, removed }) => (
  <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '7px 0', borderBottom: '1px solid #f3f4f6' }}>
    <div style={{
      width: 22, height: 22, borderRadius: '50%', background: color + '22',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      fontSize: 10, fontWeight: 700, color, flexShrink: 0,
    }}>{step}</div>
    <div style={{ flex: 1, minWidth: 0 }}>
      <div style={{ fontSize: 12, fontWeight: 500, color: '#374151', marginBottom: 3 }}>{label}</div>
      <Bar value={count} max={maxCount} color={color} />
    </div>
    <div style={{ textAlign: 'right', flexShrink: 0 }}>
      <div style={{ fontSize: 13, fontWeight: 700, color: '#111827' }}>{(count ?? 0).toLocaleString()}</div>
      {removed > 0 && (
        <div style={{ fontSize: 10, color: '#ef4444' }}>−{removed.toLocaleString()}</div>
      )}
    </div>
  </div>
);

// ── Single blacklisted pool card ──────────────────────────────────────────────
const PoolBadge = ({ pool, isRisky }) => {
  const sev = isRisky ? SEV.risky : SEV[pool.severity] || SEV.medium;
  const ttlMin = isRisky
    ? Math.round((pool.ttl_remaining_seconds || 0) / 60)
    : Math.round((pool.ttl_remaining_seconds || 0) / 60);
  const ttlLabel = ttlMin < 60
    ? `${ttlMin}m left`
    : `${Math.round(ttlMin / 60)}h left`;

  return (
    <div style={{
      background: sev.bg, border: `1px solid ${sev.border}`,
      borderRadius: 8, padding: '10px 14px', marginBottom: 8,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontFamily: 'monospace', fontSize: 12, fontWeight: 700, color: sev.text }}>
            {pool.instance_type}
          </span>
          <span style={{ fontSize: 11, color: '#6b7280' }}>{pool.az}</span>
        </div>
        <div style={{ display: 'flex', gap: 5 }}>
          {!isRisky && pool.backoff && <Tag label="backoff" color={sev.badge} />}
          <Tag label={isRisky ? 'short-risk' : pool.severity} color={sev.badge} />
        </div>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, fontSize: 11, color: '#6b7280' }}>
        <span>Reason: <strong style={{ color: sev.text }}>{pool.reason || 'itn_flag'}</strong></span>
        {!isRisky && <span>Failures: <strong>{pool.failure_count}</strong></span>}
        {!isRisky && <span>TTL: {pool.ttl_hours != null ? `${pool.ttl_hours}h` : '—'}</span>}
        <span style={{ marginLeft: 'auto', color: ttlMin < 10 ? '#ef4444' : '#6b7280' }}>{ttlLabel}</span>
      </div>
    </div>
  );
};

// ── Single region card ────────────────────────────────────────────────────────
const RegionCard = ({ data }) => {
  const [tab, setTab] = useState('pipeline'); // 'pipeline' | 'blacklist' | 'risky'
  const p = data.pipeline;
  const problemPools = data.blacklisted_count + data.risky_count;

  return (
    <div style={{
      background: '#fff', border: '1px solid #e5e7eb', borderRadius: 12,
      overflow: 'hidden', boxShadow: '0 1px 4px rgba(0,0,0,0.06)',
    }}>
      {/* Header */}
      <div style={{ padding: '14px 18px', borderBottom: '1px solid #f3f4f6', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <div style={{ fontSize: 14, fontWeight: 700, color: '#111827' }}>{data.display_name}</div>
          <div style={{ fontSize: 11, color: '#9ca3af', marginTop: 2 }}>
            {p.cache_age_minutes != null
              ? `Cache ${p.cache_age_minutes}min old  ·  ${p.in_global_cache.toLocaleString()} cached`
              : 'No cache yet'}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {problemPools > 0 && (
            <span style={{ background: '#fef2f2', color: '#dc2626', border: '1px solid #fecaca', borderRadius: 20, padding: '2px 10px', fontSize: 11, fontWeight: 700 }}>
              ⚠ {problemPools} issues
            </span>
          )}
          <span style={{ background: '#eff6ff', color: '#2563eb', border: '1px solid #bfdbfe', borderRadius: 20, padding: '2px 10px', fontSize: 11, fontWeight: 600 }}>
            {p.in_global_cache.toLocaleString()} / {p.cache_limit.toLocaleString()} cached
          </span>
        </div>
      </div>

      {/* Tab bar */}
      <div style={{ display: 'flex', borderBottom: '1px solid #f3f4f6', background: '#f9fafb' }}>
        {[
          { key: 'pipeline', icon: FiFilter, label: 'Pipeline' },
          { key: 'blacklist', icon: FiSlash, label: `Blacklisted (${data.blacklisted_count})` },
          { key: 'risky', icon: FiAlertTriangle, label: `Short-risk (${data.risky_count})` },
        ].map(t => (
          <button key={t.key} onClick={() => setTab(t.key)} style={{
            display: 'flex', alignItems: 'center', gap: 5, padding: '8px 14px',
            fontSize: 12, fontWeight: tab === t.key ? 700 : 400,
            color: tab === t.key ? '#2563eb' : '#6b7280',
            borderBottom: tab === t.key ? '2px solid #2563eb' : '2px solid transparent',
            background: 'transparent', border: 'none', cursor: 'pointer',
          }}>
            <t.icon size={12} />
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div style={{ padding: '14px 18px' }}>
        {tab === 'pipeline' && (
          <div>
            <StepRow step="S0" label="Instance Catalog Types" count={p.catalog_types} maxCount={p.catalog_types} color="#6366f1" />
            <StepRow step="S1" label={`Raw Candidates  (${p.catalog_types} types × ${p.azs} AZs)`} count={p.raw_candidates} maxCount={p.raw_candidates} color="#3b82f6" />
            <StepRow step="S3" label="After Spot Advisor  (annotation only — no pools removed)" count={p.after_spot_advisor} maxCount={p.raw_candidates} color="#06b6d4" />
            <StepRow step="S4" label="After Blacklist pre-filter  (failure_count ≥ 3)" count={p.after_blacklist} maxCount={p.raw_candidates} color="#10b981" removed={p.after_blacklist_removed} />
            <StepRow step="S7" label={`Global Cache  (top ${p.cache_limit.toLocaleString()} by ML score)`} count={p.in_global_cache} maxCount={p.raw_candidates} color="#8b5cf6" />
            <StepRow step="C1" label="After typical client filter  (amd64 · 2-64 vCPU · 4-256 GB)" count={p.typical_after_client_filter} maxCount={p.raw_candidates} color="#f59e0b" removed={p.client_filter_removed} />
            {/* Summary note */}
            <div style={{ marginTop: 10, padding: '8px 12px', background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: 8, fontSize: 11, color: '#15803d' }}>
              💡 Client-specific filters (arch, vCPU, memory, AZ restrictions, excluded types) apply on top of S7 cache — each cluster gets a tailored subset.
              Common pools counted once; client-only exclusions are not listed here.
            </div>
          </div>
        )}

        {tab === 'blacklist' && (
          <div>
            {data.blacklisted_pools.length === 0 ? (
              <div style={{ textAlign: 'center', padding: 24, color: '#9ca3af', fontSize: 13 }}>
                ✅ No blacklisted pools in this region
              </div>
            ) : (
              <>
                <div style={{ fontSize: 11, color: '#6b7280', marginBottom: 10 }}>
                  {data.blacklisted_pools.length} pool{data.blacklisted_pools.length > 1 ? 's' : ''} flagged via risky_pools:{data.region} — sorted by severity
                </div>
                {data.blacklisted_pools.map((pool, i) => (
                  <PoolBadge key={i} pool={pool} isRisky={false} />
                ))}
              </>
            )}
          </div>
        )}

        {tab === 'risky' && (
          <div>
            {data.risky_pools.length === 0 ? (
              <div style={{ textAlign: 'center', padding: 24, color: '#9ca3af', fontSize: 13 }}>
                ✅ No short-lived risk flags in this region
              </div>
            ) : (
              <>
                <div style={{ fontSize: 11, color: '#6b7280', marginBottom: 10 }}>
                  {data.risky_pools.length} RISK:* flag{data.risky_pools.length > 1 ? 's' : ''} — expire within 30 min of last interruption
                </div>
                {data.risky_pools.map((pool, i) => (
                  <PoolBadge key={i} pool={{ ...pool, reason: 'itn_flag', severity: 'high' }} isRisky={true} />
                ))}
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

// ── Main component ────────────────────────────────────────────────────────────
export default function AwsPoolIntelligence() {
  const [enabledRegions, setEnabledRegions] = useState(['ap-south-1', 'us-east-1']);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [lastFetched, setLastFetched] = useState(null);

  const toggleRegion = (id) => {
    setEnabledRegions(prev =>
      prev.includes(id) ? prev.filter(r => r !== id) : [...prev, id]
    );
  };

  const fetchData = useCallback(async () => {
    if (enabledRegions.length === 0) return;
    setLoading(true);
    setError(null);
    try {
      const res = await adminAPI.getAwsPoolData(enabledRegions);
      setData(res.data);
      setLastFetched(new Date());
    } catch (e) {
      setError(e.response?.data?.detail || e.message || 'Failed to fetch pool data');
    } finally {
      setLoading(false);
    }
  }, [enabledRegions]);

  const totalIssues = data?.regions?.reduce((s, r) => s + r.blacklisted_count + r.risky_count, 0) ?? 0;

  return (
    <div style={{ background: '#f9fafb', borderRadius: 14, padding: 24, border: '1px solid #e5e7eb' }}>
      {/* Section header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 20 }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{ width: 32, height: 32, background: '#eff6ff', borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <FiGlobe size={16} color="#2563eb" />
            </div>
            <h2 style={{ fontSize: 16, fontWeight: 700, color: '#111827', margin: 0 }}>AWS Pool Intelligence</h2>
            {totalIssues > 0 && (
              <span style={{ background: '#fee2e2', color: '#dc2626', borderRadius: 20, padding: '2px 10px', fontSize: 11, fontWeight: 700 }}>
                {totalIssues} issues
              </span>
            )}
          </div>
          <p style={{ fontSize: 12, color: '#6b7280', marginTop: 4, marginLeft: 42 }}>
            Pool pipeline counts at each step, capacity issues, and blacklisted / short-risk pools per region.
          </p>
        </div>
        <button
          onClick={fetchData}
          disabled={loading || enabledRegions.length === 0}
          style={{
            display: 'flex', alignItems: 'center', gap: 6, padding: '8px 16px',
            background: loading ? '#e5e7eb' : '#2563eb', color: loading ? '#9ca3af' : '#fff',
            border: 'none', borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: loading ? 'not-allowed' : 'pointer',
          }}
        >
          <FiRefreshCw size={13} style={{ animation: loading ? 'spin 1s linear infinite' : 'none' }} />
          {loading ? 'Fetching...' : 'Fetch Data'}
        </button>
      </div>

      {/* Region toggles */}
      <div style={{ marginBottom: 20 }}>
        <div style={{ fontSize: 12, fontWeight: 600, color: '#374151', marginBottom: 10 }}>
          AWS Regions  <span style={{ fontWeight: 400, color: '#9ca3af' }}>— toggle ON to include</span>
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {ALL_REGIONS.map(r => {
            const on = enabledRegions.includes(r.id);
            return (
              <button key={r.id} onClick={() => toggleRegion(r.id)} style={{
                display: 'flex', alignItems: 'center', gap: 5,
                padding: '5px 12px', borderRadius: 20,
                background: on ? '#eff6ff' : '#f3f4f6',
                border: `1.5px solid ${on ? '#93c5fd' : '#e5e7eb'}`,
                color: on ? '#1d4ed8' : '#6b7280',
                fontSize: 12, fontWeight: on ? 600 : 400, cursor: 'pointer',
                transition: 'all 0.15s',
              }}>
                {/* toggle pill */}
                <span style={{
                  width: 26, height: 14, borderRadius: 7, background: on ? '#3b82f6' : '#d1d5db',
                  display: 'inline-flex', alignItems: 'center', flexShrink: 0,
                  padding: '0 2px', transition: 'background 0.15s',
                }}>
                  <span style={{
                    width: 10, height: 10, borderRadius: '50%', background: '#fff',
                    display: 'block', marginLeft: on ? 'auto' : 0, transition: 'margin 0.15s',
                  }} />
                </span>
                {r.flag} {r.label}
                <span style={{ fontSize: 10, color: '#9ca3af' }}>{r.id}</span>
              </button>
            );
          })}
        </div>
        <div style={{ fontSize: 11, color: '#9ca3af', marginTop: 6 }}>
          {enabledRegions.length} region{enabledRegions.length !== 1 ? 's' : ''} selected
        </div>
      </div>

      {/* Error */}
      {error && (
        <div style={{ background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 8, padding: '10px 14px', marginBottom: 16, display: 'flex', alignItems: 'center', gap: 8 }}>
          <FiAlertCircle color="#dc2626" size={14} />
          <span style={{ fontSize: 12, color: '#dc2626' }}>{error}</span>
        </div>
      )}

      {/* Last fetched */}
      {lastFetched && !loading && (
        <div style={{ fontSize: 11, color: '#9ca3af', marginBottom: 12 }}>
          Last fetched: {lastFetched.toLocaleTimeString()}  ·  {data?.fetched_at?.replace('T', ' ').replace('Z', '') + ' UTC' || ''}
        </div>
      )}

      {/* No data yet */}
      {!data && !loading && !error && (
        <div style={{ textAlign: 'center', padding: 40, color: '#9ca3af' }}>
          <FiDatabase size={28} style={{ margin: '0 auto 10px', display: 'block' }} />
          <div style={{ fontSize: 13 }}>Select regions and click <strong>Fetch Data</strong></div>
        </div>
      )}

      {/* Region cards */}
      {data && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(400px, 1fr))', gap: 16 }}>
          {data.regions.map(r => (
            <RegionCard key={r.region} data={r} />
          ))}
        </div>
      )}

      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
      `}</style>
    </div>
  );
}
