# Decision Engines

This directory contains decision engine modules for the AWS Spot Optimizer.

## Current Engine: ML-Based Decision Engine

The default `ml_based_engine.py` provides a framework for machine learning-based spot instance optimization decisions.

### Quick Start

The engine works out of the box with rule-based fallback logic. To enable ML-powered decisions:

1. **Train your models** using historical spot pricing and interruption data
2. **Upload model files** (.pkl, .h5, .pt) to the `models/` directory via the admin UI
3. **Implement the load() method** in `ml_based_engine.py` to load your trained models
4. **Implement the _ml_based_decision() method** with your prediction pipeline

### Uploading Models via API

You can upload trained ML models through the admin dashboard or via API:

```bash
# Upload ML model files
curl -X POST http://your-server:5000/api/admin/ml-models/upload \
  -F "files=@price_predictor.pkl" \
  -F "files=@risk_predictor.pkl"

# Check upload sessions
curl http://your-server:5000/api/admin/ml-models/sessions

# Activate models (restart backend with new models)
curl -X POST http://your-server:5000/api/admin/ml-models/activate \
  -H "Content-Type: application/json" \
  -d '{"sessionId": "your-session-id"}'

# Fallback to previous version
curl -X POST http://your-server:5000/api/admin/ml-models/fallback
```

### Decision Types

The engine should return one of these decision types:

- **`stay_spot`** - Continue running on current spot instance
- **`switch_to_spot`** - Switch to a different (better) spot pool
- **`switch_to_ondemand`** - Switch to on-demand due to high risk
- **`stay_ondemand`** - Continue on on-demand instance

### Expected Model Outputs

Your ML models should predict:

1. **Spot Price Trend** - Future price movement prediction
2. **Interruption Risk** - Probability of interruption (0-1)
3. **Pool Quality Score** - Overall pool stability rating

### Example Implementation

```python
def load(self):
    """Load your trained models"""
    import joblib

    self.models['price_predictor'] = joblib.load(
        self.model_dir / 'price_lstm_model.pkl'
    )
    self.models['risk_predictor'] = joblib.load(
        self.model_dir / 'interruption_rf_model.pkl'
    )

    logger.info("✓ ML models loaded successfully")
    self.models_loaded = True
    return True

def _ml_based_decision(self, agent_data, pricing_data, market_data):
    """Use ML models to make decisions"""

    # Feature engineering
    features = self._prepare_features(agent_data, pricing_data, market_data)

    # Predict interruption risk
    risk_score = self.models['risk_predictor'].predict_proba(features)[0][1]

    # Predict price trend
    price_trend = self.models['price_predictor'].predict(features)[0]

    # Decision logic based on predictions
    if risk_score > 0.7:
        return {
            'decision_type': 'switch_to_ondemand',
            'risk_score': risk_score,
            'expected_savings': 0.0,
            'confidence': 0.85,
            'reason': f'High interruption risk detected ({risk_score:.2%})'
        }

    # ... more logic here
```

### Directory Structure

```
decision_engines/
├── __init__.py              # Package initialization
├── ml_based_engine.py       # Main decision engine (this file)
├── README.md                # This file
└── custom_engine.py         # Your custom implementations (optional)

models/                      # Model files uploaded via UI
├── price_predictor.pkl
├── risk_predictor.pkl
└── feature_scaler.pkl
```

### Model Versioning

The system keeps the last 2 upload sessions:
- **Live**: Currently active models
- **Fallback**: Previous version (for quick rollback)

Older sessions are automatically deleted to save space.

### Testing Your Engine

After implementing your decision logic:

1. Upload your model files via the admin UI
2. Monitor the logs: `tail -f /home/ubuntu/logs/backend.log`
3. Check decision history: `GET /api/client/{id}/agents/decisions`
4. Verify health indicators in the dashboard

### Support

For questions or issues:
- Check logs: `/home/ubuntu/logs/backend.log`
- Review system events: `GET /api/system/events`
- See model registry: `GET /api/admin/ml-models/sessions`
