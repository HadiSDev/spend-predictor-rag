"""The mock ERP stands up on its own, with nothing from either API installed.

Its behaviour through a connector is covered in web-api's `test_mock_erp.py`;
this only pins that the package is self-sufficient.
"""
from fastapi.testclient import TestClient

from mock_erp.main import app


def test_health_reports_generated_data():
    with TestClient(app) as client:  # entering fires startup: the generator
        body = client.get("/api/v1/health").json()

    assert body["status"] == "ok"
    assert body["stats"]["invoices"] > 0
    assert body["stats"]["entries"] > 0
