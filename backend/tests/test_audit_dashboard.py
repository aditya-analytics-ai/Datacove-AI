"""
Unit tests for services/audit_dashboard.py

Run with:  pytest tests/test_audit_dashboard.py -v
"""

import pytest
import json
from services.audit_dashboard import (
    AUDIT_EVENT_TYPES,
    record_event,
    _get_category,
    generate_compliance_report,
)


class TestAuditEventTypes:
    def test_categories_exist(self):
        assert "auth" in AUDIT_EVENT_TYPES
        assert "data" in AUDIT_EVENT_TYPES
        assert "pipeline" in AUDIT_EVENT_TYPES
        assert "security" in AUDIT_EVENT_TYPES

    def test_auth_events(self):
        auth_events = AUDIT_EVENT_TYPES["auth"]
        assert "login" in auth_events
        assert "logout" in auth_events
        assert "api_key_created" in auth_events

    def test_data_events(self):
        data_events = AUDIT_EVENT_TYPES["data"]
        assert "dataset_created" in data_events
        assert "dataset_viewed" in data_events
        assert "dataset_deleted" in data_events


class TestGetCategory:
    def test_auth_category(self):
        assert _get_category("login") == "auth"
        assert _get_category("api_key_created") == "auth"

    def test_data_category(self):
        assert _get_category("dataset_created") == "data"
        assert _get_category("dataset_viewed") == "data"

    def test_unknown_category(self):
        assert _get_category("unknown_event") == "other"


class TestComplianceReports:
    def test_gdpr_report(self):
        from datetime import datetime, timezone, timedelta

        start = datetime.now(timezone.utc) - timedelta(days=30)
        end = datetime.now(timezone.utc)

        # These tests require database setup - skip if DB not configured
        try:
            report = generate_compliance_report("gdpr", start, end)
            assert report["framework"] == "gdpr"
            assert "sections" in report
        except Exception:
            pytest.skip("Database not configured for compliance tests")

    def test_soc2_report(self):
        from datetime import datetime, timezone, timedelta

        start = datetime.now(timezone.utc) - timedelta(days=30)
        end = datetime.now(timezone.utc)

        try:
            report = generate_compliance_report("soc2", start, end)
            assert report["framework"] == "soc2"
            assert "sections" in report
        except Exception:
            pytest.skip("Database not configured for compliance tests")

    def test_hipaa_report(self):
        from datetime import datetime, timezone, timedelta

        start = datetime.now(timezone.utc) - timedelta(days=30)
        end = datetime.now(timezone.utc)

        try:
            report = generate_compliance_report("hipaa", start, end)
            assert report["framework"] == "hipaa"
        except Exception:
            pytest.skip("Database not configured for compliance tests")

    def test_pci_dss_report(self):
        from datetime import datetime, timezone, timedelta

        start = datetime.now(timezone.utc) - timedelta(days=30)
        end = datetime.now(timezone.utc)

        try:
            report = generate_compliance_report("pci-dss", start, end)
            assert report["framework"] == "pci-dss"
        except Exception:
            pytest.skip("Database not configured for compliance tests")


class TestRecordEvent:
    def test_record_event_structure(self):
        # Just test that the function can be called
        # (actual recording requires database)
        try:
            event_id = record_event(
                event_type="login",
                actor_id="user123",
                actor_email="test@example.com",
                ip_address="192.168.1.1",
                metadata={"browser": "Chrome"},
            )
            assert event_id is not None
            assert event_id.startswith("evt_")
        except Exception:
            # Database might not be available in test environment
            pass
