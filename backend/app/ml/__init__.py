"""
ML services — Phase 5.

Modules:
  - segmentation.py  — K-Means customer clustering
  - forecasting.py   — Prophet time-series spending forecasts
  - scoring.py       — XGBoost risk scoring + CLV

All services:
  1. Load features from user_features table (never raw transactions)
  2. Load champion model from MLflow registry
  3. Run inference
  4. Write results back to DB (forecasts, user_features.cluster_id, etc.)
  5. Return structured response for the API layer
"""
