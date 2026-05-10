# GPU Deployment Guide

This guide covers deploying the MOSS-TTS-Nano API service with GPU support using Docker.

## Prerequisites

### 1. NVIDIA Driver
Ensure NVIDIA drivers are installed on the host:
```bash
nvidia-smi
```

Expected output should show GPU information and driver version (e.g., 535.x or newer).

### 2. NVIDIA Container Toolkit
Install the NVIDIA Container Toolkit:

**Ubuntu/Debian:**
```bash
# Add repository
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list | \
    sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
    sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

# Install
sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit

# Configure Docker
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

**RHEL/CentOS:**
```bash
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.repo | \
    sudo tee /etc/yum.repos.d/nvidia-container-toolkit.repo

sudo yum install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

### 3. Verify GPU Access in Docker
```bash
docker run --rm --runtime=nvidia --gpus all nvidia/cuda:12.0.0-base-ubuntu22.04 nvidia-smi
```

This should show the same GPU information as the host `nvidia-smi`.

## Deployment Options

### Option 1: Using `runtime: nvidia` (Recommended)

This is the simplest and most compatible approach for Docker 19.03+.

**File: `docker-compose.gpu.yml`**

```bash
# Deploy with GPU support
docker compose -f docker-compose.gpu.yml up -d

# Check logs
docker compose -f docker-compose.gpu.yml logs -f

# Stop
docker compose -f docker-compose.gpu.yml down
```

### Option 2: Using `deploy.resources`

If `runtime: nvidia` doesn't work, use the `deploy.resources` syntax (Docker Compose v1.28.0+):

1. Edit `docker-compose.gpu.yml`
2. Comment out the `moss-tts-api-gpu-runtime` service
3. Uncomment the `moss-tts-api-gpu-deploy` service
4. Deploy:

```bash
docker compose -f docker-compose.gpu.yml up -d
```

### Option 3: Using `docker run` with `--gpus`

For direct Docker commands without Compose:

```bash
# Build image
docker build -f Dockerfile.api -t moss-tts-api:latest .

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
  moss-tts-api:latest
```

## Common Issues and Solutions

### Issue 1: "OCI runtime create failed: runc create failed"
**Error:**
```
failed to create shim task: OCI runtime create failed: runc create failed: 
unable to start container process: error during container init: 
error running prestart hook #0: exit status 1, stdout: , stderr: 
Using requested mode 'cdi'
invoking the NVIDIA Container Runtime Hook directly (e.g. specifying the 
docker --gpus flag) is not supported. Please use the NVIDIA Container 
Runtime (e.g. specify the --runtime=nvidia flag) instead
```

**Root Cause:**
The Docker daemon is configured with `nvidia` as the default runtime but the container is also specifying GPU resources, causing a conflict.

**Solution A: Use `runtime: nvidia` (Recommended)**
```yaml
services:
  moss-tts-api-gpu:
    runtime: nvidia  # Add this line
    environment:
      - NVIDIA_VISIBLE_DEVICES=all
      - NVIDIA_DRIVER_CAPABILITIES=compute,utility
    # Remove deploy.resources.devices section
```

**Solution B: Set Default Runtime in `/etc/docker/daemon.json`**
```json
{
  "default-runtime": "nvidia",
  "runtimes": {
    "nvidia": {
      "path": "nvidia-container-runtime",
      "runtimeArgs": []
    }
  }
}
```

Then restart Docker:
```bash
sudo systemctl restart docker
```

**Solution C: Remove Default Runtime**
If you prefer explicit GPU specification, edit `/etc/docker/daemon.json`:
```json
{
  "runtimes": {
    "nvidia": {
      "path": "nvidia-container-runtime",
      "runtimeArgs": []
    }
  }
}
```

Remove `"default-runtime": "nvidia"` line, then restart Docker.

### Issue 2: "could not select device driver with capabilities: [[gpu]]"
**Solution:**
Ensure `nvidia-container-toolkit` is installed and Docker is restarted:
```bash
sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

### Issue 3: GPU Not Visible Inside Container
**Check:**
```bash
docker exec -it moss-tts-nano-api-gpu nvidia-smi
```

**If command not found:**
The NVIDIA Container Toolkit is not properly configured.

**If shows "No devices found":**
Check environment variables:
```yaml
environment:
  - NVIDIA_VISIBLE_DEVICES=all  # or specific GPU index like "0,1"
  - NVIDIA_DRIVER_CAPABILITIES=compute,utility
```

### Issue 4: Out of Memory (OOM) Errors
**Symptoms:**
Container crashes or CUDA OOM errors in logs.

**Solutions:**
1. Reduce batch size in config:
```yaml
defaults:
  voice_clone_max_text_tokens: 50  # Reduce from 75
```

2. Use float32 instead of bfloat16:
```yaml
processing:
  dtype: "float32"
```

3. Limit GPU memory per container (in docker-compose.yml):
```yaml
deploy:
  resources:
    limits:
      memory: 8G  # Adjust based on available GPU VRAM
```

## Verification

### 1. Check Container Status
```bash
docker ps -a | grep moss-tts
```

### 2. Check Logs
```bash
docker logs moss-tts-nano-api-gpu -f
```

Look for:
```
INFO - Initializing TTS runtime: backend=pytorch, device=cuda
INFO - WeTextProcessing ready for API service
INFO - Warming up TTS model...
INFO - TTS runtime initialized successfully
INFO - Uvicorn running on http://0.0.0.0:8000
```

### 3. Test Health Endpoint
```bash
curl http://localhost:8000/health
```

Expected response:
```json
{
  "status": "healthy",
  "service": "moss-tts-nano-api",
  "backend": "pytorch",
  "device": "cuda",
  "slot_status": "idle"
}
```

### 4. Test GPU Usage
```bash
# Submit a job
curl -X POST http://localhost:8000/api/v1/generate \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello world", "voice": "Ava"}'

# Monitor GPU usage in another terminal
watch -n 0.5 nvidia-smi
```

You should see GPU memory increase during generation.

## Performance Expectations

**PyTorch CUDA (RTX 30/40 series with bfloat16):**
- Startup: 10-15 seconds (includes WeTextProcessing and model loading)
- Generation: 5-10 seconds per job (varies with text length)
- Memory: 2-4GB VRAM
- Concurrent: Single-slot (one job at a time)

**PyTorch CUDA (float32 or older GPUs):**
- Startup: 10-15 seconds
- Generation: 7-12 seconds per job
- Memory: 3-5GB VRAM

## Configuration Tips

### For Multiple GPUs
Specify which GPU to use:
```yaml
environment:
  - NVIDIA_VISIBLE_DEVICES=0  # Use first GPU only
  # or NVIDIA_VISIBLE_DEVICES=1 for second GPU
```

### For Production Deployments
```yaml
services:
  moss-tts-api-gpu:
    runtime: nvidia
    restart: always  # Always restart on failure
    logging:
      driver: "json-file"
      options:
        max-size: "100m"
        max-file: "3"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
    deploy:
      resources:
        limits:
          memory: 8G  # Prevent runaway memory usage
```

## Monitoring

### Check GPU Utilization
```bash
# Real-time monitoring
nvidia-smi dmon

# Container-specific
docker stats moss-tts-nano-api-gpu
```

### Check API Metrics
```bash
curl http://localhost:8000/api/v1/metrics
```

## Troubleshooting Checklist

- [ ] NVIDIA driver installed (`nvidia-smi` works on host)
- [ ] NVIDIA Container Toolkit installed
- [ ] Docker restarted after toolkit installation
- [ ] GPU accessible in test container (`docker run --rm --gpus all nvidia/cuda:12.0.0-base-ubuntu22.04 nvidia-smi`)
- [ ] Correct `runtime: nvidia` or `deploy.resources` in compose file
- [ ] Environment variables `NVIDIA_VISIBLE_DEVICES` and `NVIDIA_DRIVER_CAPABILITIES` set
- [ ] Config file mounted correctly (check with `docker exec moss-tts-nano-api-gpu cat /app/config.yaml`)
- [ ] Sufficient GPU memory available (check with `nvidia-smi`)

## References

- [NVIDIA Container Toolkit Documentation](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)
- [Docker GPU Support](https://docs.docker.com/config/containers/resource_constraints/#gpu)
- [Docker Compose GPU Support](https://docs.docker.com/compose/gpu-support/)
