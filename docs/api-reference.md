# FinScope AI — API Reference

## Base URL

| Environment | URL |
|---|---|
| Local | `http://localhost:8000` |
| Swagger UI | `http://localhost:8000/docs` |
| ReDoc | `http://localhost:8000/redoc` |

## Authentication

All protected endpoints require a JWT Bearer token:
```
Authorization: Bearer <access_token>
```

### Endpoints

#### `POST /api/v1/auth/register`
Create a new user account.

**Request:**
```json
{
  "email": "user@example.com",
  "password": "Str0ngP@ss!",
  "full_name": "Jane Smith"
}
```

**Response:** `201 Created` — UserResponse

---

#### `POST /api/v1/auth/login`
OAuth2 password flow — returns JWT pair.

**Form fields:** `username` (email), `password`

**Response:**
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 1800
}
```

---

#### `GET /api/v1/auth/me`
Returns authenticated user profile.

---

#### `GET /api/v1/transactions`
List transactions (paginated).

**Query params:** `page`, `page_size`, `account_id`, `category`, `is_anomaly`, `search`

---

#### `POST /api/v1/transactions/upload`
Upload CSV or PDF bank statement.

**Query:** `account_id`
**Body:** multipart/form-data with `file`

---

#### `GET /api/v1/ml/features`
Get pre-computed ML features for current user.

#### `POST /api/v1/ml/features/refresh`
Recompute features synchronously.

#### `GET /api/v1/ml/risk`
Get risk score + level + top factors.

#### `GET /api/v1/ml/clv`
Get CLV estimate + churn probability.

#### `GET /api/v1/ml/forecasts`
Get spending forecast. Query: `horizon_days` (7-365, default 90).

#### `GET /api/v1/explain/risk`
SHAP explanation for risk score.

#### `GET /api/v1/recommendations`
List personalized recommendations.

#### `POST /api/v1/chat/message`
Send a question to the AI assistant.

**Body:** `{"message": "How much did I spend on dining?"}`

---

#### Admin Endpoints (role=admin only)

#### `GET /api/v1/admin/stats`
Platform-wide KPI aggregates.

#### `GET /api/v1/admin/cohorts`
Cohort analytics grouped by ML cluster.
