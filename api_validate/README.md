# API Validation Test Suite

This directory contains the validation test suite for the MOSS-TTS-Nano API service. All tests are based on the [API.md](../API.md) specification.

## Overview

The test suite validates:
- **8 API endpoints** with comprehensive test coverage
- **Request/response schemas** match specification
- **Error handling** for invalid inputs
- **Edge cases** like busy slots, non-existent jobs
- **Data formats** (audio files, timestamps, etc.)

## Test Coverage

### Health & Metrics (2 endpoints)
- `GET /health` - Service health check
  - Returns 200 with health status
  - Contains required fields (status, backend, device, slot_status)
  - Status is 'healthy'
  - Backend is valid (onnx/pytorch)

- `GET /api/v1/metrics` - Service metrics
  - Returns 200 with metrics
  - Contains uptime, job counts
  - Numeric values are correct types

### Voice Management (2 endpoints)
- `GET /api/v1/voices` - List available voices
  - Returns 200 with voice list
  - Each voice has name and description
  - At least one Chinese voice available

- `POST /api/v1/voices/upload` - Upload reference audio
  - Accepts valid WAV files
  - Returns upload_id
  - Rejects requests without file

### Job Management (4 endpoints)
- `POST /api/v1/generate` - Generate speech
  - Accepts valid text and voice
  - Returns 202 with job_id
  - Returns 503 when slot busy
  - Returns 400/422 for invalid input
  - Validates empty text
  - Validates invalid options

- `GET /api/v1/status/{job_id}` - Check job status
  - Returns 200 for existing jobs
  - Contains job_id, status, timestamps
  - Status values are valid (pending/processing/completed/failed)
  - Returns 404 for non-existent jobs

- `GET /api/v1/result/{job_id}` - Download audio result
  - Returns 200 with audio data for completed jobs
  - Content-Type is audio/*
  - Audio data is WAV format (RIFF header)
  - Audio file size is reasonable (>1KB)
  - Returns 404 for non-existent jobs
  - Returns 400/404 before job completion

### Slot Management (1 endpoint)
- `GET /api/v1/slot` - Check slot availability
  - Returns 200 with slot status
  - slot_available is boolean
  - slot_status is valid (idle/busy)
  - Includes current_job_id when busy

### Busy Slot Behavior
- Returns 503 when submitting job while slot busy
- 503 response includes error, message, current_job_id
- Slot becomes available after job completion

## Running Tests

### Prerequisites

Ensure the API service is running:

```bash
# Option 1: Docker
docker compose up -d

# Option 2: Direct Python
python api_service.py
```

### Run All Tests

```bash
cd api_validate
python run_validation.py
```

### Run with Custom URL

```bash
python run_validation.py http://localhost:8002
```

### Expected Output

```
======================================================================
MOSS-TTS-Nano API Validation Test Suite
======================================================================
Target: http://localhost:8000

✓ Service is healthy

--- Testing Health Endpoint ---
✓ PASS: Health endpoint returns 200
✓ PASS: Health response contains 'status'
✓ PASS: Health response contains 'service'
✓ PASS: Health response contains 'backend'
✓ PASS: Health response contains 'device'
✓ PASS: Health response contains 'slot_status'
✓ PASS: Health status is 'healthy'
✓ PASS: Backend is valid

... (more test output) ...

======================================================================
COMBINED TEST RESULTS
======================================================================

Total: 45/45 tests passed

✓ All tests passed!

======================================================================
```

## Test Structure

### `run_validation.py`
Main test runner that validates all endpoints against API.md specification.

**Test Categories:**
- `HealthMetricsValidator` - Health and metrics endpoints
- `VoiceManagementValidator` - Voice listing and upload
- `JobManagementValidator` - Job submission, status, and results
- `SlotManagementValidator` - Slot availability and busy handling

### Test Methods

Each validator class contains test methods following the pattern:
- `test_<feature>()` - Tests normal operation
- `test_<feature>_validation()` - Tests error cases
- `test_<feature>_edge_cases()` - Tests edge cases

### Assertion Helpers

- `assert_status_code()` - Validate HTTP status code
- `assert_field_exists()` - Check response field presence
- `assert_field_type()` - Validate field data type
- `wait_for_job_completion()` - Poll job until completion

## Continuous Integration

### Pre-commit Hook

Add to `.git/hooks/pre-commit`:

```bash
#!/bin/bash
echo "Running API validation tests..."
cd api_validate
python run_validation.py
if [ $? -ne 0 ]; then
  echo "API validation failed. Commit aborted."
  exit 1
fi
```

### GitHub Actions

```yaml
name: API Validation
on: [push, pull_request]
jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Start API service
        run: docker compose up -d
      - name: Wait for service
        run: sleep 10
      - name: Run validation tests
        run: cd api_validate && python run_validation.py
```

## Adding New Tests

When adding new API endpoints or features:

1. **Update API.md** with the specification
2. **Add test method** in appropriate validator class
3. **Cover normal operation** - at least one happy path test
4. **Cover error cases** - test validation and edge cases
5. **Run full suite** - ensure no regressions

### Example: Adding Test for New Endpoint

```python
class JobManagementValidator(APIValidator):
    def test_cancel_job(self):
        """Test POST /api/v1/cancel/{job_id}"""
        print("\n--- Testing Cancel Job ---")
        
        # Create a job
        response = requests.post(f"{self.api_base}/generate", 
                                json={"text": "Test"})
        job_id = response.json()['job_id']
        
        # Test cancel endpoint
        response = requests.post(f"{self.api_base}/cancel/{job_id}")
        self.assert_status_code(response, 200, "Cancel returns 200")
        
        # Verify job is cancelled
        status = requests.get(f"{self.api_base}/status/{job_id}").json()
        passed = status['status'] == 'cancelled'
        self.log_test("Job status is cancelled", passed)
```

## Troubleshooting

### Service Not Available

```
✗ Cannot connect to service: Connection refused
```

**Solution:** Start the API service first:
```bash
docker compose up -d
# Wait 10 seconds for startup
sleep 10
python run_validation.py
```

### Tests Timing Out

```
Job completion timeout
```

**Causes:**
- Backend overloaded
- GPU not available (PyTorch backend)
- Model loading issues

**Solution:**
- Check service logs: `docker compose logs -f`
- Verify backend in `config.yaml` matches hardware
- Increase timeout in `wait_for_job_completion(timeout=120)`

### Failed Validation Tests

```
✗ FAIL: Generate without text returns 400/422
  Expected 400 or 422, got 500
```

**Action:**
1. This indicates API behavior differs from specification
2. Check if bug in implementation or outdated test
3. Fix implementation or update API.md + test accordingly
4. **Never ignore failed validation tests**

### Port Conflicts

```
Cannot connect to service: Connection refused
```

If service is running on different port:
```bash
python run_validation.py http://localhost:8002
```

## Test Maintenance

### When to Update Tests

- ✅ API.md specification changes
- ✅ New endpoints added
- ✅ Request/response schemas modified
- ✅ Error handling behavior changes
- ✅ New validation rules added

### When NOT to Update Tests

- ❌ Implementation details (not visible to API consumers)
- ❌ Performance optimizations (unless affecting timeout)
- ❌ Internal code refactoring
- ❌ Logging or monitoring changes

## Coverage Report

Run with coverage:

```bash
pip install coverage
coverage run run_validation.py
coverage report
```

## Performance Testing

For load/stress testing, use separate tools:
- `locust` for load testing
- `ab` (Apache Bench) for simple benchmarks
- `k6` for complex scenarios

This suite focuses on **functional validation**, not performance.

## Relationship to API.md

**API.md is the source of truth.** This test suite must:
1. ✅ Validate every endpoint in API.md
2. ✅ Test all documented request parameters
3. ✅ Verify all documented response fields
4. ✅ Check all documented status codes
5. ✅ Validate all documented error cases

If tests fail but implementation is correct, **update the tests and API.md** together.

## Contributing

When contributing tests:
1. Follow existing test patterns
2. Add docstrings explaining what is tested
3. Use descriptive test names
4. Include both success and failure cases
5. Run full suite before submitting

## License

Follow the main MOSS-TTS-Nano project license.
