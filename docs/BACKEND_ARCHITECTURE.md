# Backend Architecture & Contents

**Framework:** FastAPI 0.135.3  
**Python Version:** 3.11  
**Environment:** Virtual Environment (`.venv_new`)  
**Database:** MySQL  
**Cache/Queue:** Redis + Celery  

---

## Directory Structure

```
backend/
├── config.py                    # Configuration & environment settings
├── main.py                      # FastAPI application entry point
├── worker.py                    # Celery background worker
├── requirements.txt             # Python dependencies
├── test_all_routes.py          # Route validation script
│
├── routes/                      # [26+ API endpoint files]
│   ├── auth_routes.py           # Authentication (login, register, JWT)
│   ├── session_routes.py        # Session management
│   ├── upload_routes.py         # File upload handling
│   ├── export_routes.py         # Data export (CSV, Excel, JSON, Parquet)
│   ├── export_destinations_routes.py  # Export to external services
│   │
│   ├── analysis_routes.py       # Profiling, health score, anomalies
│   ├── cleaning_routes.py       # Data cleaning operations
│   ├── validation_routes.py     # Data validation rules
│   ├── streaming_routes.py      # Streaming uploads & incremental processing
│   │
│   ├── pipeline_routes.py       # Pipeline creation & execution
│   ├── orchestrator_routes.py   # AI pipeline orchestration
│   ├── batch_routes.py          # Batch processing operations
│   │
│   ├── ai_agent_routes.py       # Automated cleaning agent
│   ├── ai_data_scientist_routes.py  # ML training & prediction
│   ├── power_routes.py          # Visualization, PII detection, formulas
│   │
│   ├── sql_routes.py            # SQL query engine
│   ├── fuzzy_routes.py          # Fuzzy deduplication
│   ├── vocab_routes.py          # Vocabulary mapping
│   ├── report_routes.py         # Report generation
│   │
│   ├── connector_routes.py      # Data connectors (S3, GSheets, SQL)
│   ├── onboarding_routes.py     # Sample datasets & tutorials
│   ├── sharing_routes.py        # Dataset sharing & collaboration
│   ├── schedule_routes.py       # Scheduled jobs & webhooks
│   ├── billing_routes.py        # Billing & subscription management
│   ├── audit_routes.py          # Audit logging & compliance
│   ├── admin_routes.py          # Admin management endpoints
│   ├── jobs_routes.py           # Background job monitoring
│   │
│   └── __init__.py
│
├── services/                    # [24+ Business logic modules]
│   ├── anomaly_detector.py      # Time-series & statistical anomalies
│   ├── audit_log.py             # Audit trail logging
│   ├── cleaning_engine.py       # Core data cleaning logic
│   ├── column_similarity.py     # Column matching & similarity
│   ├── correlation_engine.py    # Statistical correlations
│   ├── dataset_loader.py        # Dataset loading & parsing
│   ├── fuzzy_dedup.py           # Fuzzy deduplication (MinHash LSH)
│   ├── health_score.py          # Data quality health scoring
│   ├── issue_detector.py        # Data quality issue detection
│   ├── nl_query_engine.py       # Natural language query parsing
│   ├── pattern_library.py       # Pattern matching & recognition
│   ├── performance.py           # Performance monitoring
│   ├── pii_detector.py          # PII detection & masking
│   ├── pipeline_engine.py       # Pipeline execution engine
│   ├── profiling_engine.py      # Data profiling & statistics
│   ├── referential_integrity.py # Foreign key validation
│   ├── report_generator.py      # PDF/HTML report generation
│   ├── scheduler.py             # APScheduler integration
│   ├── sql_engine.py            # DuckDB SQL execution
│   ├── streaming_engine.py      # Streaming/chunked processing
│   ├── timeseries_anomaly.py    # STL decomposition for anomalies
│   ├── validation_rules.py      # Custom validation rules
│   ├── visualization_engine.py  # Chart generation (Recharts specs)
│   ├── vocab_mapper.py          # Vocabulary mapping & translation
│   │
│   ├── ai_agent.py              # Automated cleaning orchestration
│   ├── ai_data_scientist.py     # AutoML training & evaluation
│   ├── ai_orchestrator.py       # AI service orchestration
│   ├── ai_safety.py             # Safety checks & constraints
│   ├── ai_suggestions.py        # AI suggestions engine
│   │
│   └── __init__.py
│
├── models/                      # [4 Data models]
│   ├── __init__.py
│   ├── dataset_session.py       # Session management (in-memory + DB)
│   ├── pipeline_model.py        # Pipeline metadata & execution
│   ├── redis_session_store.py   # Redis-based session caching
│   │
├── utils/                       # [13+ Utility modules]
│   ├── __init__.py
│   ├── ai_rate_limiter.py       # Rate limiting for AI APIs
│   ├── auth.py                  # JWT authentication & authorization
│   ├── billing.py               # Billing & subscription logic
│   ├── db.py                    # MySQL connection & migrations
│   ├── email_sender.py          # Email delivery service
│   ├── explainability.py        # Explanation generation for suggestions
│   ├── file_utils.py            # File I/O & path handling
│   ├── job_store.py             # Job queueing & tracking
│   ├── logger.py                # Structured logging (Loguru)
│   ├── preview.py               # Data preview & sampling
│   ├── request_validator.py     # Input validation helpers
│   ├── retry.py                 # Retry decorator for resilience
│   ├── session_guard.py         # Session ownership validation
│   └── validation_utils.py      # Data validation utilities
│
├── middleware/                  # [2 Middleware modules]
│   ├── __init__.py
│   └── rate_limit.py            # Global per-IP rate limiting
│
├── schemas/                     # [3 Pydantic schemas]
│   ├── __init__.py
│   ├── analysis_schema.py       # Analysis request/response schemas
│   ├── cleaning_schema.py       # Cleaning operation schemas
│   └── dataset_schema.py        # Dataset metadata schemas
│
├── tests/                       # [10+ Test files]
│   ├── conftest.py              # Pytest configuration
│   ├── test_auth.py             # Authentication tests
│   ├── test_cleaning_engine.py
│   ├── test_chunked_processing.py
│   ├── test_health_score.py
│   ├── test_health.py
│   ├── test_pipeline_engine.py
│   ├── test_production_engineering.py
│   ├── test_rate_limit.py
│   ├── test_upgrades.py
│   └── __init__.py
│
├── sample_datasets/             # [Duplicate structure for tutorials]
│   ├── hr_data.csv
│   ├── messy_customers.csv
│   ├── sales_data.csv
│   ├── [Duplicate middleware, models, routes, schemas]
│
└── datasets/                    # [Runtime data directory]
    └── [Session files & versioned snapshots stored here]
```

---

## Core Components

### 📌 Entry Point: `main.py`
- FastAPI application initialization
- CORS middleware configuration
- Global exception handling
- Health check endpoint
- Route registration (26+ routers)
- Lifespan management (startup/shutdown)

### 🔐 Authentication: `utils/auth.py`
- JWT token generation & validation
- Password hashing (bcrypt)
- Role-based access control (user, admin)
- AuthUser dataclass with user_id, username, role, is_active
- `get_current_user()` dependency
- `require_admin()` dependency

### 💾 Database: `utils/db.py`
- MySQL connection pooling
- Schema migration on startup
- Audit logging
- Session storage (TTL: 1 hour, max 200 sessions)

### 🗂️ Session Management: `models/dataset_session.py`
- In-memory session storage
- DataFrame caching
- Session ownership validation
- Dataset versioning (snapshots)
- Automatic cleanup on TTL expiry

### 🎯 Data Cleaning: `services/cleaning_engine.py`
- Deduplication (exact & fuzzy)
- Missing value imputation
- Type casting & normalization
- Whitespace trimming
- Outlier detection
- Formula-based computed columns

### 📊 Analysis Services
- **profiling_engine.py** — Column statistics, distributions
- **health_score.py** — Data quality scoring
- **anomaly_detector.py** — Statistical & time-series anomalies
- **correlation_engine.py** — Pearson, Spearman correlations
- **issue_detector.py** — Data quality issues

### 🤖 AI Services
- **ai_agent.py** — Autonomous cleaning orchestration
- **ai_data_scientist.py** — AutoML (RandomForest, XGBoost)
- **ai_suggestions.py** — Human-in-the-loop improvements
- **ai_orchestrator.py** — Service chaining

### 🔗 Integrations
- **Anthropic Claude API** — Advanced reasoning
- **OpenAI GPT-4** — Fallback AI
- **Google Gemini** — Free tier option
- **Stripe** — Payment processing
- **Google Sheets** — Data connector
- **AWS S3** — File storage
- **DuckDB** — SQL queries

---

## Key Features

| Feature | Service | File(s) |
|---------|---------|---------|
| **Upload** | Multipart form, CSV/Excel/Parquet | `upload_routes.py` |
| **Profiling** | Column stats, distributions, types | `profiling_engine.py` |
| **Cleaning** | 15+ operations, formula support | `cleaning_engine.py` |
| **Health Score** | Quality metrics, penalties | `health_score.py` |
| **Anomalies** | Statistical + STL decomposition | `anomaly_detector.py` |
| **PII Detection** | Regex + ML-based | `pii_detector.py` |
| **Fuzzy Dedup** | MinHash LSH for scalability | `fuzzy_dedup.py` |
| **Export** | CSV, Excel, JSON, Parquet | `export_routes.py` |
| **Pipelines** | DAG-based workflow engine | `pipeline_engine.py` |
| **Scheduling** | Cron jobs + webhooks | `schedule_routes.py` |
| **Reporting** | PDF/HTML generation | `report_generator.py` |
| **SQL Queries** | DuckDB backend | `sql_engine.py` |
| **Sharing** | Collaboration + permissions | `sharing_routes.py` |
| **Audit** | Compliance logging | `audit_log.py` |
| **Admin** | User management, rates, stats | `admin_routes.py` |

---

## Connection Points

### API Routes Structure
All routes follow this pattern:
```python
@router.post("/endpoint")
async def handler(req: RequestModel, user: AuthUser = Depends(get_current_user)):
    session = require_session(session_id, owner_id=user.user_id)
    # validate ownership
    # business logic
    return response
```

### Request Flow
1. **FastAPI receives request**
2. **CORS middleware** validates origin
3. **Rate limiter** checks IP limits
4. **Auth middleware** extracts JWT → AuthUser
5. **Route handler** processes request
6. **Service layer** executes business logic
7. **Models layer** manages data
8. **Database/Redis** persistence
9. **Response** marshalled to JSON

### Error Handling
- Global exception handler catches all unhandled errors
- HTTPException for API errors (400, 401, 403, 404, 500)
- Credential redaction filter prevents secrets in logs

---

## Configuration

**Environment Variables** (see `.env`):
```
JWT_SECRET              # MUST be set (32+ chars)
CORS_ORIGINS            # Comma-separated allowed origins
MYSQL_URL              # MySQL connection string
REDIS_URL              # Redis connection (optional)
ANTHROPIC_API_KEY      # Claude API key
OPENAI_API_KEY         # GPT API key
GOOGLE_API_KEY         # Gemini API key
STRIPE_SECRET_KEY      # Payment key
AWS_ACCESS_KEY_ID      # S3 access
AWS_SECRET_ACCESS_KEY  # S3 secret
```

**Configuration Class** (`config.py`):
- Settings validation at startup
- Safe defaults (AUTH_ENABLED=True)
- Dynamic CORS list parsing

---

## Database Schema

### Tables
- **users** — User accounts (username, password_hash, role, created_at)
- **audit_log** — Activity trail (user, action, resource, timestamp)
- **pipelines** — Workflow definitions (user_id, name, definition, created_at)
- **billing** — Subscription records (user_id, tier, expires_at)

### Schema Migrations
Run automatically on app startup via `db.py`. Uses custom migration system (no Alembic).

---

## Dependencies

**Core:**
- fastapi@0.135.3, uvicorn@0.29.0, pydantic@2.7.1

**Data Processing:**
- pandas@2.2.2, numpy@1.26.4, openpyxl@3.1.2, pyarrow@14.0.0

**Database:**
- sqlalchemy@2.0.0, mysql-connector-python, redis@5.0.0, celery@5.3.0

**ML/Analytics:**
- scikit-learn@1.4.0, scipy@1.11.0, statsmodels@0.14.0, duckdb@0.10.0

**AI:**
- anthropic@0.28.0, openai@1.30.1, google-generativeai@0.7.0

**Utilities:**
- loguru, croniter, APScheduler@3.11.0, rapidfuzz@3.6.0, datasketch@1.6.4

---

## Performance Characteristics

| Operation | Time | Limits |
|-----------|------|--------|
| File Upload | Chunked (50KB-100KB per chunk) | 50MB max |
| Profiling | ~100ms per 10K rows | 1M row limit |
| Cleaning | ~50ms per 10K rows | Streaming if >100K |
| AI Analysis | 5-30s (API dependent) | Rate: 10 req/min |
| Export | Streaming (no memory bloat) | All formats |

---

## Security

✅ JWT authentication with roles (user, admin)  
✅ Per-session ownership validation  
✅ Per-IP rate limiting (100+ req/min default)  
✅ AI API rate limiting (10 req/min)  
✅ Credential redaction in logs  
✅ CORS whitelist validation  
✅ HTTPS-ready (production should use SSL)  
✅ Audit logging for compliance  

---

## Development Status

**Phase 3 Features:**
- ✅ Onboarding (sample datasets)
- ✅ Sharing (collaboration)
- ✅ Scheduling (cron jobs)
- ✅ Connectors (integrations)
- ✅ Billing (subscriptions)
- ✅ Export Destinations (external services)
- ✅ Orchestrator (AI service chaining)

**Migration:**
- ✓ V3 Features migrated to `vocab_routes` & `batch_routes`
- ✓ `new_routes` removed (deprecated)

---

## Testing

Total Tests: 10+ test files in `tests/`

Run with:
```bash
pytest tests/ -v --cov=.
```

---

## Quick Start

```bash
# Activate venv
source .venv_new/bin/activate  # Linux/Mac
.venv_new\Scripts\activate     # Windows

# Start server
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Docs available at:
# http://localhost:8000/docs (Swagger UI)
# http://localhost:8000/redoc (ReDoc)
```

**Status:** ✅ **Production Ready** — All 26 routes validated, all imports correct.
