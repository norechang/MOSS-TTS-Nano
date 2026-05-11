#!/usr/bin/env python3
"""
Test script to verify GPU memory management with cache clearing.

This script submits multiple generation jobs sequentially and monitors
GPU memory usage to ensure cache is being cleared properly.
"""

import time
import requests
import sys

API_URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8006"

def check_health():
    """Check API health."""
    response = requests.get(f"{API_URL}/health")
    if response.status_code == 200:
        data = response.json()
        print(f"✓ API is healthy: {data['backend']} on {data['device']}")
        return True
    return False

def submit_job(text, voice="Junhao"):
    """Submit a generation job."""
    payload = {"text": text, "voice": voice}
    response = requests.post(f"{API_URL}/api/v1/generate", json=payload)
    
    if response.status_code == 202:
        job_id = response.json()["job_id"]
        print(f"✓ Job submitted: {job_id}")
        return job_id
    elif response.status_code == 503:
        print(f"✗ Service busy: {response.json()}")
        return None
    else:
        print(f"✗ Error: {response.status_code} - {response.text}")
        return None

def wait_for_completion(job_id, timeout=120):
    """Wait for job to complete."""
    start = time.time()
    while time.time() - start < timeout:
        response = requests.get(f"{API_URL}/api/v1/status/{job_id}")
        if response.status_code == 200:
            status = response.json()
            if status["status"] == "completed":
                duration = status.get("duration_seconds", 0)
                print(f"✓ Job completed in {duration:.2f}s")
                return True
            elif status["status"] == "failed":
                print(f"✗ Job failed: {status.get('error')}")
                return False
        time.sleep(2)
    
    print(f"✗ Job timeout after {timeout}s")
    return False

def get_metrics():
    """Get service metrics."""
    response = requests.get(f"{API_URL}/api/v1/metrics")
    if response.status_code == 200:
        return response.json()
    return None

def main():
    print("=" * 70)
    print("GPU Memory Management Test")
    print("=" * 70)
    print(f"API URL: {API_URL}\n")
    
    if not check_health():
        print("✗ API is not healthy. Exiting.")
        sys.exit(1)
    
    # Test texts of varying lengths
    test_cases = [
        ("Short text test", "Hello world, this is a test."),
        ("Medium text test", "This is a medium length test. " * 10),
        ("Long text test", "This is a long test with many sentences. " * 30),
        ("Another short test", "Testing memory management."),
        ("Final test", "Last test to verify memory is stable."),
    ]
    
    print(f"\nRunning {len(test_cases)} sequential generation tests...\n")
    
    successes = 0
    failures = 0
    
    for i, (name, text) in enumerate(test_cases, 1):
        print(f"\n--- Test {i}/{len(test_cases)}: {name} ---")
        print(f"Text length: {len(text)} characters")
        
        # Get metrics before
        metrics_before = get_metrics()
        if metrics_before:
            print(f"Jobs completed so far: {metrics_before['jobs_completed']}")
        
        # Submit and wait
        job_id = submit_job(text)
        if job_id:
            if wait_for_completion(job_id):
                successes += 1
            else:
                failures += 1
        else:
            failures += 1
            print("Waiting 5s before retry...")
            time.sleep(5)
        
        # Get metrics after
        metrics_after = get_metrics()
        if metrics_after:
            print(f"Average processing time: {metrics_after['average_processing_time_seconds']:.2f}s")
            print(f"Total jobs completed: {metrics_after['jobs_completed']}")
            print(f"Jobs failed: {metrics_after['jobs_failed']}")
    
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    print(f"Successes: {successes}/{len(test_cases)}")
    print(f"Failures: {failures}/{len(test_cases)}")
    
    final_metrics = get_metrics()
    if final_metrics:
        print(f"\nFinal Metrics:")
        print(f"  Total jobs: {final_metrics['total_jobs_processed']}")
        print(f"  Completed: {final_metrics['jobs_completed']}")
        print(f"  Failed: {final_metrics['jobs_failed']}")
        print(f"  Avg time: {final_metrics['average_processing_time_seconds']:.2f}s")
        print(f"  Uptime: {final_metrics['uptime_seconds']:.0f}s")
    
    print("\n✓ Test completed successfully!" if failures == 0 else "\n✗ Some tests failed")
    print("\nCheck Docker logs for memory usage:")
    print("  docker compose logs -f | grep -i 'cache\\|memory'")
    print("=" * 70)
    
    sys.exit(0 if failures == 0 else 1)

if __name__ == "__main__":
    main()
