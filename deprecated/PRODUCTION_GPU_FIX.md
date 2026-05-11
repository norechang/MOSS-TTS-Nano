# Production Server GPU Deployment - Quick Fix Guide

## Problem
Error when deploying with GPU on production server:
```
OCI runtime create failed: runc create failed: unable to start container process: 
error during container init: error running prestart hook #0: exit status 1, 
stdout: , stderr: Using requested mode 'cdi'
invoking the NVIDIA Container Runtime Hook directly (e.g. specifying the docker 
--gpus flag) is not supported. Please use the NVIDIA Container Runtime (e.g. 
specify the --runtime=nvidia flag) instead
```

## Root Cause
Docker daemon has `nvidia` as the default runtime, causing a conflict when docker-compose also specifies GPU resources.

## Quick Fix (Choose One)

### Option 1: Use the New GPU Compose File (Recommended)

Pull the latest changes and use the dedicated GPU compose file:

```bash
# Pull latest code
git pull origin main

# Stop any running containers
docker compose down

# Deploy with GPU using new compose file
docker compose -f docker-compose.gpu.yml up -d

# Check logs
docker compose -f docker-compose.gpu.yml logs -f

# Verify
curl http://localhost:8000/health
```

### Option 2: Fix Docker Daemon Configuration

If Option 1 doesn't work, the Docker daemon configuration may need adjustment:

```bash
# Run the diagnosis script
./fix_gpu_deployment.sh

# Follow the recommendations from the script
# Most common fix: Remove "default-runtime" from /etc/docker/daemon.json

# Example: Edit daemon.json
sudo nano /etc/docker/daemon.json

# Change from:
{
  "default-runtime": "nvidia",
  "runtimes": {
    "nvidia": {
      "path": "nvidia-container-runtime",
      "runtimeArgs": []
    }
  }
}

# To:
{
  "runtimes": {
    "nvidia": {
      "path": "nvidia-container-runtime",
      "runtimeArgs": []
    }
  }
}

# Restart Docker
sudo systemctl restart docker

# Deploy
docker compose -f docker-compose.gpu.yml up -d
```

### Option 3: Use Direct Docker Run

If docker-compose continues to have issues:

```bash
# Build image
docker build -f Dockerfile.api -t moss-tts-api:latest .

# Stop any existing containers
docker rm -f moss-tts-nano-api-gpu 2>/dev/null

# Run with GPU
docker run -d \
  --name moss-tts-nano-api-gpu \
  --gpus all \
  -p 8000:8000 \
  -v $(pwd)/generated_audio:/app/generated_audio \
  -v $(pwd)/uploads:/app/uploads \
  -v $(pwd)/config_pytorch_cuda_fp32.yaml:/app/config.yaml:ro \
  -e PROCESSING_BACKEND=pytorch \
  -e PROCESSING_DEVICE=cuda \
  -e NVIDIA_VISIBLE_DEVICES=all \
  -e NVIDIA_DRIVER_CAPABILITIES=compute,utility \
  --restart unless-stopped \
  moss-tts-api:latest

# Check logs
docker logs -f moss-tts-nano-api-gpu

# Verify
curl http://localhost:8000/health
```

## Verification Steps

### 1. Check Container is Running
```bash
docker ps | grep moss-tts
```

Expected: Container status should be "Up" not "Restarting"

### 2. Check Logs for Successful Startup
```bash
docker logs moss-tts-nano-api-gpu 2>&1 | grep -E "TTS runtime initialized|Uvicorn running"
```

Expected output:
```
INFO - TTS runtime initialized successfully
INFO - Uvicorn running on http://0.0.0.0:8000
```

### 3. Check Health Endpoint
```bash
curl http://localhost:8000/health
```

Expected:
```json
{
  "status": "healthy",
  "service": "moss-tts-nano-api",
  "backend": "pytorch",
  "device": "cuda",
  "slot_status": "idle"
}
```

### 4. Test GPU Generation
```bash
curl -X POST http://localhost:8000/api/v1/generate \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello world", "voice": "Ava"}' | jq

# Get job_id from response, then check status
curl http://localhost:8000/api/v1/status/{job_id} | jq
```

### 5. Monitor GPU Usage
```bash
# In another terminal, watch GPU usage during generation
watch -n 0.5 nvidia-smi
```

You should see GPU memory increase during generation.

## Expected Performance

**Startup Time:**
- Container build: ~2-5 minutes (first time)
- Service startup: ~10-15 seconds (includes model loading and WeTextProcessing)

**Generation Time:**
- Short text (10-20 chars): ~5-10 seconds
- Medium text (50-100 chars): ~7-12 seconds
- Long text (500+ chars): ~20-40 seconds (batched)

**Resource Usage:**
- GPU Memory: 2-4GB VRAM
- CPU: 2-4 cores during generation
- RAM: 2-4GB

## Troubleshooting

### Container Keeps Restarting
```bash
# Check logs for errors
docker logs moss-tts-nano-api-gpu --tail 50

# Common issues:
# 1. Out of GPU memory -> reduce batch size in config
# 2. CUDA version mismatch -> check nvidia-smi vs container CUDA version
# 3. Missing config file -> verify mount with: docker exec moss-tts-nano-api-gpu cat /app/config.yaml
```

### "No GPU Found" in Logs
```bash
# Test GPU access
docker run --rm --gpus all nvidia/cuda:12.0.0-base-ubuntu22.04 nvidia-smi

# If this fails, NVIDIA Container Toolkit needs configuration:
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

### Still Getting Runtime Errors
See detailed troubleshooting guide: [GPU_DEPLOYMENT.md](./GPU_DEPLOYMENT.md)

## Rollback

If you need to roll back to CPU-only deployment:

```bash
# Stop GPU container
docker compose -f docker-compose.gpu.yml down

# Start CPU container
docker compose up -d

# Verify
curl http://localhost:8002/health
```

## Files Changed in Latest Update

- `docker-compose.gpu.yml` (NEW) - Dedicated GPU deployment compose
- `docker-compose.yml` (UPDATED) - Fixed GPU variant with runtime: nvidia
- `GPU_DEPLOYMENT.md` (NEW) - Comprehensive GPU deployment guide  
- `fix_gpu_deployment.sh` (NEW) - Automated diagnosis and fix script
- `QUICKSTART.md` (UPDATED) - Added GPU deployment instructions

## Support

For detailed documentation, see:
- [GPU_DEPLOYMENT.md](./GPU_DEPLOYMENT.md) - Full GPU deployment guide
- [API.md](./API.md) - API reference
- [KNOWN_ISSUES.md](./KNOWN_ISSUES.md) - Known issues and solutions
