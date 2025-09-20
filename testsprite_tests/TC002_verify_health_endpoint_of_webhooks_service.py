import requests

def test_tc002_verify_health_endpoint_webhooks_service():
    base_url = "http://localhost:8000"
    health_url = f"http://localhost:8001/health"
    headers = {
        "Accept": "application/json"
    }
    try:
        response = requests.get(health_url, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        # Validate response structure and key indicators of health
        assert response.status_code == 200, f"Expected status code 200, got {response.status_code}"
        assert isinstance(data, dict), "Response is not a JSON object"
        # Check expected keys or values if any exist that indicate WhatsApp integration and webhook processing health
        # Common health check pattern: "status": "ok" or similar
        assert "status" in data, "Missing 'status' key in health response"
        assert data["status"].lower() in ["ok", "healthy", "healthy"], f"Unexpected status: {data['status']}"
        # Additional specific checks could be added here if API returns details on whatsapp_integration or message_processing
    except requests.exceptions.RequestException as e:
        assert False, f"HTTP request to {health_url} failed: {e}"

test_tc002_verify_health_endpoint_webhooks_service()