# Datacove API Documentation

**Version**: 6.0.0  
**Base URL**: `http://localhost:8000/api`

---

## Authentication

### Login
```http
POST /api/auth/login
Content-Type: application/json

{
  "username": "your_username",
  "password": "your_password"
}
```

**Response:**
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "user_id": "uuid",
  "username": "your_username",
  "role": "user"
}
```

### Register
```http
POST /api/auth/register
Content-Type: application/json

{
  "username": "new_user",
  "password": "secure_password"
}
```

---

## Sessions

### Create Session
```http
POST /api/sessions
Authorization: Bearer <token>
Content-Type: multipart/form-data

file: <CSV or Excel file>
```

### List Sessions
```http
GET /api/sessions
Authorization: Bearer <token>
```

### Get Session
```http
GET /api/sessions/{session_id}
Authorization: Bearer <token>
```

### Delete Session
```http
DELETE /api/sessions/{session_id}
Authorization: Bearer <token>
```

---

## Data Cleaning

### Apply Transformation
```http
POST /api/clean
Authorization: Bearer <token>
Content-Type: application/json

{
  "session_id": "uuid",
  "action": "remove_duplicates",
  "params": {}
}
```

### Auto Clean
```http
POST /api/clean/auto
Authorization: Bearer <token>
Content-Type: application/json

{
  "session_id": "uuid"
}
```

### Available Actions

| Action | Description |
|--------|-------------|
| `remove_duplicates` | Remove duplicate rows |
| `trim_whitespace` | Trim leading/trailing spaces |
| `fill_missing` | Fill missing values |
| `standardise_capitalisation` | Standardize text case |
| `coerce_numeric` | Convert to numeric |
| `standardise_dates` | Standardize date formats |
| `find_replace` | Find and replace values |
| `split_column` | Split column into multiple |
| `merge_columns` | Merge columns together |

---

## Analysis

### Get Summary
```http
GET /api/analysis/summary?session_id={session_id}
Authorization: Bearer <token>
```

### Get Profile
```http
POST /api/analysis/profile
Authorization: Bearer <token>
Content-Type: application/json

{
  "session_id": "uuid"
}
```

### Health Score
```http
POST /api/analysis/health
Authorization: Bearer <token>
Content-Type: application/json

{
  "session_id": "uuid"
}
```

---

## Pipelines

### Create Pipeline
```http
POST /api/pipelines
Authorization: Bearer <token>
Content-Type: application/json

{
  "name": "my_pipeline",
  "steps": [
    {"action": "remove_duplicates", "params": {}},
    {"action": "fill_missing", "params": {"strategy": "mean"}}
  ]
}
```

### Run Pipeline
```http
POST /api/pipelines/{pipeline_id}/run
Authorization: Bearer <token>
Content-Type: application/json

{
  "session_id": "uuid"
}
```

---

## AI Features

### Natural Language Command
```http
POST /api/ai/nl
Authorization: Bearer <token>
Content-Type: application/json

{
  "session_id": "uuid",
  "command": "remove duplicates and fill missing values with mean"
}
```

### AI Suggestions
```http
POST /api/ai/suggest
Authorization: Bearer <token>
Content-Type: application/json

{
  "session_id": "uuid"
}
```

---

## Connectors

### PostgreSQL Import
```http
POST /api/connectors/postgresql
Authorization: Bearer <token>
Content-Type: application/json

{
  "host": "localhost",
  "port": 5432,
  "database": "mydb",
  "username": "user",
  "password": "pass",
  "query": "SELECT * FROM customers"
}
```

### MongoDB Import
```http
POST /api/connectors/mongodb
Authorization: Bearer <token>
Content-Type: application/json

{
  "host": "localhost",
  "port": 27017,
  "database": "mydb",
  "collection": "customers"
}
```

---

## Distributed Processing

### Profile Dataset
```http
POST /api/distributed/profile
Authorization: Bearer <token>
Content-Type: application/json

{
  "dataset_id": "uuid"
}
```

### Process Dataset
```http
POST /api/distributed/process
Authorization: Bearer <token>
Content-Type: application/json

{
  "dataset_id": "uuid",
  "transformations": [
    {"action": "remove_duplicates", "params": {}}
  ],
  "mode": "auto"
}
```

---

## API Keys (Public API)

### Create API Key
```http
POST /api/api-keys
Authorization: Bearer <token>
Content-Type: application/json

{
  "name": "My API Key",
  "tier": "pro",
  "scopes": ["datasets:read", "datasets:write"]
}
```

### List API Keys
```http
GET /api/api-keys
Authorization: Bearer <token>
```

---

## Error Codes

| Code | Description |
|------|-------------|
| 400 | Bad Request - Invalid input |
| 401 | Unauthorized - Invalid or missing token |
| 403 | Forbidden - Insufficient permissions |
| 404 | Not Found - Resource doesn't exist |
| 429 | Too Many Requests - Rate limit exceeded |
| 500 | Internal Server Error |

---

## Rate Limits

| Tier | Requests/Minute | Requests/Day | Requests/Month |
|------|-----------------|--------------|----------------|
| Free | 60 | 1,000 | 10,000 |
| Basic | 300 | 10,000 | 100,000 |
| Pro | 1,000 | 100,000 | 1,000,000 |
| Enterprise | 10,000 | 1,000,000 | 10,000,000 |

---

## SDKs

### Python
```bash
pip install datacove
```

```python
from datacove import Datacove

client = Datacove(api_key="your_api_key")

# List datasets
datasets = client.datasets.list()

# Upload file
dataset = client.datasets.upload("data.csv")

# Clean data
result = client.clean.apply(
    dataset_id=dataset["id"],
    action="remove_duplicates"
)
```
