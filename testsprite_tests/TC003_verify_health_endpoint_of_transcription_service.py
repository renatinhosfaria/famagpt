import requests

def test_tc003_verify_health_endpoint_transcription_service():
    base_url = "http://localhost:8002"
    health_url = f"{base_url}/health"
    headers = {
        "Accept": "application/json"
    }
    try:
        response = requests.get(health_url, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        # Assert HTTP status code is 200
        assert response.status_code == 200
        
        # Validate expected keys in health response, assuming typical health check JSON structure
        # For transcription service, checking that relevant keys exist and are True or "ok"
        # Since PRD does not define exact schema for health response, we assume standard keys
        
        # Common checks could be "status" == "ok" or "service" == "transcription"
        # and checks that transcription and file_processing subsystems are healthy
        assert "status" in data
        assert data["status"].lower() in ("ok", "healthy", "success")
        
        # Additional keys based on core features (best guess)
        # e.g., "audio_transcription" and "file_processing" keys might be bool or string status
        if "audio_transcription" in data:
            assert str(data["audio_transcription"]).lower() in ("ok", "healthy", "true", "running", "success")
        if "file_processing" in data:
            assert str(data["file_processing"]).lower() in ("ok", "healthy", "true", "running", "success")
            
    except requests.Timeout:
        assert False, "Request to transcription service health endpoint timed out."
    except requests.RequestException as e:
        assert False, f"Request failed: {e}"
    except ValueError:
        assert False, "Response is not valid JSON."

test_tc003_verify_health_endpoint_transcription_service()