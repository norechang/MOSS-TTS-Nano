# MOSS-TTS-Nano API Service - Quick Start Guide

## Overview

This guide helps you quickly deploy and test the MOSS-TTS-Nano API service.

## Prerequisites

- Docker and Docker Compose (recommended), OR
- Python 3.10+ with pip

## Quick Start with Docker (Recommended)

### 1. Start the Service

#### Option A: CPU Backend (ONNX)
```bash
# Start with CPU backend (ONNX) - recommended for CPU-only servers
docker compose up -d

# Or build and start
docker compose up --build -d
```

#### Option B: GPU Backend (PyTorch CUDA)
```bash
# Start with GPU backend (PyTorch CUDA)
docker compose -f docker-compose.gpu.yml up -d

# Or build and start
docker compose -f docker-compose.gpu.yml up --build -d
```

**Note**: For GPU deployment, see [GPU_DEPLOYMENT.md](./GPU_DEPLOYMENT.md) for detailed setup instructions and troubleshooting.

### 2. Check Service Health

```bash
# For CPU deployment
curl http://localhost:8002/health

# For GPU deployment
curl http://localhost:8000/health
```

Expected response:
```json
{
  "status": "healthy",
  "service": "moss-tts-nano-api",
  "backend": "onnx",  // or "pytorch"
  "device": "cpu",    // or "cuda"
  "slot_status": "idle"
}
```

### 3. Test the API

```bash
python test_api_client.py
```

### 4. View Logs

```bash
docker-compose logs -f moss-tts-api
```

### 5. Stop the Service

```bash
docker-compose down
```

## Quick Start without Docker

### 1. Install Dependencies

```bash
pip install -r requirements.txt
pip install pyyaml
```

### 2. Start the Service

```bash
# CPU backend (ONNX) - fastest for CPU
python api_service.py --backend onnx --device cpu

# GPU backend (PyTorch) - best for GPU
python api_service.py --backend pytorch --device cuda
```

### 3. Test the API

In another terminal:

```bash
python test_api_client.py
```

## Configuration

Edit `config.yaml` to customize:

```yaml
processing:
  backend: onnx  # or pytorch
  device: cpu    # or cuda
  cpu_threads: 4

storage:
  retention_hours: 1.0
  max_upload_size_mb: 10

defaults:
  voice: Junhao
  max_new_frames: 375
```

## API Documentation

Once the service is running, visit:

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- Full documentation: [API.md](./API.md)

## Basic Usage Examples

### Python

```python
import requests
import time

BASE_URL = "http://localhost:8000/api/v1"

# Submit job
response = requests.post(
    f"{BASE_URL}/generate",
    json={"text": "Hello world", "voice": "Ava"}
)
job_id = response.json()["job_id"]

# Poll until complete
while True:
    status = requests.get(f"{BASE_URL}/status/{job_id}").json()
    if status["status"] == "completed":
        break
    time.sleep(1)

# Download result
audio = requests.get(f"{BASE_URL}/result/{job_id}")
with open("output.wav", "wb") as f:
    f.write(audio.content)
```

### cURL

```bash
# Submit job
JOB_ID=$(curl -X POST http://localhost:8000/api/v1/generate \
  -H "Content-Type: application/json" \
  -d '{"text":"Hello world","voice":"Ava"}' \
  | jq -r '.job_id')

# Check status
curl http://localhost:8000/api/v1/status/$JOB_ID

# Download result
curl -o output.wav http://localhost:8000/api/v1/result/$JOB_ID
```

## Troubleshooting

### Service returns 503 (Busy)

The processing slot is occupied. Wait and retry:

```bash
# Check slot status
curl http://localhost:8000/api/v1/slot
```

### Out of Memory Error

Reduce `max_new_frames` in config or request:

```json
{
  "text": "Your text",
  "options": {
    "max_new_frames": 200
  }
}
```

### Docker Container Won't Start

Check logs:

```bash
docker-compose logs moss-tts-api
```

Common issues:
- Port 8000 already in use: Change port in `docker-compose.yml`
- Insufficient memory: Reduce `max_new_frames` in config

## GPU Support

To use GPU with Docker:

1. Install [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)

2. Uncomment GPU service in `docker-compose.yml`

3. Start GPU service:

```bash
docker-compose up moss-tts-api-gpu -d
```

## File Locations

- Generated audio: `./generated_audio/`
- Uploaded references: `./uploads/`
- Logs: stdout or `./logs/` (if configured)
- Configuration: `./config.yaml`

## Architecture

The service uses a **single-slot execution model**:
- ✓ One job at a time (sequential processing)
- ✓ Simple, predictable resource usage
- ✓ Returns 503 when busy (clients retry)
- ✓ No queue management complexity

See [AGENTS.md](./AGENTS.md) for design rationale.

## Next Steps

- Read full API documentation: [API.md](./API.md)
- Customize configuration: Edit `config.yaml`
- Integrate with your application
- Monitor usage: Check `/api/v1/metrics`

## Support

- Issues: https://github.com/OpenMOSS/MOSS-TTS-Nano/issues
- Documentation: https://studio.mosi.cn/docs/moss-tts-nano
