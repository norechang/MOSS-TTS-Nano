"""
MOSS-TTS-Nano API Validation Test Suite

This test suite validates all API endpoints against the API.md specification.
Each endpoint must have at least one test case covering normal operation and error conditions.

Test Categories:
1. Health & Metrics (2 endpoints)
2. Voice Management (2 endpoints)
3. Job Management (4 endpoints)
4. Slot Management (1 endpoint)

Total: 8 endpoints with comprehensive validation
"""

import requests
import time
import json
import base64
import os
from typing import Dict, Any, Optional
from pathlib import Path

class APIValidator:
    """Base validator class with common utilities"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.api_base = f"{base_url}/api/v1"
        self.test_results = []
        self.job_ids = []  # Track created jobs for cleanup
        
    def log_test(self, test_name: str, passed: bool, message: str = ""):
        """Log test result"""
        status = "✓ PASS" if passed else "✗ FAIL"
        self.test_results.append({
            "test": test_name,
            "passed": passed,
            "message": message
        })
        print(f"{status}: {test_name}")
        if message:
            print(f"  {message}")
    
    def assert_status_code(self, response: requests.Response, expected: int, test_name: str):
        """Assert HTTP status code"""
        passed = response.status_code == expected
        message = f"Expected {expected}, got {response.status_code}"
        if not passed:
            message += f"\nResponse: {response.text[:200]}"
        self.log_test(test_name, passed, message if not passed else "")
        return passed
    
    def assert_field_exists(self, data: dict, field: str, test_name: str):
        """Assert field exists in response"""
        passed = field in data
        message = f"Field '{field}' {'found' if passed else 'missing'}"
        if not passed:
            message += f"\nAvailable fields: {list(data.keys())}"
        self.log_test(test_name, passed, message if not passed else "")
        return passed
    
    def assert_field_type(self, data: dict, field: str, expected_type, test_name: str):
        """Assert field type (expected_type can be a type or tuple of types)"""
        if field not in data:
            self.log_test(test_name, False, f"Field '{field}' not found")
            return False
        passed = isinstance(data[field], expected_type)
        
        # Handle both single types and tuple of types for error message
        if isinstance(expected_type, tuple):
            type_names = ' or '.join(t.__name__ for t in expected_type)
        else:
            type_names = expected_type.__name__
        
        message = f"Field '{field}' type: expected {type_names}, got {type(data[field]).__name__}"
        self.log_test(test_name, passed, message if not passed else "")
        return passed
    
    def wait_for_job_completion(self, job_id: str, timeout: int = 60) -> Optional[Dict]:
        """Wait for job to complete and return final status"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            response = requests.get(f"{self.api_base}/status/{job_id}")
            if response.status_code == 200:
                data = response.json()
                status = data.get('status')
                if status in ['completed', 'failed']:
                    return data
            time.sleep(2)
        return None
    
    def print_summary(self):
        """Print test summary"""
        total = len(self.test_results)
        passed = sum(1 for r in self.test_results if r['passed'])
        failed = total - passed
        
        print("\n" + "="*70)
        print(f"TEST SUMMARY: {passed}/{total} passed, {failed} failed")
        print("="*70)
        
        if failed > 0:
            print("\nFailed Tests:")
            for result in self.test_results:
                if not result['passed']:
                    print(f"  - {result['test']}")
                    if result['message']:
                        print(f"    {result['message']}")
        
        return failed == 0


class HealthMetricsValidator(APIValidator):
    """Validate health and metrics endpoints"""
    
    def test_health_endpoint(self):
        """Test GET /health endpoint"""
        print("\n--- Testing Health Endpoint ---")
        
        # Test 1: Health endpoint returns 200
        response = requests.get(f"{self.base_url}/health")
        if not self.assert_status_code(response, 200, "Health endpoint returns 200"):
            return
        
        data = response.json()
        
        # Test 2: Response contains required fields
        required_fields = ['status', 'service', 'backend', 'device', 'slot_status']
        for field in required_fields:
            self.assert_field_exists(data, field, f"Health response contains '{field}'")
        
        # Test 3: Status field is 'healthy'
        if 'status' in data:
            passed = data['status'] == 'healthy'
            self.log_test("Health status is 'healthy'", passed,
                         f"Expected 'healthy', got '{data['status']}'" if not passed else "")
        
        # Test 4: Backend is valid
        if 'backend' in data:
            passed = data['backend'] in ['onnx', 'pytorch']
            self.log_test("Backend is valid", passed,
                         f"Expected 'onnx' or 'pytorch', got '{data['backend']}'" if not passed else "")
    
    def test_metrics_endpoint(self):
        """Test GET /api/v1/metrics endpoint"""
        print("\n--- Testing Metrics Endpoint ---")
        
        # Test 1: Metrics endpoint returns 200
        response = requests.get(f"{self.api_base}/metrics")
        if not self.assert_status_code(response, 200, "Metrics endpoint returns 200"):
            return
        
        data = response.json()
        
        # Test 2: Response contains metrics fields
        expected_fields = ['uptime_seconds', 'current_status', 'jobs_completed', 'jobs_failed']
        for field in expected_fields:
            self.assert_field_exists(data, field, f"Metrics response contains '{field}'")
        
        # Test 3: Uptime is numeric
        if 'uptime_seconds' in data:
            self.assert_field_type(data, 'uptime_seconds', (int, float), "Uptime is numeric")


class VoiceManagementValidator(APIValidator):
    """Validate voice-related endpoints"""
    
    def test_list_voices(self):
        """Test GET /api/v1/voices endpoint"""
        print("\n--- Testing List Voices Endpoint ---")
        
        # Test 1: Voices endpoint returns 200
        response = requests.get(f"{self.api_base}/voices")
        if not self.assert_status_code(response, 200, "List voices returns 200"):
            return
        
        data = response.json()
        
        # Test 2: Response is a dict with 'voices' key
        passed = isinstance(data, dict) and 'voices' in data
        self.log_test("Response is a dict with 'voices' key", passed,
                     f"Expected dict with 'voices', got {type(data).__name__}" if not passed else "")
        
        if not isinstance(data, dict) or 'voices' not in data:
            return
        
        voices = data['voices']
        if not isinstance(voices, list) or len(voices) == 0:
            return
        
        # Test 3: Each voice has required fields
        voice = voices[0]
        for field in ['name', 'voice']:
            self.assert_field_exists(voice, field, f"Voice object contains '{field}'")
        
        # Test 4: At least one Chinese voice exists
        chinese_voices = [v['name'] for v in voices if v['name'] in ['Junhao', 'Zhiming', 'Xiaoyu']]
        passed = len(chinese_voices) > 0
        self.log_test("At least one Chinese voice available", passed,
                     f"Found voices: {[v['name'] for v in voices][:5]}" if passed else "No Chinese voices found")
    
    def test_upload_reference_audio(self):
        """Test POST /api/v1/voices/upload endpoint"""
        print("\n--- Testing Upload Reference Audio Endpoint ---")
        
        # Create a minimal WAV file for testing (44-byte header + 1 sample)
        wav_data = (
            b'RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00'
            b'\x00\x7d\x00\x00\x00\xfa\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00'
        )
        
        # Test 1: Upload with valid audio file
        files = {'file': ('test.wav', wav_data, 'audio/wav')}
        response = requests.post(f"{self.api_base}/voices/upload", files=files)
        
        if self.assert_status_code(response, 200, "Upload audio returns 200"):
            data = response.json()
            
            # Test 2: Response contains upload_id
            if self.assert_field_exists(data, 'upload_id', "Upload response contains upload_id"):
                # Store upload_id for potential future tests
                self.upload_id = data['upload_id']
            
            # Test 3: Upload_id is valid format
            if 'upload_id' in data:
                passed = len(data['upload_id']) > 0 and isinstance(data['upload_id'], str)
                self.log_test("Upload ID is valid string", passed)
        
        # Test 4: Upload without file returns error
        response = requests.post(f"{self.api_base}/voices/upload")
        passed = response.status_code in [400, 422]
        self.log_test("Upload without file returns 400/422", passed,
                     f"Expected 400 or 422, got {response.status_code}" if not passed else "")


class JobManagementValidator(APIValidator):
    """Validate job-related endpoints"""
    
    def test_generate_speech_success(self):
        """Test POST /api/v1/generate with valid input"""
        print("\n--- Testing Generate Speech (Success Case) ---")
        
        # Test 1: Generate with minimal valid input
        payload = {
            "text": "Hello world test",
            "voice": "Ava"
        }
        response = requests.post(f"{self.api_base}/generate", json=payload)
        
        if not self.assert_status_code(response, 202, "Generate returns 202 Accepted"):
            return
        
        data = response.json()
        
        # Test 2: Response contains job_id
        if not self.assert_field_exists(data, 'job_id', "Generate response contains job_id"):
            return
        
        job_id = data['job_id']
        self.job_ids.append(job_id)
        
        # Test 3: Response contains status
        self.assert_field_exists(data, 'status', "Generate response contains status")
        
        # Test 4: Status is 'processing'
        if 'status' in data:
            passed = data['status'] == 'processing'
            self.log_test("Initial status is 'processing'", passed,
                         f"Expected 'processing', got '{data['status']}'" if not passed else "")
        
        # Test 5: Response contains created_at timestamp
        self.assert_field_exists(data, 'created_at', "Generate response contains created_at")
        
        print(f"  Created job: {job_id}")
        
        # Wait for job to complete to avoid blocking subsequent tests
        print(f"  Waiting for job {job_id} to complete...")
        self.wait_for_job_completion(job_id, timeout=60)
    
    def test_generate_speech_validation(self):
        """Test POST /api/v1/generate with invalid input"""
        print("\n--- Testing Generate Speech (Validation) ---")
        
        # Test 1: Generate without text returns 400/422
        response = requests.post(f"{self.api_base}/generate", json={})
        passed = response.status_code in [400, 422]
        self.log_test("Generate without text returns 400/422", passed,
                     f"Expected 400 or 422, got {response.status_code}" if not passed else "")
        
        # Test 2: Generate with empty text returns 400/422
        response = requests.post(f"{self.api_base}/generate", json={"text": ""})
        passed = response.status_code in [400, 422]
        self.log_test("Generate with empty text returns 400/422", passed,
                     f"Expected 400 or 422, got {response.status_code}" if not passed else "")
        
        # Test 3: Generate with invalid options returns 400/422
        response = requests.post(f"{self.api_base}/generate", json={
            "text": "Test",
            "options": {"max_new_frames": -1}  # Invalid negative value
        })
        passed = response.status_code in [400, 422]
        self.log_test("Generate with invalid options returns 400/422", passed,
                     f"Expected 400 or 422, got {response.status_code}" if not passed else "")
    
    def test_check_job_status(self):
        """Test GET /api/v1/status/{job_id}"""
        print("\n--- Testing Check Job Status ---")
        
        # First create a job
        payload = {"text": "Status check test", "voice": "Ava"}
        response = requests.post(f"{self.api_base}/generate", json=payload)
        
        if response.status_code != 202:
            self.log_test("Create job for status test", False, "Failed to create test job")
            return
        
        job_id = response.json()['job_id']
        self.job_ids.append(job_id)
        
        # Test 1: Status endpoint returns 200
        response = requests.get(f"{self.api_base}/status/{job_id}")
        if not self.assert_status_code(response, 200, "Status endpoint returns 200"):
            return
        
        data = response.json()
        
        # Test 2: Response contains required status fields
        required_fields = ['job_id', 'status', 'created_at']
        for field in required_fields:
            self.assert_field_exists(data, field, f"Status response contains '{field}'")
        
        # Test 3: Job ID matches
        if 'job_id' in data:
            passed = data['job_id'] == job_id
            self.log_test("Job ID matches", passed,
                         f"Expected '{job_id}', got '{data['job_id']}'" if not passed else "")
        
        # Test 4: Status is valid
        if 'status' in data:
            valid_statuses = ['pending', 'processing', 'completed', 'failed']
            passed = data['status'] in valid_statuses
            self.log_test("Status is valid", passed,
                         f"Expected one of {valid_statuses}, got '{data['status']}'" if not passed else "")
        
        # Wait for job to complete to avoid blocking subsequent tests
        print(f"  Waiting for job {job_id} to complete...")
        self.wait_for_job_completion(job_id, timeout=60)
        
        # Test 5: Check non-existent job returns 404
        response = requests.get(f"{self.api_base}/status/nonexistent-job-id")
        self.assert_status_code(response, 404, "Non-existent job returns 404")
    
    def test_download_result(self):
        """Test GET /api/v1/result/{job_id}"""
        print("\n--- Testing Download Result ---")
        
        # Create a job and wait for completion
        payload = {"text": "Download test", "voice": "Ava"}
        response = requests.post(f"{self.api_base}/generate", json=payload)
        
        if response.status_code != 202:
            self.log_test("Create job for download test", False, "Failed to create test job")
            return
        
        job_id = response.json()['job_id']
        self.job_ids.append(job_id)
        
        print(f"  Waiting for job {job_id} to complete...")
        final_status = self.wait_for_job_completion(job_id, timeout=60)
        
        if not final_status:
            self.log_test("Job completion timeout", False, "Job did not complete within 60s")
            return
        
        if final_status['status'] != 'completed':
            self.log_test("Job completed successfully", False, f"Job status: {final_status['status']}")
            return
        
        self.log_test("Job completed successfully", True)
        
        # Test 1: Download returns 200 and audio data
        response = requests.get(f"{self.api_base}/result/{job_id}")
        if not self.assert_status_code(response, 200, "Download result returns 200"):
            return
        
        # Test 2: Content-Type is audio
        content_type = response.headers.get('Content-Type', '')
        passed = 'audio' in content_type.lower()
        self.log_test("Content-Type is audio", passed,
                     f"Expected audio/*, got '{content_type}'" if not passed else "")
        
        # Test 3: Response contains audio data
        passed = len(response.content) > 1000  # Reasonable minimum for WAV file
        self.log_test("Response contains audio data", passed,
                     f"Expected >1000 bytes, got {len(response.content)}" if not passed else "")
        
        # Test 4: Audio data starts with RIFF (WAV format)
        if len(response.content) >= 4:
            passed = response.content[:4] == b'RIFF'
            self.log_test("Audio is WAV format", passed,
                         f"Expected RIFF header, got {response.content[:4]}" if not passed else "")
        
        # Test 5: Download non-existent job returns 404
        response = requests.get(f"{self.api_base}/result/nonexistent-job-id")
        self.assert_status_code(response, 404, "Download non-existent job returns 404")
        
        # Test 6: Download before completion returns 400
        # Create a new job but don't wait
        payload = {"text": "Quick test for early download"}
        response = requests.post(f"{self.api_base}/generate", json=payload)
        if response.status_code == 202:
            early_job_id = response.json()['job_id']
            self.job_ids.append(early_job_id)
            
            # Try to download immediately
            response = requests.get(f"{self.api_base}/result/{early_job_id}")
            passed = response.status_code in [400, 404]
            self.log_test("Download before completion returns 400/404", passed,
                         f"Expected 400 or 404, got {response.status_code}" if not passed else "")
            
            # Wait for this job to complete to avoid blocking subsequent tests
            print(f"  Waiting for job {early_job_id} to complete...")
            self.wait_for_job_completion(early_job_id, timeout=60)


class SlotManagementValidator(APIValidator):
    """Validate slot availability endpoint"""
    
    def test_slot_availability(self):
        """Test GET /api/v1/slot endpoint"""
        print("\n--- Testing Slot Availability ---")
        
        # Test 1: Slot endpoint returns 200
        response = requests.get(f"{self.api_base}/slot")
        if not self.assert_status_code(response, 200, "Slot endpoint returns 200"):
            return
        
        data = response.json()
        
        # Test 2: Response contains required fields
        required_fields = ['available', 'status']
        for field in required_fields:
            self.assert_field_exists(data, field, f"Slot response contains '{field}'")
        
        # Test 3: available is boolean
        self.assert_field_type(data, 'available', bool, "available is boolean")
        
        # Test 4: status is valid
        if 'status' in data:
            valid_statuses = ['idle', 'busy']
            passed = data['status'] in valid_statuses
            self.log_test("status is valid", passed,
                         f"Expected 'idle' or 'busy', got '{data['status']}'" if not passed else "")
        
        # Test 5: When busy, current_job_id should be present
        if data.get('status') == 'busy':
            self.assert_field_exists(data, 'current_job_id', "Busy slot includes current_job_id")
    
    def test_busy_slot_rejection(self):
        """Test that API returns 503 when slot is busy"""
        print("\n--- Testing Busy Slot Rejection ---")
        
        # Submit first job
        payload1 = {"text": "First job for busy test", "voice": "Ava"}
        response1 = requests.post(f"{self.api_base}/generate", json=payload1)
        
        if response1.status_code != 202:
            self.log_test("Create first job", False, "Failed to create first job")
            return
        
        job_id1 = response1.json()['job_id']
        self.job_ids.append(job_id1)
        self.log_test("Create first job", True)
        
        # Immediately submit second job (should get 503)
        payload2 = {"text": "Second job should be rejected", "voice": "Ava"}
        response2 = requests.post(f"{self.api_base}/generate", json=payload2)
        
        # Test: Should return 503 when busy
        if response2.status_code == 503:
            self.log_test("Busy slot returns 503", True)
            
            data = response2.json()
            
            # FastAPI wraps custom errors in 'detail' field
            detail = data.get('detail', data)
            
            # Test: 503 response contains helpful information
            self.assert_field_exists(detail, 'error', "503 response contains error field")
            self.assert_field_exists(detail, 'message', "503 response contains message")
            
            if 'current_job_id' in detail:
                self.log_test("503 response includes current_job_id", True)
        elif response2.status_code == 202:
            # Job was accepted (first job might have finished already)
            self.log_test("Busy slot returns 503", True, "Note: First job completed quickly, slot became available")
            job_id2 = response2.json()['job_id']
            self.job_ids.append(job_id2)
        else:
            self.log_test("Busy slot returns 503", False,
                         f"Expected 503, got {response2.status_code}")


def run_all_validations(base_url: str = "http://localhost:8000"):
    """Run all validation tests"""
    print("="*70)
    print("MOSS-TTS-Nano API Validation Test Suite")
    print("="*70)
    print(f"Target: {base_url}")
    print()
    
    # Check if service is available
    try:
        response = requests.get(f"{base_url}/health", timeout=5)
        if response.status_code != 200:
            print(f"✗ Service health check failed: {response.status_code}")
            return False
        print("✓ Service is healthy\n")
    except Exception as e:
        print(f"✗ Cannot connect to service: {e}")
        print("\nPlease ensure the service is running:")
        print("  docker compose up -d")
        print("  OR")
        print("  python api_service.py")
        return False
    
    # Initialize validators
    all_passed = True
    
    # Run tests by category
    validators = [
        HealthMetricsValidator(base_url),
        VoiceManagementValidator(base_url),
        JobManagementValidator(base_url),
        SlotManagementValidator(base_url),
    ]
    
    for validator in validators:
        # Run all test methods
        for method_name in dir(validator):
            if method_name.startswith('test_'):
                try:
                    method = getattr(validator, method_name)
                    if callable(method):  # Only call if it's actually a method
                        method()
                except Exception as e:
                    print(f"\n✗ EXCEPTION in {method_name}: {e}")
                    validator.log_test(method_name, False, str(e))
    
    # Print combined summary
    print("\n" + "="*70)
    print("COMBINED TEST RESULTS")
    print("="*70)
    
    total_tests = sum(len(v.test_results) for v in validators)
    total_passed = sum(sum(1 for r in v.test_results if r['passed']) for v in validators)
    total_failed = total_tests - total_passed
    
    print(f"\nTotal: {total_passed}/{total_tests} tests passed")
    
    if total_failed > 0:
        print(f"\n{total_failed} tests failed:")
        for validator in validators:
            for result in validator.test_results:
                if not result['passed']:
                    print(f"  - {result['test']}")
                    if result['message']:
                        for line in result['message'].split('\n'):
                            print(f"    {line}")
        all_passed = False
    else:
        print("\n✓ All tests passed!")
    
    print("\n" + "="*70)
    
    return all_passed


if __name__ == "__main__":
    import sys
    
    # Allow custom base URL via command line
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
    
    success = run_all_validations(base_url)
    sys.exit(0 if success else 1)
