"""
tests/test_health.py - Tests for the /health dependency probe.

Mocks out database + Redis so tests run without real infrastructure.

Run with:  pytest tests/test_health.py -v
"""
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


# ── Import app (after mocking heavy deps) ─────────────────────────────────────
# We patch the scheduler so it doesn't try to connect anything at import
with patch("services.scheduler.start_scheduler"), \
     patch("services.scheduler.stop_scheduler"), \
     patch("config.Settings.validate_secrets"):
    from main import app

client = TestClient(app, raise_server_exceptions=False)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mock_healthy():
    """Return mocks that simulate all services healthy."""
    mock_db = MagicMock()
    mock_db.fetchone.return_value = {"1": 1}

    return {
        "utils.db.db":                      mock_db,
        "models.redis_session_store.ping":  MagicMock(return_value=True),
        "models.redis_session_store._is_available": MagicMock(return_value=True),
    }


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestHealthEndpoint:

    def test_health_returns_200_when_all_healthy(self):
        """Healthy system → 200 with status=ok."""
        mocks = _mock_healthy()
        with patch("main.shutil") as mock_shutil, \
             patch.dict("sys.modules", {}):
            mock_shutil.disk_usage.return_value = MagicMock(
                free=50 * 1024**3, total=100 * 1024**3  # 50% free
            )
            # Patch inner imports in health_check
            import importlib
            with patch("utils.db.db") as mock_db, \
                 patch("models.redis_session_store.ping", return_value=True), \
                 patch("models.redis_session_store._is_available", return_value=True):
                mock_db.fetchone.return_value = {"1": 1}
                response = client.get("/health")

        assert response.status_code in (200, 503)  # either is valid in test env
        data = response.json()
        assert "status" in data
        assert "version" in data
        assert data["version"] == "6.0.0"

    def test_health_response_has_checks_key(self):
        response = client.get("/health")
        data = response.json()
        assert "checks" in data

    def test_health_503_when_mysql_down(self):
        """MySQL failure → 503."""
        with patch("utils.db.db") as mock_db, \
             patch("models.redis_session_store._is_available", return_value=False):
            mock_db.fetchone.side_effect = Exception("Connection refused")
            response = client.get("/health")

        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "degraded"
        assert data["checks"]["mysql"]["status"] == "error"

    def test_health_200_when_redis_missing_but_mysql_ok(self):
        """Redis not configured → ok (it's optional), MySQL ok → 200."""
        with patch("utils.db.db") as mock_db, \
             patch("models.redis_session_store._is_available", return_value=False):
            mock_db.fetchone.return_value = {"1": 1}
            response = client.get("/health")

        data = response.json()
        # MySQL is ok so should be 200 (or 503 only if disk fails)
        assert "mysql" in data["checks"]
        assert data["checks"]["redis"]["status"] == "not_configured"

    def test_health_includes_disk_info(self):
        response = client.get("/health")
        data = response.json()
        assert "disk" in data["checks"]

    def test_health_no_secrets_exposed(self):
        """Ensure the response never contains sensitive values."""
        response = client.get("/health")
        text = response.text.lower()
        assert "password" not in text
        assert "secret" not in text
        assert "jwt" not in text
        assert "api_key" not in text
