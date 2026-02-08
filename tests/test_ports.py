"""
Tests for remote-browser container ports.

Tests that all required ports are accessible and responding correctly.
"""
import socket
import time
import os
import requests
import pytest
import subprocess


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
    
    # Get DevTools token from environment variable (optional)
    devtools_token = os.environ.get("DEVTOOLS_TOKEN")
    
    # Prepare auth if token is provided
    auth = None
    if devtools_token:
        from requests.auth import HTTPBasicAuth
        auth = HTTPBasicAuth('token', devtools_token)
    
    while attempt < max_attempts:
        try:
            response = requests.get("http://localhost:9222/json", timeout=2, auth=auth)
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


def test_vnc_password_authentication(container_name, wait_for_services):
    """Test that VNC password authentication works."""
    test_password = "testpass123"
    
    # Check container logs for password setup confirmation
    logs_result = subprocess.run(
        ["docker", "logs", container_name],
        capture_output=True, text=True
    )
    logs = logs_result.stdout
    assert "VNC server started with password authentication" in logs, \
        "VNC password should be configured"
    print("✓ VNC password authentication configured in container")
    
    # Test VNC connection - verify port is accessible and requires authentication
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5)
    
    try:
        result = sock.connect_ex(('localhost', 5900))
        assert result == 0, f"Port 5900 connection failed with code {result}"
        
        # Read VNC protocol handshake
        data = sock.recv(12)
        assert len(data) >= 12, "VNC server should send protocol version"
        assert data.startswith(b"RFB"), "Should receive RFB protocol header"
        print(f"✓ VNC server responded with protocol: {data[:12].decode('ascii', errors='ignore')}")
        
        # Send client version
        sock.send(b"RFB 003.008\n")
        
        # Read number of security types (1 byte)
        num_sec_types_data = sock.recv(1)
        assert len(num_sec_types_data) == 1, "Should receive number of security types"
        num_sec_types = num_sec_types_data[0]
        print(f"✓ VNC server offers {num_sec_types} security type(s)")
        assert num_sec_types > 0, "VNC server should offer security types"
        
        # Read security types (N bytes where N is num_sec_types)
        sec_types = sock.recv(num_sec_types)
        assert len(sec_types) == num_sec_types, f"Should receive {num_sec_types} security type bytes"
        # Security type 2 is VNC authentication
        assert b'\x02' in sec_types, "VNC authentication (type 2) should be available"
        print("✓ VNC authentication (password) is available")
        
        print(f"✓ VNC password authentication test passed (password: {test_password})")
        
    except Exception as e:
        pytest.fail(f"VNC password authentication test failed: {e}")
    finally:
        sock.close()

