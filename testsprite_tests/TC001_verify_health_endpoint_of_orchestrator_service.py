import requests

def test_verify_health_endpoint_of_orchestrator_service():
    url = "http://localhost:8000/health"
    headers = {
        "Accept": "application/json"
    }
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
    except requests.RequestException as e:
        assert False, f"Request to orchestrator health endpoint failed: {e}"

    try:
        data = response.json()
    except ValueError:
        assert False, "Response is not valid JSON"

    # Check status code is 200
    assert response.status_code == 200, f"Expected status code 200, got {response.status_code}"

    # Validate 'status' field
    status = data.get("status", "").lower()
    assert status in ["ok", "healthy", "success"], f"Unexpected status value: {status}"

test_verify_health_endpoint_of_orchestrator_service()
