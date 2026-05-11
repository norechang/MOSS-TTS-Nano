# MOSS-TTS-Nano API Service

## Overview

The MOSS-TTS-Nano API Service provides a production-ready, asynchronous RESTful API for speech synthesis. It implements a single-slot execution model with support for both CPU (ONNX) and GPU (PyTorch) backends.

## Documentation

### Primary API Reference
**📘 [API.md](./API.md)** is the authoritative specification document for:
- Complete API endpoint reference
- Request/response schemas  
- Authentication and error handling
- Usage examples and client code

**All developers and AI agents must maintain consistency with API.md during the development lifecycle.**

### Supporting Documentation
- **[QUICKSTART.md](./QUICKSTART.md)** - Getting started guide for users
- **[GPU_DEPLOYMENT.md](./GPU_DEPLOYMENT.md)** - GPU deployment guide
- **[GPU_MEMORY_MANAGEMENT.md](./GPU_MEMORY_MANAGEMENT.md)** - GPU memory management implementation details
- **[AGENTS.md](./AGENTS.md)** - Design decisions and architectural constraints (for maintainers)
- **[KNOWN_ISSUES.md](./KNOWN_ISSUES.md)** - Troubleshooting guide

## Architecture Overview

### Core Design Principles

**1. Single-Slot Execution Model**
- One job at a time (sequential processing)
- No job queue - returns 503 when busy
- Predictable resource usage (one model loaded)

**2. Asynchronous Pattern**
- Submit → Poll Status → Retrieve Result
- Non-blocking submission (202 Accepted)
- Client-controlled retry logic

**3. Lightweight & Stateless**
- Minimal file architecture
- No database required
- Jobs lost on service restart (ephemeral state)

### Components

```
api_service.py       # Main FastAPI application (878 lines)
slot_manager.py      # Single-slot state management (320 lines)
config.yaml          # Service configuration
Dockerfile.api       # Container definition
docker-compose.yml   # Deployment configuration
```

### Backends

**ONNX Runtime (Recommended for CPU)**
- CPU-optimized, 2x faster than PyTorch on CPU
- Lighter dependencies
- 2-5 seconds per generation

**PyTorch (Recommended for GPU)**
- GPU-optimized with CUDA support
- More flexible (fine-tuning, custom models)
- 5-10 seconds per generation with GPU

## Quick Start

### Docker Deployment (Recommended)

**CPU Backend:**
```bash
docker compose up -d
curl http://localhost:8002/health
```

**GPU Backend:**
```bash
docker compose -f docker-compose.gpu.yml up -d
curl http://localhost:8000/health
```

### Direct Python

```bash
# CPU (ONNX)
python api_service.py --backend onnx --device cpu

# GPU (PyTorch)
python api_service.py --backend pytorch --device cuda
```

See [QUICKSTART.md](./QUICKSTART.md) for detailed instructions.

## API Endpoints

**Primary specification: [API.md](./API.md)**

### Core Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/generate` | POST | Submit speech generation job |
| `/api/v1/status/{job_id}` | GET | Check job status |
| `/api/v1/result/{job_id}` | GET | Download generated audio |
| `/api/v1/voices` | GET | List available voice presets |
| `/api/v1/slot` | GET | Check slot availability |
| `/health` | GET | Service health check |

### Example Usage

```python
import requests
import time

# Submit job
response = requests.post('http://localhost:8000/api/v1/generate', json={
    'text': '你好世界',
    'voice': 'Junhao'
})
job_id = response.json()['job_id']

# Poll status
while True:
    status = requests.get(f'http://localhost:8000/api/v1/status/{job_id}').json()
    if status['status'] == 'completed':
        break
    time.sleep(2)

# Download result
audio = requests.get(f'http://localhost:8000/api/v1/result/{job_id}')
with open('output.wav', 'wb') as f:
    f.write(audio.content)
```

## Configuration

Edit `config.yaml` to customize:

```yaml
processing:
  backend: onnx          # or pytorch
  device: cpu            # or cuda
  
storage:
  retention_hours: 1.0   # Result TTL
  max_upload_size_mb: 10
  
defaults:
  voice: Junhao
  max_new_frames: 375
```

Full configuration schema in [AGENTS.md](./AGENTS.md).

## Key Features

### Text Normalization
- Automatic WeTextProcessing for Chinese/English/Japanese
- Robust text cleanup and normalization
- Hyphen rewriting for Chinese text

### Voice Presets
18 built-in voices across languages:
- Chinese: Junhao, Zhiming, Weiguo, Xiaoyu, Yuewen, Lingyu
- English: Trump, Ava, Bella, Adam, Nathan
- Japanese: Sakura, Yui, Aoi, Hina, Mei

### Automatic Cleanup
- TTL-based file cleanup (default: 1 hour)
- Background cleanup every 5 minutes
- Configurable retention policy

## Technical Constraints

### Hard Limits
- **Single active job**: Only one generation at a time
- **No job queue**: Requests rejected when busy (503)
- **No persistence**: Jobs lost on service restart
- **No distributed**: Single-instance only

### Soft Limits (Configurable)
- Result retention: Default 1 hour
- Max text length: Default 5000 chars
- Max upload size: Default 10MB
- Request timeout: Default 300 seconds

### Resource Requirements
- **Processing time**: 2-10 seconds typical per job
- **Memory**: 2-4GB RAM (CPU) or 2-4GB VRAM (GPU)
- **Storage**: ~100MB per hour of generated audio
- **Network**: Local network latency (<10ms recommended)

## Error Handling

The API follows RESTful error conventions:

- **200 OK**: Successful operation
- **202 Accepted**: Job submitted and processing
- **400 Bad Request**: Invalid input
- **404 Not Found**: Job not found or expired
- **503 Service Unavailable**: Slot busy, retry later
- **500 Internal Server Error**: Generation failed

All errors include descriptive messages. See [API.md](./API.md) for complete error handling specification.

## Testing

```bash
# Run validation test suite
cd api_validate
python run_validation.py

# Run specific test
python test_generate_endpoint.py
```

Test suite validates all endpoints against [API.md](./API.md) specification.

## Performance Expectations

**ONNX CPU (4 threads)**:
- Startup: 3-5 seconds
- Generation: 2-5 seconds per job
- Memory: ~2GB RAM

**PyTorch CUDA (RTX 30/40 series)**:
- Startup: 10-15 seconds (includes WeTextProcessing)
- Generation: 5-10 seconds per job
- Memory: ~2-4GB VRAM

**First-run overhead**:
- WeTextProcessing: 25-30s to build FST (one-time)
- Model download: ~40s from HuggingFace (one-time, cached)

## Deployment Modes

### Development
```bash
python api_service.py --config config.yaml
```

### Production (Docker)
```bash
docker compose up -d
```

### Production (GPU)
```bash
docker compose -f docker-compose.gpu.yml up -d
```

See [GPU_DEPLOYMENT.md](./GPU_DEPLOYMENT.md) for GPU-specific configuration.

## Monitoring

### Health Check
```bash
curl http://localhost:8000/health
```

### Metrics
```bash
curl http://localhost:8000/api/v1/metrics
```

### Slot Status
```bash
curl http://localhost:8000/api/v1/slot
```

## Security Considerations

**Current Implementation**: No authentication

**Design Philosophy**: Designed for internal/trusted networks. Deploy behind:
- VPN for remote access
- Reverse proxy (nginx/Traefik) with authentication
- Network firewall rules

**Not Recommended**: Direct internet exposure without authentication.

## Scalability Considerations

### What This Design Does NOT Support
❌ Multiple concurrent jobs  
❌ Job queuing  
❌ Distributed deployment  
❌ High availability  
❌ Load balancing  
❌ Horizontal scaling  

### When to Revisit Architecture
Consider a more complex architecture if:
1. **Traffic**: >1000 requests/hour consistently
2. **SLA**: <5 second response time required
3. **Availability**: 99.9%+ uptime needed
4. **Concurrency**: Multiple GPUs available
5. **Distribution**: Multi-region deployment needed

## Development Guidelines

### For Developers

1. **Always reference [API.md](./API.md)** for endpoint specifications
2. **Maintain backward compatibility** in request/response schemas
3. **Add validation tests** in `api_validate/` for new features
4. **Update API.md** when changing endpoint behavior
5. **Run validation suite** before committing changes

### For AI Agents

1. **API.md is the source of truth** - maintain consistency during development
2. **Respect single-slot constraint** - never implement queuing or parallelization
3. **Keep it simple** - prefer single-file solutions over multi-module architectures
4. **Document changes** - update AGENTS.md for architectural decisions
5. **Test thoroughly** - every change should include validation tests

## Troubleshooting

### Common Issues

**Service won't start:**
- Check logs: `docker compose logs -f`
- Verify config file: `cat config.yaml`
- Check port availability: `netstat -tlnp | grep 8000`

**GPU not accessible:**
- See [GPU_DEPLOYMENT.md](./GPU_DEPLOYMENT.md)
- Run diagnosis: `./fix_gpu_deployment.sh`

**Generation fails:**
- Check [KNOWN_ISSUES.md](./KNOWN_ISSUES.md)
- Verify backend: ONNX vs PyTorch compatibility

**503 errors:**
- Expected when slot is busy
- Client should implement exponential backoff
- Check slot status: `curl http://localhost:8000/api/v1/slot`

## Contributing

1. Read [API.md](./API.md) to understand API contract
2. Read [AGENTS.md](./AGENTS.md) to understand design decisions
3. Make changes while maintaining API compatibility
4. Add validation tests in `api_validate/`
5. Run test suite: `cd api_validate && python run_validation.py`
6. Update documentation if behavior changes

## License

Follow the main MOSS-TTS-Nano project license.

## References

- **Primary**: [API.md](./API.md) - Complete API specification
- **Quick Start**: [QUICKSTART.md](./QUICKSTART.md) - Getting started
- **GPU Setup**: [GPU_DEPLOYMENT.md](./GPU_DEPLOYMENT.md) - GPU deployment guide
- **Architecture**: [AGENTS.md](./AGENTS.md) - Design decisions
- **Troubleshooting**: [KNOWN_ISSUES.md](./KNOWN_ISSUES.md) - Known issues
- **Main Project**: [README.md](./README.md) - MOSS-TTS-Nano overview
