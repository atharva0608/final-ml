from celery import Task
from backend.workers import app
from backend.scrapers.pricing_collector import collect_spot_prices, collect_ondemand_prices
from backend.scrapers.spot_advisor_scraper import scrape_spot_advisor_data
import logging

logger = logging.getLogger(__name__)

@app.task(bind=True, name="backend.workers.tasks.pricing.fetch_aws_pricing")
def fetch_aws_pricing(self: Task):
    """
    Fetch AWS On-Demand pricing and Spot interruption risks
    """
    try:
        logger.info("Starting Pricing Data Fetch...")
        
        # 1. Fetch Spot Prices
        logger.info("Collecting Spot Prices...")
        spot_stats = collect_spot_prices()
        logger.info(f"Spot Price Collection Stats: {spot_stats}")

        # 2. Fetch Spot Advisor Data (Interruption Risks)
        logger.info("Collecting Spot Advisor Data...")
        advisor_stats = scrape_spot_advisor_data()
        logger.info(f"Spot Advisor Collection Stats: {advisor_stats}")
        
        # 3. Fetch On-Demand Prices (Optional, can be heavy)
        # Uncomment if needed to run daily
        # logger.info("Collecting On-Demand Prices...")
        # ondemand_stats = collect_ondemand_prices()
        # logger.info(f"On-Demand Price Collection Stats: {ondemand_stats}")

        return {
            "status": "success", 
            "message": "Pricing data updated successfully",
            "spot_stats": spot_stats,
            "advisor_stats": advisor_stats
        }
    except Exception as e:
        logger.error(f"Error fetching pricing: {str(e)}", exc_info=True)
        return {"status": "failed", "error": str(e)}
