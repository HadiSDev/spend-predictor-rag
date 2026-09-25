"""The mock ERP stands up on its own, with nothing from either API installed."""
from fastapi.testclient import TestClient

from mock_erp.main import app


def test_health_reports_generated_data():
    with TestClient(app) as client:
        body = client.get("/api/v1/health").json()

    assert body["status"] == "ok"
    assert body["stats"]["invoices"] > 0
    assert body["stats"]["entries"] > 0
