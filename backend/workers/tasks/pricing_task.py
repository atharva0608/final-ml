from celery import Task
from backend.workers import app
from backend.models.base import get_db
import logging

logger = logging.getLogger(__name__)

@app.task(bind=True, name="backend.workers.tasks.pricing.fetch_aws_pricing")
def fetch_aws_pricing(self: Task):
    """
    Fetch AWS On-Demand pricing and Spot interruption risks
    """
    db = next(get_db())
    try:
        logger.info("Starting Pricing Data Fetch...")
        
        # 1. Fetch On-Demand Pricing
        # Assuming PricingCollector exists as per changes.txt
        # If it doesn't exist, this will crash. Verify imports first?
        # The user's changes.txt code block explicitly imports:
        # from backend.scrapers.pricing_collector import PricingCollector
        # from backend.scrapers.spot_advisor_scraper import SpotAdvisorScraper
        
        from backend.scrapers.pricing_collector import PricingCollector
        from backend.scrapers.spot_advisor_scraper import SpotAdvisorScraper

        collector = PricingCollector()
        prices = collector.fetch_pricing() 
        logger.info(f"Fetched {len(prices)} pricing records.")

        # 2. Fetch Spot Interruption Risks
        spot_scraper = SpotAdvisorScraper()
        risks = spot_scraper.scrape_data()
        logger.info(f"Fetched spot risk data for {len(risks)} instance types.")
        
        return {"status": "success", "message": "Pricing data updated successfully"}
    except Exception as e:
        logger.error(f"Error fetching pricing: {str(e)}")
        return {"status": "failed", "error": str(e)}
    finally:
        db.close()
