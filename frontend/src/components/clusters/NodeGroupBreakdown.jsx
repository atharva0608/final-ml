import React, { useEffect, useState } from 'react';
import { Card } from '../shared';
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, Legend } from 'recharts';
import api from '../../services/api';

const NodeGroupBreakdown = ({ clusterId }) => {
    const [data, setData] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const fetchData = async () => {
            try {
                if (!clusterId) return;
                const res = await api.get(`/metrics/cluster/${clusterId}/nodegroups`);
                setData(res.data);
            } catch (err) {
                console.error("Failed to load node groups", err);
            } finally {
                setLoading(false);
            }
        };
        fetchData();
    }, [clusterId]);

    if (loading) return <div className="h-48 bg-gray-50 animate-pulse rounded-lg"></div>;

    // Transform data for stacked bar if needed, or simple bar
    // Data: [{name, instance_type, count, lifecycle}]

    return (
        <Card title="Node Group Breakdown" className="h-full">
            <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                    <BarChart
                        data={data}
                        layout="vertical"
                        margin={{ top: 5, right: 30, left: 40, bottom: 5 }}
                    >
                        <XAxis type="number" />
                        <YAxis type="category" dataKey="name" width={100} tick={{ fontSize: 10 }} />
                        <Tooltip
                            formatter={(value, name, props) => [value, `${props.payload.lifecycle} (${props.payload.instance_type})`]}
                            cursor={{ fill: 'transparent' }}
                        />
                        <Legend />
                        <Bar dataKey="count" name="Node Count" fill="#3B82F6" radius={[0, 4, 4, 0]} barSize={20} />
                    </BarChart>
                </ResponsiveContainer>
            </div>
        </Card>
    );
};

export default NodeGroupBreakdown;
