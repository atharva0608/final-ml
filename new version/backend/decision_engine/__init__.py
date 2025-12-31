"""
Decision Engine Module - Core decision logic for spot optimization

The Decision Engine is the brain of CAST-AI Mini. It analyzes instance state,
usage metrics, and predicted prices to decide whether to stay on current spot
pool, switch to a better pool, or fallback to on-demand.

Components:
- PoolDiscoveryAndDedup: Find available pools
- CurrentPriceFilter: Filter by current price
- OneHourPriceForecast: ML-based price prediction
- UsageClassification: Over/right/under-provisioned detection
- FutureBaselineCheck: Evaluate if current pool will be OK
- CandidateFilterWithUsageRules: Apply right-sizing rules
- FutureImprovementFilter: Ensure meaningful improvement
- ActionSelector: Make final decision
"""

from .engine import DecisionEngine

__all__ = ['DecisionEngine']
