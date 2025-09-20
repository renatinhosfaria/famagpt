import requests

def test_TC005_verify_health_endpoint_of_memory_service():
    base_url = "http://localhost:8004"
    url = f"{base_url}/health"
    headers = {
        "Accept": "application/json"
    }
    timeout = 30
    try:
        response = requests.get(url, headers=headers, timeout=timeout)
    except requests.RequestException as e:
        assert False, f"Request to memory service /health endpoint failed: {e}"
    assert response.status_code == 200, f"Expected status code 200 but got {response.status_code}"
    try:
        data = response.json()
    except ValueError:
        assert False, "Response is not valid JSON"
    # Validate likely expected keys and values in health check
    # Assuming typical health structure might include: status, uptime, memory_usage, etc.
    assert "status" in data, "'status' key missing in health response"
    assert data["status"] in ["ok", "healthy", "success"], f"Unexpected health status value: {data['status']}"
    # Optionally check presence of metrics
    # Since no exact schema provided, just check keys that might exist
    expected_keys = ["status", "uptime", "memory"]
    found_keys = any(key in data for key in expected_keys)
    assert found_keys, "Health response missing expected health metric keys"
    
test_TC005_verify_health_endpoint_of_memory_service()