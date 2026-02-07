"""
Tests for remote-browser container ports.

Tests that all required ports are accessible and responding correctly.
"""
import socket
import time
import requests
import pytest


@pytest.fixture(scope="module")
def container_name():
    """Container name for testing."""
    return "test-remote-browser"


@pytest.fixture(scope="module")
def wait_for_services():
    """Wait for services to start."""
    time.sleep(10)


def test_port_9222_chrome_devtools(container_name, wait_for_services):
    """Test that Chrome DevTools port 9222 is accessible."""
    max_attempts = 30
    attempt = 0
    
    while attempt < max_attempts:
        try:
            response = requests.get("http://localhost:9222/json", timeout=2)
            assert response.status_code == 200, f"Expected 200, got {response.status_code}"
            assert len(response.json()) >= 0, "Response should be valid JSON"
            print(f"✓ Port 9222 is accessible")
            print(f"  Response preview: {response.text[:200]}")
            return
        except (requests.exceptions.RequestException, AssertionError) as e:
            attempt += 1
            if attempt >= max_attempts:
                pytest.fail(f"Port 9222 failed to respond after {max_attempts} attempts: {e}")
            time.sleep(2)


def test_port_5900_vnc_server(container_name, wait_for_services):
    """Test that VNC server port 5900 is accessible."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5)
    
    try:
        result = sock.connect_ex(('localhost', 5900))
        assert result == 0, f"Port 5900 connection failed with code {result}"
        print("✓ Port 5900 is accessible")
    except Exception as e:
        pytest.fail(f"Port 5900 is not accessible: {e}")
    finally:
        sock.close()

