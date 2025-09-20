import requests

def test_verify_health_endpoint_web_search_service():
    base_url = "http://localhost:8003"
    health_url = f"{base_url}/health"
    headers = {
        "Accept": "application/json"
    }
    try:
        response = requests.get(health_url, headers=headers, timeout=30)
        response.raise_for_status()
        json_response = response.json()
        # Validate expected keys and values indicating Playwright and scraping are operational
        assert isinstance(json_response, dict), "Response is not a JSON object"
        # Typical health checks often include 'status' or similar keys
        assert "status" in json_response, "'status' key missing in health response"
        assert json_response["status"].lower() == "ok" or json_response["status"].lower() == "healthy", "Health status not OK"
        # Additional checks could be included if schema was specified
    except requests.RequestException as e:
        assert False, f"Request to web search health endpoint failed: {e}"

test_verify_health_endpoint_web_search_service()