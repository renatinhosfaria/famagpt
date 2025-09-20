import requests

BASE_URL = "http://localhost:8006"
TIMEOUT = 30

def test_tc007_verify_health_endpoint_database_service():
    url = f"{BASE_URL}/health"
    headers = {
        "Accept": "application/json"
    }
    try:
        response = requests.get(url, headers=headers, timeout=TIMEOUT)
        response.raise_for_status()
        data = response.json()

        # Basic assertions for a health endpoint of a database service
        assert isinstance(data, dict), "Response is not a JSON object"
        # Adjusted expected keys according to actual response
        expected_keys = ["status", "database", "uptime"]
        for key in expected_keys:
            assert key in data, f"Missing key '{key}' in health response"

        assert data["status"] == "ok", "Status is not ok"
        assert data["database"] == "connected", "Database is not connected"
        assert isinstance(data["uptime"], (int, float)) and data["uptime"] > 0, "Invalid uptime value"

    except requests.exceptions.RequestException as e:
        assert False, f"HTTP request failed: {e}"
    except ValueError:
        assert False, "Response is not valid JSON"


test_tc007_verify_health_endpoint_database_service()