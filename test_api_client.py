#!/usr/bin/env python3
"""
Simple test client for MOSS-TTS-Nano API service.

Usage:
    python test_api_client.py
    python test_api_client.py --text "Hello world" --voice Ava
    python test_api_client.py --url http://localhost:8000
"""

import argparse
import time
import sys
import requests


def test_api(base_url: str, text: str, voice: str, output_file: str):
    """Test the API service end-to-end."""
    
    print(f"Testing MOSS-TTS-Nano API at {base_url}")
    print("=" * 60)
    
    # 1. Health check
    print("\n1. Health Check...")
    try:
        response = requests.get(f"{base_url}/health", timeout=5)
        response.raise_for_status()
        health = response.json()
        print(f"   ✓ Service is healthy")
        print(f"   Backend: {health['backend']}, Device: {health['device']}")
        print(f"   Slot status: {health['slot_status']}")
    except Exception as e:
        print(f"   ✗ Health check failed: {e}")
        return False
    
    # 2. List voices
    print("\n2. List Available Voices...")
    try:
        response = requests.get(f"{base_url}/api/v1/voices", timeout=5)
        response.raise_for_status()
        voices_data = response.json()
        print(f"   ✓ Found {voices_data['total_count']} voices")
        print(f"   Default voice: {voices_data['default_voice']}")
        if voices_data['voices']:
            print(f"   Available: {', '.join(v['name'] for v in voices_data['voices'][:5])}")
    except Exception as e:
        print(f"   ✗ Failed to list voices: {e}")
        return False
    
    # 3. Check slot availability
    print("\n3. Check Slot Availability...")
    try:
        response = requests.get(f"{base_url}/api/v1/slot", timeout=5)
        response.raise_for_status()
        slot = response.json()
        if slot['available']:
            print(f"   ✓ Processing slot is available")
        else:
            print(f"   ! Slot is busy (job: {slot.get('current_job_id')})")
            print(f"   Estimated wait: {slot.get('estimated_wait_seconds', '?')} seconds")
    except Exception as e:
        print(f"   ✗ Failed to check slot: {e}")
        return False
    
    # 4. Submit generation job
    print(f"\n4. Submit Generation Job...")
    print(f"   Text: {text[:50]}{'...' if len(text) > 50 else ''}")
    print(f"   Voice: {voice}")
    
    try:
        response = requests.post(
            f"{base_url}/api/v1/generate",
            json={
                "text": text,
                "voice": voice,
                "options": {
                    "do_sample": True,
                    "seed": 42
                }
            },
            timeout=10
        )
        
        if response.status_code == 503:
            print(f"   ! Service is busy (503), try again later")
            error_data = response.json()
            print(f"   {error_data.get('detail', {}).get('message', 'Unknown error')}")
            return False
        
        response.raise_for_status()
        job_data = response.json()
        job_id = job_data['job_id']
        print(f"   ✓ Job submitted: {job_id}")
        print(f"   Status: {job_data['status']}")
    except Exception as e:
        print(f"   ✗ Failed to submit job: {e}")
        return False
    
    # 5. Poll status until completion
    print(f"\n5. Polling Job Status...")
    max_wait = 120  # Max 2 minutes
    start_time = time.time()
    
    while True:
        try:
            response = requests.get(f"{base_url}/api/v1/status/{job_id}", timeout=5)
            response.raise_for_status()
            status_data = response.json()
            
            status = status_data['status']
            progress = status_data.get('progress', 0.0)
            
            print(f"   Status: {status} - Progress: {progress:.0%}", end='\r')
            
            if status == 'completed':
                duration = status_data.get('duration_seconds', 0)
                audio_duration = status_data.get('audio_duration_seconds', 0)
                print(f"\n   ✓ Job completed in {duration:.1f}s")
                print(f"   Generated audio: {audio_duration:.1f}s")
                break
            
            elif status == 'failed':
                error = status_data.get('error', 'Unknown error')
                print(f"\n   ✗ Job failed: {error}")
                return False
            
            # Check timeout
            if time.time() - start_time > max_wait:
                print(f"\n   ✗ Timeout waiting for job completion")
                return False
            
            time.sleep(1)
            
        except Exception as e:
            print(f"\n   ✗ Failed to get status: {e}")
            return False
    
    # 6. Download result
    print(f"\n6. Download Result...")
    try:
        response = requests.get(f"{base_url}/api/v1/result/{job_id}", timeout=30)
        response.raise_for_status()
        
        with open(output_file, 'wb') as f:
            f.write(response.content)
        
        file_size = len(response.content) / 1024  # KB
        print(f"   ✓ Audio saved to: {output_file}")
        print(f"   File size: {file_size:.1f} KB")
    except Exception as e:
        print(f"   ✗ Failed to download result: {e}")
        return False
    
    # 7. Check metrics
    print(f"\n7. Service Metrics...")
    try:
        response = requests.get(f"{base_url}/api/v1/metrics", timeout=5)
        response.raise_for_status()
        metrics = response.json()
        print(f"   Total jobs: {metrics['total_jobs_processed']}")
        print(f"   Completed: {metrics['jobs_completed']}")
        print(f"   Failed: {metrics['jobs_failed']}")
        print(f"   Avg time: {metrics['average_processing_time_seconds']:.1f}s")
    except Exception as e:
        print(f"   ! Failed to get metrics: {e}")
    
    print("\n" + "=" * 60)
    print("✓ All tests passed successfully!")
    return True


def main():
    parser = argparse.ArgumentParser(description="Test MOSS-TTS-Nano API")
    parser.add_argument(
        "--url",
        default="http://localhost:8000",
        help="API base URL (default: http://localhost:8000)"
    )
    parser.add_argument(
        "--text",
        default="Hello, this is a test of the MOSS TTS Nano API service.",
        help="Text to synthesize"
    )
    parser.add_argument(
        "--voice",
        default="Junhao",
        help="Voice name (default: Junhao)"
    )
    parser.add_argument(
        "--output",
        default="test_output.wav",
        help="Output audio file (default: test_output.wav)"
    )
    
    args = parser.parse_args()
    
    success = test_api(
        base_url=args.url.rstrip('/'),
        text=args.text,
        voice=args.voice,
        output_file=args.output
    )
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
