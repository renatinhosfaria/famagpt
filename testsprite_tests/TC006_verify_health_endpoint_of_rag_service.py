import requests

BASE_URL = "http://localhost:8005"
TIMEOUT = 30
HEALTH_ENDPOINT = "/health"
HEADERS = {
    "Accept": "application/json"
}

def test_verify_health_endpoint_of_rag_service():
    url = f"{BASE_URL}{HEALTH_ENDPOINT}"
    try:
        response = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        response.raise_for_status()
        data = response.json()

        # Assert response structure and status presence
        assert isinstance(data, dict), "Response should be a JSON object"
        assert "status" in data, "Response missing 'status' key"
        assert data["status"] in ["ok", "healthy"], "'status' should be 'ok' or 'healthy'"

    except requests.exceptions.Timeout:
        assert False, "Request timed out"
    except requests.exceptions.RequestException as e:
        assert False, f"Request failed: {e}"
    except ValueError:
        assert False, "Response is not valid JSON"


test_verify_health_endpoint_of_rag_service()
