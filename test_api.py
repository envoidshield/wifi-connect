#!/usr/bin/env python3
"""
Test script for WiFi Connect API endpoints
This script tests all the API endpoints to ensure they work correctly
"""

import requests
import json
import time
import sys
from typing import Dict, Any

# Configuration
BASE_URL = "http://localhost:8000"
TIMEOUT = 10

def print_status(message: str, status: str = "INFO"):
    """Print a formatted status message"""
    colors = {
        "INFO": "\033[94m",
        "SUCCESS": "\033[92m",
        "WARNING": "\033[93m",
        "ERROR": "\033[91m"
    }
    color = colors.get(status, "\033[0m")
    print(f"{color}[{status}]\033[0m {message}")

def test_endpoint(method: str, endpoint: str, data: Dict[str, Any] = None, expected_status: int = 200) -> bool:
    """Test a single API endpoint"""
    url = f"{BASE_URL}{endpoint}"
    
    try:
        if method.upper() == "GET":
            response = requests.get(url, timeout=TIMEOUT)
        elif method.upper() == "POST":
            response = requests.post(url, json=data, timeout=TIMEOUT)
        else:
            print_status(f"Unsupported method: {method}", "ERROR")
            return False
        
        if response.status_code == expected_status:
            print_status(f"✓ {method} {endpoint} - Status: {response.status_code}", "SUCCESS")
            try:
                result = response.json()
                print(f"   Response: {json.dumps(result, indent=2)}")
            except:
                print(f"   Response: {response.text}")
            return True
        else:
            print_status(f"✗ {method} {endpoint} - Expected: {expected_status}, Got: {response.status_code}", "ERROR")
            print(f"   Response: {response.text}")
            return False
            
    except requests.exceptions.ConnectionError:
        print_status(f"✗ {method} {endpoint} - Connection failed. Is the server running?", "ERROR")
        return False
    except requests.exceptions.Timeout:
        print_status(f"✗ {method} {endpoint} - Request timed out", "ERROR")
        return False
    except Exception as e:
        print_status(f"✗ {method} {endpoint} - Error: {str(e)}", "ERROR")
        return False

def main():
    """Run all API tests"""
    print("=" * 60)
    print("  WiFi Connect API Test Suite")
    print("=" * 60)
    print()
    
    # Check if server is running
    print_status("Testing server connectivity...", "INFO")
    if not test_endpoint("GET", "/health"):
        print_status("Server is not running. Please start the WiFi API server first.", "ERROR")
        print_status("Run: python3 wifi_api_server.py", "INFO")
        sys.exit(1)
    
    print()
    print_status("Starting API endpoint tests...", "INFO")
    print()
    
    # Test results tracking
    tests_passed = 0
    tests_failed = 0
    
    # Test 1: Health check
    print_status("Test 1: Health Check", "INFO")
    if test_endpoint("GET", "/health"):
        tests_passed += 1
    else:
        tests_failed += 1
    print()
    
    # Test 2: Get WiFi Direct status
    print_status("Test 2: Get WiFi Direct Status", "INFO")
    if test_endpoint("GET", "/get-wifi-direct"):
        tests_passed += 1
    else:
        tests_failed += 1
    print()
    
    # Test 3: List available networks
    print_status("Test 3: List Available Networks", "INFO")
    if test_endpoint("GET", "/list-networks"):
        tests_passed += 1
    else:
        tests_failed += 1
    print()
    
    # Test 4: List connected network
    print_status("Test 4: List Connected Network", "INFO")
    if test_endpoint("GET", "/list-connected"):
        tests_passed += 1
    else:
        tests_failed += 1
    print()
    
    # Test 5: List saved networks
    print_status("Test 5: List Saved Networks", "INFO")
    if test_endpoint("GET", "/list-saved"):
        tests_passed += 1
    else:
        tests_failed += 1
    print()
    
    # # Test 6: Set WiFi Direct (enable)
    # print_status("Test 6: Enable WiFi Direct", "INFO")
    # if test_endpoint("POST", "/set-wifi-direct", {"value": "true"}):
    #     tests_passed += 1
    # else:
    #     tests_failed += 1
    # print()
    #
    # # Wait a moment for WiFi Direct to activate
    # time.sleep(2)
    #
    # # Test 7: Get WiFi Direct status (should be enabled)
    # print_status("Test 7: Verify WiFi Direct Enabled", "INFO")
    # if test_endpoint("GET", "/get-wifi-direct"):
    #     tests_passed += 1
    # else:
    #     tests_failed += 1
    # print()
    #
    # # Test 8: Set WiFi Direct (disable)
    # print_status("Test 8: Disable WiFi Direct", "INFO")
    # if test_endpoint("POST", "/set-wifi-direct", {"value": "false"}):
    #     tests_passed += 1
    # else:
    #     tests_failed += 1
    # print()
    
    # Test 9: Test connection to non-existent network (should fail gracefully)
    print_status("Test 9: Test Connection to Non-existent Network", "INFO")
    if test_endpoint("POST", "/connect", {"ssid": "TEST_NETWORK_12345", "passphrase": "test123"}, 200):
        tests_passed += 1
    else:
        tests_failed += 1
    print()
    
    # Test 10: Test forget network (should work even if network doesn't exist)
    print_status("Test 10: Test Forget Network", "INFO")
    if test_endpoint("POST", "/forget-network", {"ssid": "TEST_NETWORK_12345"}):
        tests_passed += 1
    else:
        tests_failed += 1
    print()
    
    # # Test 11: Test forget all networks
    # print_status("Test 11: Test Forget All Networks", "INFO")
    # if test_endpoint("POST", "/forget-all", {}):
    #     tests_passed += 1
    # else:
    #     tests_failed += 1
    # print()
    
    # Summary
    print("=" * 60)
    print_status(f"Test Summary: {tests_passed} passed, {tests_failed} failed", "INFO")
    
    if tests_failed == 0:
        print_status("All tests passed! The WiFi API is working correctly.", "SUCCESS")
    else:
        print_status(f"{tests_failed} tests failed. Please check the errors above.", "WARNING")
    
    print()
    print_status("Note: Some tests may fail if WiFi hardware is not available or", "INFO")
    print_status("      if running without proper permissions.", "INFO")
    print("=" * 60)

if __name__ == "__main__":
    main()
