"""
DEPLOYMENT_GUIDE.md — Complete guide to deploying Datacove to production

Created: April 8, 2026
Purpose: Document production deployment procedures and best practices
Status: Ready for use

## Quick Start

### 1. Using Make Commands (Recommended)

```bash
# Install dependencies
make install

# Run tests
make test

# Start development
make dev

# Build Docker image
make build

# Start with docker-compose
make up

# View logs
make logs

# Stop services
make down
```

### 2. Development Setup

```bash
# Create virtual environment
make venv

# Install dependencies
make install

# Start backend (auto-reloads on file changes)
make backend

# In another terminal, start frontend
make frontend

# Both together
make dev
```

### 3. Production Deployment

#### Option A: Docker Compose (Recommended)

```bash
# Build production image
make build-prod

# Start all services
make up

# Monitor health
make health

# View logs
make logs

# Stop services
make down
```

#### Option B: Manual Docker

```bash
# Build image
docker build -t datacove:latest .

# Run backend
docker run -d \
  --name datacove-backend \
  -p 8000:8000 \
  -e ENV=production \
  -e DATABASE_URL=postgresql://user:pass@host/db \
  -e REDIS_URL=redis://localhost:6379 \
  datacove:latest

# Check health
curl http://localhost:8000/health
```

#### Option C: Direct Installation

```bash
# 1. Install Python 3.11+
sudo apt-get install python3.11 python3.11-venv

# 2. Clone repository
git clone <repo> datacove
cd datacove/backend

# 3. Create virtual environment
python3.11 -m venv venv
source venv/bin/activate  # or: venv\Scripts\activate (Windows)

# 4. Install dependencies
pip install -r requirements.txt

# 5. Configure environment
cp .env.example .env
# Edit .env with production settings

# 6. Run migrations
alembic upgrade head

# 7. Start server
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

## Configuration

### Environment Variables

Create `.env` file in root directory:

```bash
# Database
DATABASE_URL=postgresql://user:password@localhost:5432/datacove_prod
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=40

# Redis
REDIS_URL=redis://localhost:6379/0

# API Settings
API_HOST=0.0.0.0
API_PORT=8000
API_WORKERS=4
DEBUG=false
ENV=production

# Logging
LOG_LEVEL=INFO
LOG_FILE=/var/log/datacove/app.log

# CORS
CORS_ORIGINS=https://example.com,https://app.example.com
CORS_ALLOW_CREDENTIALS=true

# JWT
JWT_SECRET_KEY=your-secret-key-here-min-32-chars
JWT_ALGORITHM=HS256
JWT_EXPIRATION_HOURS=24

# Email (if applicable)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@example.com
SMTP_PASSWORD=your-password

# Feature Flags
ENABLE_OAUTH=false
ENABLE_AI_FEATURES=true
```

### Docker Compose Configuration

The `docker-compose.yml` includes:

```yaml
services:
  backend:
    image: datacove:latest
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://...
      - REDIS_URL=redis://redis:6379
    depends_on:
      - db
      - redis
    
  db:
    image: postgres:15
    environment:
      POSTGRES_DB: datacove
      POSTGRES_PASSWORD: secure_password
    volumes:
      - postgres_data:/var/lib/postgresql/data
  
  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data
```

## New Utilities & Best Practices

### 1. Error Response Standardization

Use standardized error responses across all endpoints:

```python
from utils.standard_errors import validation_error, auth_error

@router.post("/datasets")
async def create_dataset(data: DatasetCreate):
    try:
        # Validation
        if not data.name:
            raise validation_error("Dataset name required")
        
        # Authorization
        if not user.can_create_datasets:
            raise auth_error("Permission denied")
        
        return {"dataset_id": "..."}
    except ValueError as e:
        return validation_error(str(e))
```

### 2. Redis Caching

Use caching decorator for expensive operations:

```python
from utils.cache import cached

@cached(ttl=3600, key_prefix="dataset_profile")
async def get_dataset_profile(dataset_id: str):
    # Expensive operation (profiling a large dataset)
    return profile_result

# Cache automatically handles:
# - Serialization/deserialization
# - TTL and expiration
# - Graceful fallback if Redis unavailable
```

### 3. Structured Logging

Enable distributed tracing across services:

```python
from utils.structured_logging import configure_logging
from middleware.correlation_id_middleware import CorrelationIdMiddleware

# In main.py
configure_logging(level="INFO", json_output=True)  # Production
app.add_middleware(CorrelationIdMiddleware)

# In services - automatic correlation IDs in logs
logger.info("Processing dataset")  # Logs include request_id automatically
```

Output (production):
```json
{
  "timestamp": "2026-04-08T14:30:45",
  "level": "INFO",
  "message": "Processing dataset",
  "request_id": "abc-123-def",
  "user_id": "user@example.com"
}
```

### 4. Pagination

Standardize pagination across list endpoints:

```python
from utils.pagination import PaginationParams, paginate_response

@router.get("/datasets")
async def list_datasets(
    pagination: PaginationParams = Depends(),
    current_user: AuthUser = Depends(require_session),
):
    datasets = db.query(Dataset).filter_by(owner_id=current_user.id).all()
    
    return paginate_response(
        items=datasets[pagination.offset : pagination.offset + pagination.limit],
        total=len(datasets),
        limit=pagination.limit,
        offset=pagination.offset,
    )

# Response:
{
  "items": [...],
  "total": 150,
  "limit": 50,
  "offset": 0,
  "page": 1,
  "pages": 3,
  "has_next": true,
  "has_prev": false
}
```

### 5. Type Hints

All core services now have comprehensive type hints. Enable strict type checking:

```python
# Enable in mypy.ini or set in IDE
python.analysis.typeCheckingMode = "strict"

# Type hints enable:
- IDE autocomplete
- Early error detection
- Better documentation
- More maintainable code
```

## Monitoring & Observability

### Health Check

```bash
curl http://localhost:8000/health
# Response: {"status": "ok", "timestamp": "2026-04-08T..."}
```

### Logging

View production logs with JSON format:

```bash
# Follow logs
tail -f /var/log/datacove/app.log

# Filter by request_id
grep '"request_id":"abc-123-def"' app.log

# View errors only
grep '"level":"ERROR"' app.log
```

### Database Migrations

```bash
# Check current version
alembic current

# Run pending migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# View migration history
alembic history
```

### Performance Monitoring

Logs now include request duration:

```json
{
  "request_id": "abc-123",
  "status_code": 200,
  "duration_ms": 234.56,
  "user_id": "user@example.com"
}
```

## Testing Before Deployment

### 1. Unit Tests

```bash
make test
# Runs all tests in tests/ directory
```

### 2. Integration Tests

```bash
make test-integration
# Tests critical workflows:
# - Authentication flow
# - Dataset upload/profiling
# - Data cleaning
# - Export
# - Error handling
```

### 3. Route Validation

```bash
make test-routes
# Verifies all 115 routes load correctly
```

### 4. Type Checking

```bash
make typecheck
# Validates type hints across services
```

### 5. Full CI Pipeline

```bash
make ci
# Runs: clean → install → lint → typecheck → test
```

## Security Checklist

- [ ] JWT secret key is strong (32+ characters, random)
- [ ] Database password is strong and unique
- [ ] CORS origins restricted to known domains
- [ ] Environment variables not committed to git
- [ ] Non-root user running container (Dockerfile uses `datacove` user)
- [ ] Health check passes
- [ ] SSL/TLS configured (if behind nginx/load balancer)
- [ ] Rate limiting enabled
- [ ] Database backups automated
- [ ] Logs rotated and archived

## Scaling

### Horizontal Scaling (Multiple Instances)

```yaml
# docker-compose.yml
services:
  backend:
    image: datacove:latest
    deploy:
      replicas: 3
    environment:
      - UVICORN_WORKERS=4  # 3 instances × 4 workers = 12 processes
```

### Load Balancing

Use nginx or similar to distribute traffic:

```nginx
upstream datacove {
    server localhost:8000;
    server localhost:8001;
    server localhost:8002;
}

server {
    listen 80;
    location / {
        proxy_pass http://datacove;
    }
}
```

### Caching Strategy

```python
# Redis stores:
- User sessions (1 hour TTL)
- Dataset profiles (24 hour TTL)
- Query results (1 hour TTL)
- API responses (variable TTL)
```

## Troubleshooting

### Backend won't start

```bash
# Check logs
docker-compose logs backend

# Verify database connection
make health

# Run migrations
make migrate

# Check environment variables
docker-compose config
```

### High memory usage

```bash
# Check processes
docker stats

# Adjust worker count
UVICORN_WORKERS=2  # Reduce from default 4

# Check for memory leaks
python -m memory_profiler main.py
```

### Slow queries

```bash
# Enable slow query log in PostgreSQL
# Then check correlation IDs in logs to trace slow requests

grep '"duration_ms":[0-9]{4,}' /var/log/datacove/app.log
```

### Redis issues

```bash
# Check Redis connectivity
redis-cli ping

# Monitor Redis
redis-cli monitor

# Clear cache if needed
make shell  # Enter container shell
redis-cli FLUSHDB
```

## Backup & Recovery

### Database Backup

```bash
# Backup PostgreSQL
pg_dump -U postgres datacove > backup_$(date +%Y%m%d_%H%M%S).sql

# Restore from backup
psql -U postgres datacove < backup_20240408_143000.sql
```

### Configuration Backup

```bash
# Backup environment and configs
cp .env .env.backup.$(date +%Y%m%d_%H%M%S)
```

## Rollback Procedure

```bash
# If deployment breaks:
1. Stop new services: make down
2. Start previous version: docker run datacove:previous
3. Check health: make health
4. Investigate logs: make logs
5. Fix issues
6. Re-deploy: make build && make up
```

## Performance Tuning

### Database Connection Pool

```env
DATABASE_POOL_SIZE=20        # Connections to maintain
DATABASE_MAX_OVERFLOW=40     # Maximum additional connections
```

### Uvicorn Workers

```env
UVICORN_WORKERS=4            # Number of worker processes
```

### Redis Optimization

```env
REDIS_POOL_SIZE=20           # Connection pool size
```

## Support & References

- FastAPI Docs: https://fastapi.tiangolo.com
- PostgreSQL Docs: https://www.postgresql.org/docs/
- Redis Docs: https://redis.io/docs/
- Docker Docs: https://docs.docker.com/
- Uvicorn Docs: https://www.uvicorn.org/

## Files Modified/Created

1. `backend/Dockerfile` - Container definition (existing, verified)
2. `docker-compose.yml` - Service orchestration (existing)
3. `Makefile` - Build automation (new)
4. `backend/utils/standard_errors.py` - Error standardization (new)
5. `backend/utils/cache.py` - Redis caching (new)
6. `backend/utils/tracing.py` - Distributed tracing (new)
7. `backend/middleware/correlation_id_middleware.py` - Correlation ID injection (new)
8. `backend/utils/structured_logging.py` - Structured logging (new)
9. `backend/utils/pagination.py` - Pagination utility (new)
10. `backend/tests/test_integration.py` - Integration tests (new)
11. This deployment guide (DEPLOYMENT_GUIDE.md)

## Non-Breaking Changes

✅ All new utilities are:
- Opt-in (decorator/dependency based)
- Gracefully degradeable (works without Redis, etc.)
- Fully backward compatible
- Non-invasive to existing code

Existing code flows are unchanged. New features can be adopted incrementally.
"""
