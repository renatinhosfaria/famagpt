import requests

BASE_URL = "http://localhost:8007"
TIMEOUT = 30

def test_tc008_verify_health_endpoint_of_specialist_service():
    url = f"{BASE_URL}/health"
    try:
        response = requests.get(url, timeout=TIMEOUT)
        assert response.status_code == 200, f"Expected status code 200, got {response.status_code}"
        data = response.json()
        # Basic checks that indicate service and dependencies are operational
        assert "status" in data, "Response JSON missing 'status' key"
        assert data["status"].lower() in ("ok", "healthy", "healthy_services"), f"Unexpected health status: {data['status']}"
        # Optionally, if details about dependencies are returned, check them
        if "dependencies" in data:
            assert isinstance(data["dependencies"], dict), "'dependencies' should be a dictionary"
            for dep, state in data["dependencies"].items():
                assert state.lower() in ("ok", "healthy", "up"), f"Dependency {dep} unhealthy: {state}"
    except requests.RequestException as e:
        assert False, f"Request to health endpoint failed: {e}"

test_tc008_verify_health_endpoint_of_specialist_service()