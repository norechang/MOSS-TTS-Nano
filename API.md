# MOSS-TTS-Nano API Documentation

## Overview

The MOSS-TTS-Nano API provides a lightweight, asynchronous speech generation service with a single-slot execution model. This design ensures predictable resource usage and simplified management for deployments with limited processing resources.

## Service Characteristics

- **Execution Model**: Asynchronous (submit job → poll status → retrieve result)
- **Processing Slots**: Single slot (one job at a time, sequential execution)
- **Availability**: Returns `503 Service Unavailable` when slot is occupied
- **Backend Support**: CPU (ONNX) or GPU (PyTorch) configurable
- **Storage**: Local filesystem with automatic cleanup
- **Authentication**: None (suitable for internal/trusted networks)

## Base URL

```
http://localhost:8000/api/v1
```

## API Endpoints

### 1. Generate Speech (Async)

Submit a text-to-speech generation job.

**Endpoint**: `POST /api/v1/generate`

**Request Body**:
```json
{
  "text": "Text to synthesize (required)",
  "voice": "Junhao (optional, default: Junhao)",
  "reference_audio": "base64-encoded audio or upload_id (optional)",
  "options": {
    "max_new_frames": 375,
    "voice_clone_max_text_tokens": 75,
    "do_sample": true,
    "text_temperature": 1.0,
    "text_top_p": 1.0,
    "text_top_k": 50,
    "audio_temperature": 0.8,
    "audio_top_p": 0.95,
    "audio_top_k": 25,
    "audio_repetition_penalty": 1.2,
    "seed": null
  }
}
```

**Response (202 Accepted)**:
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "processing",
  "created_at": "2026-05-10T10:30:00Z",
  "message": "Job accepted and processing started"
}
```

**Response (503 Service Unavailable)**:
```json
{
  "error": "service_busy",
  "message": "Processing slot is currently occupied. Please try again later.",
  "current_job_id": "550e8400-e29b-41d4-a716-446655440000",
  "estimated_wait_seconds": 15
}
```

**Response (400 Bad Request)**:
```json
{
  "error": "validation_error",
  "message": "Invalid request parameters",
  "details": {
    "text": "Text is required and cannot be empty"
  }
}
```

---

### 2. Check Job Status

Check the status of a submitted job.

**Endpoint**: `GET /api/v1/status/{job_id}`

**Response (Processing)**:
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "processing",
  "progress": 0.65,
  "created_at": "2026-05-10T10:30:00Z",
  "started_at": "2026-05-10T10:30:01Z",
  "message": "Generating speech..."
}
```

**Response (Completed)**:
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "progress": 1.0,
  "created_at": "2026-05-10T10:30:00Z",
  "started_at": "2026-05-10T10:30:01Z",
  "completed_at": "2026-05-10T10:30:15Z",
  "duration_seconds": 14.5,
  "result_url": "/api/v1/result/550e8400-e29b-41d4-a716-446655440000",
  "audio_duration_seconds": 8.3,
  "sample_rate": 48000,
  "message": "Speech generation completed successfully"
}
```

**Response (Failed)**:
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "failed",
  "created_at": "2026-05-10T10:30:00Z",
  "started_at": "2026-05-10T10:30:01Z",
  "completed_at": "2026-05-10T10:30:05Z",
  "error": "generation_error",
  "message": "Speech generation failed: Out of memory"
}
```

**Response (404 Not Found)**:
```json
{
  "error": "job_not_found",
  "message": "Job ID not found or has expired"
}
```

**Status Values**:
- `processing`: Job is currently being processed
- `completed`: Job completed successfully
- `failed`: Job failed with error

---

### 3. Download Result

Download the generated audio file.

**Endpoint**: `GET /api/v1/result/{job_id}`

**Response (200 OK)**:
- Content-Type: `audio/wav`
- Body: Binary audio data (WAV format, 48kHz, 2-channel)

**Response (404 Not Found)**:
```json
{
  "error": "result_not_found",
  "message": "Result not available. Job may not be completed or has expired."
}
```

**Response Headers**:
```
Content-Type: audio/wav
Content-Disposition: attachment; filename="tts_output_{job_id}.wav"
Content-Length: 1234567
```

---

### 4. Check Slot Availability

Check if the processing slot is available for new jobs.

**Endpoint**: `GET /api/v1/slot`

**Response (Available)**:
```json
{
  "available": true,
  "status": "idle",
  "message": "Processing slot is available"
}
```

**Response (Busy)**:
```json
{
  "available": false,
  "status": "busy",
  "current_job_id": "550e8400-e29b-41d4-a716-446655440000",
  "current_job_progress": 0.45,
  "estimated_wait_seconds": 20,
  "message": "Processing slot is currently occupied"
}
```

---

### 5. List Available Voices

List all preset voices available for speech generation.

**Endpoint**: `GET /api/v1/voices`

**Response**:
```json
{
  "voices": [
    {
      "name": "Junhao",
      "language": "Chinese",
      "gender": "male",
      "description": "Chinese male voice A"
    },
    {
      "name": "Xiaoyu",
      "language": "Chinese",
      "gender": "female",
      "description": "Chinese female voice A"
    },
    {
      "name": "Trump",
      "language": "English",
      "gender": "male",
      "description": "Trump reference voice"
    }
  ],
  "default_voice": "Junhao",
  "total_count": 15
}
```

---

### 6. Upload Reference Audio

Upload a reference audio file for voice cloning.

**Endpoint**: `POST /api/v1/voices/upload`

**Request**:
- Content-Type: `multipart/form-data`
- Field: `file` (audio file: WAV, MP3, FLAC, OGG)
- Max size: 10MB

**Response (200 OK)**:
```json
{
  "upload_id": "ref_audio_550e8400e29b41d4a716446655440000",
  "filename": "my_voice.wav",
  "duration_seconds": 5.2,
  "sample_rate": 48000,
  "message": "Reference audio uploaded successfully",
  "expires_at": "2026-05-10T11:30:00Z"
}
```

**Usage**: Use the returned `upload_id` in the `reference_audio` field when generating speech.

---

### 7. Health Check

Check service health status.

**Endpoint**: `GET /health`

**Response**:
```json
{
  "status": "healthy",
  "service": "moss-tts-nano-api",
  "version": "0.1.0",
  "backend": "onnx",
  "device": "cpu",
  "slot_status": "idle",
  "uptime_seconds": 3600
}
```

---

### 8. Service Metrics

Get simple service usage metrics.

**Endpoint**: `GET /api/v1/metrics`

**Response**:
```json
{
  "total_jobs_processed": 142,
  "jobs_completed": 138,
  "jobs_failed": 4,
  "average_processing_time_seconds": 12.5,
  "current_status": "idle",
  "uptime_seconds": 86400,
  "service_start_time": "2026-05-09T10:30:00Z"
}
```

---

## Error Codes

| HTTP Status | Error Code | Description |
|-------------|------------|-------------|
| 400 | `validation_error` | Invalid request parameters |
| 400 | `invalid_voice` | Specified voice not found |
| 400 | `text_too_long` | Text exceeds maximum length |
| 404 | `job_not_found` | Job ID not found or expired |
| 404 | `result_not_found` | Result file not available |
| 503 | `service_busy` | Processing slot is occupied |
| 500 | `generation_error` | Speech generation failed |
| 500 | `internal_error` | Internal server error |

---

## Usage Examples

### Python Example

```python
import requests
import time

BASE_URL = "http://localhost:8000/api/v1"

# Check if slot is available
response = requests.get(f"{BASE_URL}/slot")
if not response.json()["available"]:
    print("Service is busy, try again later")
    exit(1)

# Submit generation job
response = requests.post(
    f"{BASE_URL}/generate",
    json={
        "text": "Hello, this is a test of the MOSS TTS Nano API.",
        "voice": "Ava",
        "options": {
            "do_sample": True,
            "seed": 42
        }
    }
)

if response.status_code == 503:
    print("Service busy:", response.json()["message"])
    exit(1)

job_data = response.json()
job_id = job_data["job_id"]
print(f"Job submitted: {job_id}")

# Poll status until completion
while True:
    response = requests.get(f"{BASE_URL}/status/{job_id}")
    status_data = response.json()
    
    print(f"Status: {status_data['status']} - Progress: {status_data.get('progress', 0):.0%}")
    
    if status_data["status"] == "completed":
        print(f"Completed in {status_data['duration_seconds']:.1f} seconds")
        break
    elif status_data["status"] == "failed":
        print(f"Failed: {status_data['message']}")
        exit(1)
    
    time.sleep(1)

# Download result
response = requests.get(f"{BASE_URL}/result/{job_id}")
with open("output.wav", "wb") as f:
    f.write(response.content)
print("Audio saved to output.wav")
```

### cURL Examples

**Submit job**:
```bash
curl -X POST http://localhost:8000/api/v1/generate \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Hello world",
    "voice": "Junhao"
  }'
```

**Check status**:
```bash
curl http://localhost:8000/api/v1/status/550e8400-e29b-41d4-a716-446655440000
```

**Download result**:
```bash
curl -o output.wav http://localhost:8000/api/v1/result/550e8400-e29b-41d4-a716-446655440000
```

**Check slot availability**:
```bash
curl http://localhost:8000/api/v1/slot
```

**List voices**:
```bash
curl http://localhost:8000/api/v1/voices
```

### JavaScript/Node.js Example

```javascript
const axios = require('axios');
const fs = require('fs');

const BASE_URL = 'http://localhost:8000/api/v1';

async function generateSpeech(text, voice = 'Junhao') {
  // Check availability
  const slotResponse = await axios.get(`${BASE_URL}/slot`);
  if (!slotResponse.data.available) {
    throw new Error('Service is busy');
  }

  // Submit job
  const submitResponse = await axios.post(`${BASE_URL}/generate`, {
    text,
    voice,
    options: { do_sample: true }
  });

  const jobId = submitResponse.data.job_id;
  console.log(`Job submitted: ${jobId}`);

  // Poll status
  while (true) {
    const statusResponse = await axios.get(`${BASE_URL}/status/${jobId}`);
    const status = statusResponse.data;

    console.log(`Status: ${status.status} - Progress: ${(status.progress || 0) * 100}%`);

    if (status.status === 'completed') {
      console.log(`Completed in ${status.duration_seconds}s`);
      break;
    } else if (status.status === 'failed') {
      throw new Error(`Generation failed: ${status.message}`);
    }

    await new Promise(resolve => setTimeout(resolve, 1000));
  }

  // Download result
  const resultResponse = await axios.get(`${BASE_URL}/result/${jobId}`, {
    responseType: 'arraybuffer'
  });

  fs.writeFileSync('output.wav', Buffer.from(resultResponse.data));
  console.log('Audio saved to output.wav');
}

generateSpeech('Hello, this is a test.', 'Ava');
```

---

## Configuration

The service can be configured via `config.yaml`:

```yaml
service:
  host: 0.0.0.0
  port: 8000
  
processing:
  backend: onnx      # or pytorch
  device: cpu        # or cuda
  cpu_threads: 4
  execution_provider: cpu  # or cuda (for ONNX)
  
storage:
  output_dir: ./generated_audio
  upload_dir: ./uploads
  retention_hours: 1
  max_upload_size_mb: 10
  
defaults:
  voice: Junhao
  max_new_frames: 375
  voice_clone_max_text_tokens: 75
  do_sample: true
  
limits:
  max_text_length: 5000
  request_timeout_seconds: 300
```

---

## Deployment

### Docker

**Build**:
```bash
docker build -t moss-tts-nano-api .
```

**Run (CPU)**:
```bash
docker run -p 8000:8000 \
  -v $(pwd)/generated_audio:/app/generated_audio \
  moss-tts-nano-api
```

**Run (GPU)**:
```bash
docker run --gpus all -p 8000:8000 \
  -v $(pwd)/generated_audio:/app/generated_audio \
  -e PROCESSING_BACKEND=pytorch \
  -e PROCESSING_DEVICE=cuda \
  moss-tts-nano-api
```

### Docker Compose

```bash
docker-compose up -d
```

---

## Rate Limiting & Best Practices

### Client-Side Best Practices

1. **Always check slot availability** before submitting jobs
2. **Implement exponential backoff** when receiving 503 errors
3. **Poll status with 1-2 second intervals** (not more frequently)
4. **Download results promptly** - files are auto-deleted after retention period
5. **Handle network errors gracefully** with retry logic

### Recommended Retry Logic

```python
import time
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

def create_session():
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[500, 502, 503, 504],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

def submit_with_retry(url, data, max_attempts=5):
    session = create_session()
    for attempt in range(max_attempts):
        try:
            response = session.post(url, json=data)
            if response.status_code == 503:
                wait_time = 2 ** attempt  # Exponential backoff
                print(f"Service busy, waiting {wait_time}s...")
                time.sleep(wait_time)
                continue
            return response
        except requests.exceptions.RequestException as e:
            if attempt == max_attempts - 1:
                raise
            time.sleep(2 ** attempt)
    raise Exception("Max retry attempts reached")
```

---

## Troubleshooting

### Service returns 503 frequently
- **Cause**: Jobs take longer than expected
- **Solution**: Check if text is too long, reduce `max_new_frames`, or use faster hardware

### Jobs fail with "Out of memory"
- **Cause**: Insufficient GPU/CPU memory
- **Solution**: Reduce `max_new_frames`, use CPU backend, or upgrade hardware

### Results not available (404)
- **Cause**: Files expired (default: 1 hour retention)
- **Solution**: Download results promptly after completion

### Slow generation
- **Cause**: CPU backend is slower than GPU
- **Solution**: Use GPU backend if available, reduce quality settings

---

## API Versioning

Current version: **v1**

The API follows semantic versioning. Breaking changes will result in a new version (v2, v3, etc.).

---

## Support

For issues and questions:
- GitHub Issues: https://github.com/OpenMOSS/MOSS-TTS-Nano/issues
- Documentation: https://studio.mosi.cn/docs/moss-tts-nano

---

Last Updated: 2026-05-10
