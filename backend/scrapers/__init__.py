"""
Data Collection Scrapers - Phase 6 Implementation

This package contains scrapers for collecting external AWS data:
- Spot Advisor data (interruption frequency ratings)
- Real-time Spot and On-Demand pricing

These scrapers run on scheduled intervals to keep data fresh.
"""

from .spot_advisor_scraper import (
    scrape_spot_advisor_data,
    get_spot_advisor_rating,
    get_low_interruption_instances,
    calculate_risk_score,
    refresh_cache_for_region
)

from .pricing_collector import (
    collect_spot_prices,
    collect_ondemand_prices,
    get_current_spot_price,
    get_price_comparison,
    calculate_savings_percentage
)

__all__ = [
    # Spot Advisor scraper
    "scrape_spot_advisor_data",
    "get_spot_advisor_rating",
    "get_low_interruption_instances",
    "calculate_risk_score",
    "refresh_cache_for_region",

    # Pricing collector
    "collect_spot_prices",
    "collect_ondemand_prices",
    "get_current_spot_price",
    "get_price_comparison",
    "calculate_savings_percentage",
]
