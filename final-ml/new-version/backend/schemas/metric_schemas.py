from pydantic import BaseModel, Field
from typing import List, Optional, Any, Dict
from datetime import datetime

class TimeSeriesPoint(BaseModel):
    timestamp: datetime
    value: float

class TimeSeriesData(BaseModel):
    points: List[TimeSeriesPoint]
    label: str

class DashboardKPIs(BaseModel):
    total_savings: float
    spot_percentage: float
    cluster_health: float
    active_clusters: int

class CostMetrics(BaseModel):
    on_demand_cost: float
    spot_cost: float
    savings: float

class InstanceMetrics(BaseModel):
    instance_id: str
    cpu_util: float
    memory_util: float

class SavingsBreakdown(BaseModel):
    total: float
    by_category: Dict[str, float]

class ClusterMetrics(BaseModel):
    cluster_id: str
    cpu_utilization: float
    memory_utilization: float
    node_count: int
    spot_ratio: float

class MetricFilter(BaseModel):
    cluster_id: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None

# Aliases for dashboard
class KPISet(DashboardKPIs): pass
class ChartDataPoint(TimeSeriesPoint): pass
class MultiSeriesChartData(BaseModel):
    series: List[TimeSeriesData]
    timestamps: List[datetime]

# Compatibility aliases
class ChartData(TimeSeriesData): pass

class PieChartSlice(BaseModel):
    label: str
    value: float
    color: Optional[str] = None

class PieChartData(BaseModel):
    slices: List[PieChartSlice]

class PieData(PieChartData): pass

class ActivityFeedItem(BaseModel):
    id: str
    timestamp: datetime
    event_type: str
    message: str
    severity: str = "info"
    metadata: Dict[str, Any] = {}

class ActivityFeed(BaseModel):
    items: List[ActivityFeedItem]
    total: int

class CostBreakdown(CostMetrics):
    potential_savings: float

class DashboardMetrics(BaseModel):
    kpis: DashboardKPIs
    cost_history: MultiSeriesChartData
    cluster_distribution: PieChartData
    recent_activity: List[ActivityFeedItem]
