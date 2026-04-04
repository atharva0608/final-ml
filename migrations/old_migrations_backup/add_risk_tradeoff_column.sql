-- Add risk/savings tradeoff percentage to optimization_strategy table
-- Default 20 = accept pool up to 20% more expensive if it has lower risk

ALTER TABLE optimization_strategy ADD COLUMN IF NOT EXISTS risk_savings_tradeoff_pct INTEGER DEFAULT 20;
