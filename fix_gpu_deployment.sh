#!/bin/bash
# Quick fix script for GPU deployment issues
# This script helps diagnose and fix common NVIDIA Docker GPU issues

set -e

echo "=== MOSS-TTS-Nano GPU Deployment Fix Script ==="
echo

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# 1. Check NVIDIA driver
echo "1. Checking NVIDIA driver..."
if command_exists nvidia-smi; then
    nvidia-smi --query-gpu=name,driver_version --format=csv,noheader
    echo "✓ NVIDIA driver found"
else
    echo "✗ NVIDIA driver not found. Please install NVIDIA drivers first."
    exit 1
fi
echo

# 2. Check NVIDIA Container Toolkit
echo "2. Checking NVIDIA Container Toolkit..."
if command_exists nvidia-container-cli; then
    nvidia-container-cli --version
    echo "✓ NVIDIA Container Toolkit found"
else
    echo "✗ NVIDIA Container Toolkit not found"
    echo "Install with:"
    echo "  sudo apt-get update"
    echo "  sudo apt-get install -y nvidia-container-toolkit"
    echo "  sudo nvidia-ctk runtime configure --runtime=docker"
    echo "  sudo systemctl restart docker"
    exit 1
fi
echo

# 3. Check Docker configuration
echo "3. Checking Docker daemon configuration..."
DAEMON_JSON="/etc/docker/daemon.json"
if [ -f "$DAEMON_JSON" ]; then
    echo "Current daemon.json:"
    cat "$DAEMON_JSON" | jq . 2>/dev/null || cat "$DAEMON_JSON"
    echo
    
    # Check if nvidia is default runtime
    if grep -q '"default-runtime".*"nvidia"' "$DAEMON_JSON"; then
        echo "⚠ WARNING: 'nvidia' is set as default-runtime"
        echo "This can cause conflicts with docker-compose GPU specifications."
        echo
        echo "Recommended fix:"
        echo "  1. Edit $DAEMON_JSON"
        echo "  2. Remove the 'default-runtime' line"
        echo "  3. Keep only the 'runtimes' section"
        echo "  4. Run: sudo systemctl restart docker"
        echo
        echo "Suggested daemon.json content:"
        cat <<'EOF'
{
  "runtimes": {
    "nvidia": {
      "path": "nvidia-container-runtime",
      "runtimeArgs": []
    }
  }
}
EOF
        echo
    else
        echo "✓ Docker daemon configuration looks good"
    fi
else
    echo "✓ No daemon.json found (using defaults)"
fi
echo

# 4. Test GPU access
echo "4. Testing GPU access in Docker..."
if docker run --rm --runtime=nvidia --gpus all nvidia/cuda:12.0.0-base-ubuntu22.04 nvidia-smi >/dev/null 2>&1; then
    echo "✓ GPU is accessible from Docker containers"
else
    echo "✗ GPU is NOT accessible from Docker containers"
    echo "Try:"
    echo "  sudo nvidia-ctk runtime configure --runtime=docker"
    echo "  sudo systemctl restart docker"
    exit 1
fi
echo

# 5. Check for running containers
echo "5. Checking for existing MOSS-TTS containers..."
if docker ps -a | grep -q moss-tts; then
    echo "Found existing containers:"
    docker ps -a | grep moss-tts
    echo
    read -p "Do you want to stop and remove them? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        docker ps -a | grep moss-tts | awk '{print $1}' | xargs -r docker rm -f
        echo "✓ Containers removed"
    fi
else
    echo "✓ No existing containers found"
fi
echo

# 6. Recommend deployment approach
echo "6. Recommended deployment approach:"
echo
echo "Option A: Using docker-compose.gpu.yml (Recommended)"
echo "  docker compose -f docker-compose.gpu.yml up -d"
echo
echo "Option B: Using docker run with --gpus flag"
echo "  docker run -d \\"
echo "    --name moss-tts-nano-api-gpu \\"
echo "    --gpus all \\"
echo "    -p 8000:8000 \\"
echo "    -v \$(pwd)/generated_audio:/app/generated_audio \\"
echo "    -v \$(pwd)/uploads:/app/uploads \\"
echo "    -v \$(pwd)/config_pytorch_cuda_fp32.yaml:/app/config.yaml:ro \\"
echo "    -e PROCESSING_BACKEND=pytorch \\"
echo "    -e PROCESSING_DEVICE=cuda \\"
echo "    -e NVIDIA_VISIBLE_DEVICES=all \\"
echo "    -e NVIDIA_DRIVER_CAPABILITIES=compute,utility \\"
echo "    moss-tts-api:latest"
echo
echo "Option C: Using runtime: nvidia in docker-compose.yml"
echo "  See docker-compose.gpu.yml for example"
echo

echo "=== Diagnosis Complete ==="
echo
echo "Next steps:"
echo "1. Review the findings above"
echo "2. If daemon.json has 'default-runtime': 'nvidia', remove it and restart Docker"
echo "3. Deploy using one of the recommended options above"
echo "4. Check logs: docker logs -f moss-tts-nano-api-gpu"
echo "5. Test health: curl http://localhost:8000/health"
