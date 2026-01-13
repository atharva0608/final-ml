from pydantic import BaseModel, Field
from typing import List, Optional, Any, Dict
from datetime import datetime

class TimeSeriesPoint(BaseModel):
    timestamp: datetime
    value: float

class TimeSeriesData(BaseModel):
    """Time series data for charts"""
    metric_name: str = ""
    data_points: List[TimeSeriesPoint] = []
    unit: str = ""
    # Legacy compatibility
    points: Optional[List[TimeSeriesPoint]] = None
    label: Optional[str] = None

class DashboardKPIs(BaseModel):
    """Dashboard key performance indicators"""
    total_instances: int = 0
    active_instances: int = 0
    spot_instances: int = 0
    on_demand_instances: int = 0
    total_cost: float = 0.0
    estimated_savings: float = 0.0
    savings_percentage: float = 0.0
    total_optimizations: int = 0
    successful_optimizations: int = 0
    optimization_rate: Optional[float] = None
    time_range_start: Optional[datetime] = None
    time_range_end: Optional[datetime] = None

class CostMetrics(BaseModel):
    """Cost breakdown metrics"""
    total_cost: float = 0.0
    spot_cost: float = 0.0
    on_demand_cost: float = 0.0
    currency: str = "USD"

class InstanceMetrics(BaseModel):
    """Aggregate instance metrics for dashboard"""
    total_instances: int = 0
    running_instances: int = 0
    pending_instances: int = 0
    stopping_instances: int = 0
    stopped_instances: int = 0
    terminated_instances: int = 0
    spot_instances: int = 0
    on_demand_instances: int = 0
    amd64_instances: int = 0
    arm64_instances: int = 0

class SavingsBreakdown(BaseModel):
    """Savings breakdown metrics"""
    total_savings: float = 0.0
    spot_savings: float = 0.0
    hibernation_savings: float = 0.0
    savings_percentage: float = 0.0

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
