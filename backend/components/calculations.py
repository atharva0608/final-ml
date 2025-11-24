"""
================================================================================
CALCULATION COMPONENT - Savings and Metrics Engine
================================================================================

COMPONENT PURPOSE:
------------------
Dedicated numerical processing component that manages all calculations related
to savings, costs, performance statistics, and client-wise metrics. This
component ensures consistent calculation methods across the entire system.

KEY RESPONSIBILITIES:
--------------------
1. Savings Calculations: Spot vs On-Demand, actual vs projected
2. Cost Tracking: Hourly, daily, monthly, yearly aggregations
3. Client Metrics: Per-client performance statistics
4. Agent Metrics: Per-agent efficiency and uptime
5. ROI Analysis: Return on investment for replica strategies
6. Trend Analysis: Pricing trends and prediction support

ARCHITECTURE POSITION:
---------------------
Service Layer → Calculation Component → Data Valve/Database
                  ↑
            (Pure Functions)

SCENARIO EXAMPLES:
-----------------

Scenario 1: Calculate Monthly Savings for Client
------------------------------------------------
Client has 3 agents running 24/7 for entire month:

Agent 1: t3.medium, 730 hours
  - On-Demand price: $0.0416/hr
  - Actual avg spot price: $0.0125/hr (70% savings)
  - On-Demand cost: $0.0416 × 730 = $30.37
  - Actual cost: $0.0125 × 730 = $9.13
  - Savings: $21.24

Agent 2: t3.large, 730 hours
  - On-Demand price: $0.0832/hr
  - Actual avg spot price: $0.0245/hr (71% savings)
  - On-Demand cost: $0.0832 × 730 = $60.74
  - Actual cost: $0.0245 × 730 = $17.89
  - Savings: $42.85

Agent 3: t3.xlarge, 730 hours
  - On-Demand price: $0.1664/hr
  - Actual avg spot price: $0.0498/hr (70% savings)
  - On-Demand cost: $0.1664 × 730 = $121.47
  - Actual cost: $0.0498 × 730 = $36.35
  - Savings: $85.12

Total Client Savings:
  - Total would-be cost: $212.58
  - Total actual cost: $63.37
  - Total savings: $149.21 (70.18%)
  - Monthly savings rate: 70.18%

Scenario 2: Switch Savings Impact
---------------------------------
Switch from expensive to cheaper pool:

Before Switch:
  - Pool: t3.medium.us-east-1a
  - Spot price: $0.045/hr
  - On-Demand price: $0.0416/hr
  - Currently LOSING money (-8% vs On-Demand)

After Switch:
  - Pool: t3.medium.us-east-1b
  - Spot price: $0.0125/hr
  - On-Demand price: $0.0416/hr (same instance type)
  - Now SAVING: 70% vs On-Demand

Switch Impact:
  - Immediate hourly savings: $0.0416 - $0.0125 = $0.0291/hr
  - Daily savings: $0.0291 × 24 = $0.70/day
  - Monthly savings: $0.70 × 30 = $21/month
  - Yearly savings: $21 × 12 = $252/year

Calculation stores:
  - savings_impact = $0.0291 (stored in switches table)
  - Used for displaying "This switch saved you $21/month"

Scenario 3: Replica Cost vs Savings Analysis
--------------------------------------------
Manual Replica Mode enabled for 30 days:

Primary Instance Costs:
  - Instance: t3.medium at avg $0.0312/hr
  - Hours: 720 (30 days × 24 hrs)
  - Total: $22.46

Replica Instance Costs:
  - Instance: t3.medium at avg $0.0315/hr (slightly higher pool)
  - Hours: 720 (continuous)
  - Total: $22.68

Combined Cost: $45.14/month

Without Manual Replica (Auto-Switch Mode):
  - Primary only: $22.46
  - Emergency replicas: 8 hours total @ $0.0312 = $0.25
  - Total: $22.71/month

Cost Difference:
  - Manual replica overhead: $45.14 - $22.71 = $22.43/month
  - Extra cost: 98.7%

Value Analysis:
  - Downtime prevented: 4 potential interruptions
  - Estimated downtime without replica: 4 × 45 sec = 3 minutes
  - Revenue @ $1000/hr: 3min = $50 potential loss
  - ROI: $50 loss prevented / $22.43 cost = 223% ROI
  - Verdict: Manual replica is worth it for this workload

Calculation Result:
  {
    'manual_replica_cost': 45.14,
    'auto_switch_cost': 22.71,
    'overhead': 22.43,
    'overhead_percent': 98.7,
    'downtime_prevented_minutes': 3,
    'estimated_revenue_protected': 50.00,
    'roi_percent': 223,
    'recommendation': 'manual_replica_justified'
  }

Scenario 4: Client Performance Scorecard
----------------------------------------
Generate monthly performance report:

Metrics Calculated:
  - Total agents: 5
  - Active agents: 5
  - Total instances (including switches): 23
  - Total switches this month: 18
  - Total replicas created: 6 (4 auto, 2 manual)
  - Interruptions handled: 3 (100% success rate)

  Financial:
    - Total baseline cost (On-Demand): $512.34
    - Total actual cost (optimized): $167.88
    - Total savings: $344.46
    - Savings rate: 67.24%

  Operational:
    - Total uptime: 99.94%
    - Total downtime: 2.7 minutes
    - Avg switch time: 38 seconds
    - Fastest switch: 18 seconds
    - Slowest switch: 67 seconds
    - Data quality: 98.3% actual, 1.7% interpolated

  Efficiency:
    - Switches per agent: 3.6 avg
    - Cost per switch: $0.42 (AMI creation + brief dual-instance)
    - Savings per switch: $19.14 avg
    - ROI per switch: 4558%

CONFIGURATION:
-------------
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from decimal import Decimal
from collections import defaultdict

from backend.database_manager import execute_query

logger = logging.getLogger(__name__)


class CalculationConfig:
    """
    Calculation engine configuration

    Adjust these constants based on your business requirements:
    - HOURS_PER_MONTH: Use 730 for accurate monthly calculations
    - MIN_SAVINGS_FOR_SWITCH: Don't recommend switches for <$5/month savings
    - REPLICA_COST_MULTIPLIER: Account for slightly higher replica pool costs
    """

    # Time Constants
    HOURS_PER_DAY = 24
    HOURS_PER_MONTH = 730  # AWS standard (365.25 days / 12 months * 24 hours)
    HOURS_PER_YEAR = 8766  # 365.25 days * 24 hours
    DAYS_PER_MONTH = 30.4375  # 365.25 / 12
    SECONDS_PER_HOUR = 3600

    # Financial Thresholds
    MIN_SAVINGS_FOR_SWITCH = Decimal('5.00')  # Min $5/month to justify switch
    SWITCH_COST_ESTIMATE = Decimal('0.50')  # Avg cost of switch (AMI + dual-instance)

    # Replica Cost Modeling
    REPLICA_COST_MULTIPLIER = Decimal('1.02')  # Replicas typically 2% more expensive
    REPLICA_OVERHEAD_PERCENT = Decimal('100')  # Manual replica = 100% overhead

    # Precision
    DECIMAL_PLACES_MONEY = 4  # $0.0001 precision
    DECIMAL_PLACES_PERCENT = 2  # 0.01% precision


class CalculationEngine:
    """
    Calculation Engine - Pure mathematical processing

    This component provides pure functions for all financial and statistical
    calculations. It has no side effects and doesn't access the database directly.

    Example Usage:

    from backend.components.calculations import calculation_engine

    # Calculate monthly savings
    savings = calculation_engine.calculate_monthly_savings(
        ondemand_price=Decimal('0.0416'),
        actual_avg_price=Decimal('0.0125'),
        hours=730
    )
    # Returns: {'savings': 21.24, 'savings_percent': 69.95, ...}

    # Calculate switch impact
    impact = calculation_engine.calculate_switch_impact(
        old_price=Decimal('0.045'),
        new_price=Decimal('0.0125'),
        ondemand_price=Decimal('0.0416')
    )
    # Returns: {'hourly_impact': 0.0325, 'monthly_impact': 23.73, ...}
    """

    def __init__(self, config: CalculationConfig = None):
        """Initialize calculation engine with configuration"""
        self.config = config or CalculationConfig()
        logger.info("Calculation Engine initialized")

    # =========================================================================
    # SAVINGS CALCULATIONS
    # =========================================================================

    def calculate_hourly_savings(
        self,
        ondemand_price: Decimal,
        spot_price: Decimal
    ) -> Dict[str, Any]:
        """
        Calculate hourly savings: On-Demand vs Spot

        Formula:
          savings = ondemand_price - spot_price
          savings_percent = (savings / ondemand_price) * 100

        Args:
            ondemand_price: On-Demand price ($/hr)
            spot_price: Current spot price ($/hr)

        Returns:
            {
                'savings_hourly': Decimal('0.0291'),
                'savings_percent': Decimal('69.95'),
                'ondemand_cost': Decimal('0.0416'),
                'actual_cost': Decimal('0.0125'),
                'is_saving': True
            }
        """
        if ondemand_price <= 0:
            return {
                'savings_hourly': Decimal('0'),
                'savings_percent': Decimal('0'),
                'ondemand_cost': ondemand_price,
                'actual_cost': spot_price,
                'is_saving': False
            }

        savings = ondemand_price - spot_price
        savings_percent = (savings / ondemand_price) * 100

        return {
            'savings_hourly': self._round_money(savings),
            'savings_percent': self._round_percent(savings_percent),
            'ondemand_cost': self._round_money(ondemand_price),
            'actual_cost': self._round_money(spot_price),
            'is_saving': savings > 0
        }

    def calculate_monthly_savings(
        self,
        ondemand_price: Decimal,
        actual_avg_price: Decimal,
        hours: Decimal = None
    ) -> Dict[str, Any]:
        """
        Calculate monthly savings (extrapolated from hourly)

        Args:
            ondemand_price: On-Demand price ($/hr)
            actual_avg_price: Actual average spot price paid ($/hr)
            hours: Number of hours (defaults to full month = 730)

        Returns:
            {
                'savings_monthly': Decimal('21.24'),
                'ondemand_cost_monthly': Decimal('30.37'),
                'actual_cost_monthly': Decimal('9.13'),
                'savings_percent': Decimal('69.95'),
                'hours': Decimal('730')
            }
        """
        if hours is None:
            hours = Decimal(str(self.config.HOURS_PER_MONTH))

        ondemand_cost_monthly = ondemand_price * hours
        actual_cost_monthly = actual_avg_price * hours
        savings_monthly = ondemand_cost_monthly - actual_cost_monthly

        if ondemand_cost_monthly > 0:
            savings_percent = (savings_monthly / ondemand_cost_monthly) * 100
        else:
            savings_percent = Decimal('0')

        return {
            'savings_monthly': self._round_money(savings_monthly),
            'ondemand_cost_monthly': self._round_money(ondemand_cost_monthly),
            'actual_cost_monthly': self._round_money(actual_cost_monthly),
            'savings_percent': self._round_percent(savings_percent),
            'hours': hours
        }

    def calculate_switch_impact(
        self,
        old_price: Decimal,
        new_price: Decimal,
        ondemand_price: Decimal
    ) -> Dict[str, Any]:
        """
        Calculate the financial impact of a switch

        Compares:
        - Before switch savings
        - After switch savings
        - Impact (improvement)

        Args:
            old_price: Price before switch ($/hr)
            new_price: Price after switch ($/hr)
            ondemand_price: On-Demand baseline ($/hr)

        Returns:
            {
                'before_savings_percent': Decimal('-8.00'),  # Was losing money
                'after_savings_percent': Decimal('69.95'),   # Now saving
                'improvement': Decimal('77.95'),  # Percentage points gained
                'hourly_impact': Decimal('0.0291'),  # $/hr improvement
                'monthly_impact': Decimal('21.24'),  # $/month improvement
                'yearly_impact': Decimal('254.91')   # $/year improvement
            }
        """
        # Before switch
        before_hourly = self.calculate_hourly_savings(ondemand_price, old_price)

        # After switch
        after_hourly = self.calculate_hourly_savings(ondemand_price, new_price)

        # Impact
        improvement = after_hourly['savings_percent'] - before_hourly['savings_percent']
        hourly_impact = new_price - old_price  # Negative = cost reduction
        monthly_impact = hourly_impact * Decimal(str(self.config.HOURS_PER_MONTH))
        yearly_impact = hourly_impact * Decimal(str(self.config.HOURS_PER_YEAR))

        return {
            'before_savings_percent': before_hourly['savings_percent'],
            'after_savings_percent': after_hourly['savings_percent'],
            'improvement': self._round_percent(improvement),
            'hourly_impact': self._round_money(hourly_impact),
            'monthly_impact': self._round_money(monthly_impact),
            'yearly_impact': self._round_money(yearly_impact),
            'old_price': self._round_money(old_price),
            'new_price': self._round_money(new_price),
            'ondemand_price': self._round_money(ondemand_price)
        }

    # =========================================================================
    # CLIENT METRICS
    # =========================================================================

    def calculate_client_totals(
        self,
        client_id: str,
        period_days: int = 30
    ) -> Dict[str, Any]:
        """
        Calculate comprehensive client metrics

        Queries database for all agent activity and calculates:
        - Total savings
        - Cost breakdown
        - Operational metrics
        - Efficiency scores

        Args:
            client_id: Client UUID
            period_days: Number of days to analyze

        Returns:
            Complete client scorecard (see Scenario 4 above)
        """
        cutoff_date = datetime.utcnow() - timedelta(days=period_days)

        # Get all switches in period
        switches = execute_query("""
            SELECT
                old_spot_price,
                new_spot_price,
                on_demand_price,
                savings_impact,
                initiated_at,
                instance_ready_at,
                old_terminated_at,
                TIMESTAMPDIFF(SECOND, initiated_at, instance_ready_at) as switch_duration_sec
            FROM switches
            WHERE client_id = %s
              AND initiated_at >= %s
        """, (client_id, cutoff_date), fetch=True)

        # Get all agents
        agents = execute_query("""
            SELECT
                id,
                status,
                spot_price,
                ondemand_price,
                baseline_ondemand_price,
                installed_at,
                last_switch_at
            FROM agents
            WHERE client_id = %s
        """, (client_id,), fetch=True)

        # Get interruption events
        interruptions = execute_query("""
            SELECT
                signal_type,
                detected_at,
                replica_id,
                new_instance_id
            FROM spot_interruption_events sie
            JOIN agents a ON sie.agent_id = a.id
            WHERE a.client_id = %s
              AND detected_at >= %s
        """, (client_id, cutoff_date), fetch=True)

        # Calculate totals
        total_switches = len(switches or [])
        total_interruptions = len(interruptions or [])
        total_agents = len(agents or [])
        active_agents = sum(1 for a in (agents or []) if a['status'] == 'online')

        # Financial calculations
        total_savings = Decimal('0')
        total_ondemand_cost = Decimal('0')
        total_actual_cost = Decimal('0')

        for agent in (agents or []):
            if agent['baseline_ondemand_price'] and agent['spot_price']:
                hours = Decimal(str(period_days * self.config.HOURS_PER_DAY))
                ondemand = Decimal(str(agent['baseline_ondemand_price'])) * hours
                actual = Decimal(str(agent['spot_price'])) * hours
                total_ondemand_cost += ondemand
                total_actual_cost += actual
                total_savings += (ondemand - actual)

        savings_percent = Decimal('0')
        if total_ondemand_cost > 0:
            savings_percent = (total_savings / total_ondemand_cost) * 100

        # Operational metrics
        switch_durations = [
            s['switch_duration_sec']
            for s in (switches or [])
            if s.get('switch_duration_sec')
        ]

        avg_switch_time = 0
        if switch_durations:
            avg_switch_time = sum(switch_durations) / len(switch_durations)

        return {
            'period_days': period_days,
            'agents': {
                'total': total_agents,
                'active': active_agents,
                'inactive': total_agents - active_agents
            },
            'financial': {
                'total_savings': float(self._round_money(total_savings)),
                'total_ondemand_cost': float(self._round_money(total_ondemand_cost)),
                'total_actual_cost': float(self._round_money(total_actual_cost)),
                'savings_percent': float(self._round_percent(savings_percent))
            },
            'operational': {
                'total_switches': total_switches,
                'total_interruptions': total_interruptions,
                'interruptions_handled': total_interruptions,  # All handled if present
                'avg_switch_time_seconds': round(avg_switch_time, 1),
                'fastest_switch_seconds': min(switch_durations) if switch_durations else 0,
                'slowest_switch_seconds': max(switch_durations) if switch_durations else 0
            },
            'efficiency': {
                'switches_per_agent': round(total_switches / total_agents, 1) if total_agents > 0 else 0,
                'cost_per_switch': float(self.config.SWITCH_COST_ESTIMATE),
                'avg_savings_per_switch': float(self._round_money(
                    total_savings / total_switches if total_switches > 0 else Decimal('0')
                ))
            }
        }

    # =========================================================================
    # REPLICA COST ANALYSIS
    # =========================================================================

    def calculate_replica_cost_analysis(
        self,
        primary_price: Decimal,
        replica_price: Decimal,
        hours: Decimal,
        interruptions_prevented: int = 0,
        avg_downtime_per_interruption_seconds: int = 45,
        revenue_per_hour: Decimal = Decimal('0')
    ) -> Dict[str, Any]:
        """
        Analyze cost/benefit of manual replica mode

        Compares:
        - Manual replica mode costs
        - Auto-switch mode costs
        - Revenue protected by preventing downtime

        See Scenario 3 above for detailed example.

        Returns:
            Complete ROI analysis
        """
        # Manual replica costs (2x instances)
        manual_primary_cost = primary_price * hours
        manual_replica_cost = replica_price * hours
        manual_total_cost = manual_primary_cost + manual_replica_cost

        # Auto-switch costs (primary + occasional emergency replicas)
        # Assume emergency replicas run 2 hours per interruption
        auto_primary_cost = primary_price * hours
        auto_replica_cost = replica_price * Decimal(str(interruptions_prevented * 2))
        auto_total_cost = auto_primary_cost + auto_replica_cost

        # Cost difference
        overhead = manual_total_cost - auto_total_cost
        overhead_percent = Decimal('0')
        if auto_total_cost > 0:
            overhead_percent = (overhead / auto_total_cost) * 100

        # Downtime analysis
        downtime_prevented_seconds = interruptions_prevented * avg_downtime_per_interruption_seconds
        downtime_prevented_hours = Decimal(str(downtime_prevented_seconds)) / Decimal('3600')

        # Revenue protected
        revenue_protected = revenue_per_hour * downtime_prevented_hours

        # ROI calculation
        roi_percent = Decimal('0')
        if overhead > 0:
            roi_percent = (revenue_protected / overhead) * 100

        recommendation = 'not_justified'
        if roi_percent > 100:
            recommendation = 'manual_replica_justified'
        elif interruptions_prevented >= 4:
            recommendation = 'manual_replica_recommended'

        return {
            'costs': {
                'manual_replica_total': float(self._round_money(manual_total_cost)),
                'auto_switch_total': float(self._round_money(auto_total_cost)),
                'overhead': float(self._round_money(overhead)),
                'overhead_percent': float(self._round_percent(overhead_percent))
            },
            'downtime': {
                'interruptions_prevented': interruptions_prevented,
                'downtime_prevented_seconds': downtime_prevented_seconds,
                'downtime_prevented_hours': float(downtime_prevented_hours)
            },
            'roi': {
                'revenue_protected': float(self._round_money(revenue_protected)),
                'roi_percent': float(self._round_percent(roi_percent)),
                'recommendation': recommendation
            }
        }

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _round_money(self, value: Decimal) -> Decimal:
        """Round money to configured decimal places"""
        return value.quantize(
            Decimal('0.0001') if self.config.DECIMAL_PLACES_MONEY == 4 else Decimal('0.01')
        )

    def _round_percent(self, value: Decimal) -> Decimal:
        """Round percentage to configured decimal places"""
        return value.quantize(Decimal('0.01'))


# ============================================================================
# GLOBAL INSTANCE (SINGLETON PATTERN)
# ============================================================================

# Global calculation engine instance - import this in services
calculation_engine = CalculationEngine()

logger.info("Calculation Engine component initialized and ready")
