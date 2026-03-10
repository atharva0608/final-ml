import React, { useState, useEffect } from 'react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import { multiClusterAPI } from '../../../services/api';

const C = {
    bg: "#f8f9fb",
    surface: "#ffffff",
    border: "#e8eaed",
    text: "#0f1117",
    muted: "#6b7280",
    subtle: "#9ca3af",
    green: "#059669",
    greenLight: "#ecfdf5",
    blue: "#2563eb",
    purple: "#7c3aed"
};

export default function TrendsChart({ widgetKey }) {
    const [data, setData] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        multiClusterAPI.getTrends(30)
            .then(res => {
                // Format dates
                const formatted = (res.data.trends || []).map(d => ({
                    ...d,
                    formattedDate: new Date(d.date).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
                }));
                setData(formatted);
            })
            .catch(err => console.error("Failed to fetch trends", err))
            .finally(() => setLoading(false));
    }, []);

    if (loading) {
        return (
            <div style={{
                background: C.surface, border: `1px solid ${C.border}`, borderRadius: 12, padding: "20px",
                height: 300, display: "flex", alignItems: "center", justifyContent: "center", color: C.subtle, fontSize: 13
            }}>
                Loading Fleet Trends...
            </div>
        );
    }

    if (data.length === 0) {
        return (
            <div style={{
                background: C.surface, border: `1px solid ${C.border}`, borderRadius: 12, padding: "20px",
                height: 300, display: "flex", alignItems: "center", justifyContent: "center", color: C.subtle, fontSize: 13
            }}>
                No trend data available for the last 30 days.
            </div>
        );
    }

    return (
        <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 12, padding: "20px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
                <div>
                    <h3 style={{ margin: 0, fontSize: 14, fontWeight: 700, color: C.text }}>Fleet Optimization Trends</h3>
                    <p style={{ margin: "4px 0 0", fontSize: 12, color: C.muted }}>30-day savings & Spot ratio evolution across all clusters</p>
                </div>
            </div>

            <div style={{ height: 260 }}>
                <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={data} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                        <defs>
                            <linearGradient id="colorSavings" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="5%" stopColor={C.green} stopOpacity={0.3} />
                                <stop offset="95%" stopColor={C.green} stopOpacity={0} />
                            </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={C.border} />
                        <XAxis dataKey="formattedDate" axisLine={false} tickLine={false} tick={{ fontSize: 11, fill: C.subtle }} dy={10} />
                        <YAxis yAxisId="left" axisLine={false} tickLine={false} tick={{ fontSize: 11, fill: C.subtle }} tickFormatter={(val) => `$${val}`} />
                        <YAxis yAxisId="right" orientation="right" axisLine={false} tickLine={false} tick={{ fontSize: 11, fill: C.subtle }} tickFormatter={(val) => `${val}%`} />
                        <Tooltip
                            contentStyle={{ borderRadius: 8, border: `1px solid ${C.border}`, boxShadow: "0 4px 12px rgba(0,0,0,0.05)", fontSize: 12 }}
                            formatter={(value, name) => {
                                if (name === "Savings") return [`$${value.toFixed(2)}`, name];
                                if (name === "Spot Ratio") return [`${value.toFixed(1)}%`, name];
                                return [value, name];
                            }}
                        />
                        <Legend iconType="circle" wrapperStyle={{ fontSize: 12, paddingTop: 10 }} />
                        <Area yAxisId="left" type="monotone" name="Savings" dataKey="savings" stroke={C.green} strokeWidth={2} fillOpacity={1} fill="url(#colorSavings)" />
                        <Area yAxisId="right" type="monotone" name="Spot Ratio" dataKey="spot_ratio_pct" stroke={C.purple} strokeWidth={2} fill="none" />
                    </AreaChart>
                </ResponsiveContainer>
            </div>
        </div>
    );
}
