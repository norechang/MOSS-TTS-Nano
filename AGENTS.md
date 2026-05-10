# MOSS-TTS-Nano API Service Design Policy

## Document Purpose

This document records the design decisions and architectural constraints for the MOSS-TTS-Nano API service implementation. It serves as a reference for future development, maintenance, and AI agents working on this codebase.

---

## Core Design Principles

### 1. Lightweight Architecture
- **Philosophy**: Minimize complexity and management overhead
- **Goal**: Single-file or minimal-file implementation where possible
- **Reasoning**: Easier to deploy, maintain, and debug

### 2. Single-Slot Execution Model
- **Processing Capacity**: One job at a time (sequential execution)
- **Concurrency**: No parallel job processing
- **Reasoning**: Limited to single processing resource (one GPU or CPU)

### 3. Predictable Resource Usage
- **Memory**: Fixed memory footprint (one model loaded)
- **CPU/GPU**: Predictable utilization (one job active)
- **Storage**: Bounded by retention policy

---

## Architectural Decisions

### Execution Mode
- **Selected**: Asynchronous (async)
- **Pattern**: Submit → Poll Status → Retrieve Result
- **Alternatives Rejected**: 
  - Synchronous (prone to timeouts)
  - Queue-based (adds complexity)

**Rationale**: Async mode provides better client experience without adding queue management complexity. Clients can retry on 503 without losing work.

### Deployment Model
- **Selected**: Standalone service
- **Pattern**: Separate from existing web UI (`app.py`)
- **Alternatives Rejected**: 
  - Extend existing `app.py` (mixed concerns)

**Rationale**: Clean separation allows independent deployment, versioning, and scaling. Web UI and API have different requirements.

### Container Strategy
- **Selected**: Docker
- **Base Image**: Python 3.10+ with ONNX Runtime
- **Alternatives Considered**: 
  - Bare metal (less portable)
  - K8s (overkill for single-slot)

**Rationale**: Docker provides consistent deployment across environments without orchestration overhead.

### Authentication
- **Selected**: None
- **Security Model**: Trust network perimeter
- **Alternatives Rejected**: 
  - API keys (added complexity)
  - OAuth (overkill)

**Rationale**: Designed for internal/trusted networks. Authentication can be added at reverse proxy layer if needed.

### Backend Selection
- **Selected**: Configurable (CPU/GPU via config)
- **Options**: 
  - ONNX Runtime (CPU-optimized, 2x faster)
  - PyTorch (GPU-optimized)
- **Default**: ONNX with CPU

**Rationale**: Flexibility for different deployment scenarios without code changes.

### Storage
- **Selected**: Local filesystem
- **Structure**: 
  - `./generated_audio/` for outputs
  - `./uploads/` for reference audio
- **Alternatives Rejected**: 
  - S3/Cloud storage (adds dependencies)
  - Database BLOB storage (unnecessary)

**Rationale**: Simple, fast, sufficient for ephemeral results with TTL-based cleanup.

### Busy Handling
- **Selected**: Return 503 immediately
- **Pattern**: Fail-fast with retry guidance
- **Alternatives Rejected**: 
  - Queue single request (partial queue)
  - Block/wait (bad UX)

**Rationale**: Clear, predictable behavior. Client controls retry logic. No hidden queuing complexity.

---

## Technical Constraints

### Hard Limits
1. **Single active job**: Only one generation at a time
2. **No job queue**: Requests rejected when busy (503)
3. **No persistence**: Jobs lost on service restart
4. **No distributed**: Single-instance only

### Soft Limits (Configurable)
1. **Result retention**: Default 1 hour (configurable)
2. **Max text length**: Default 5000 chars (configurable)
3. **Max upload size**: Default 10MB (configurable)
4. **Request timeout**: Default 300 seconds (configurable)

### Resource Assumptions
1. **Processing time**: 10-30 seconds typical per job
2. **Memory**: ~2-4GB for model + processing
3. **Storage**: ~100MB per hour of generated audio
4. **Network**: Local network latency (<10ms)

---

## API Design Philosophy

### RESTful Principles
- **Resources**: Jobs and results are resources
- **Idempotent GET**: Status and result endpoints
- **Stateless**: Each request self-contained
- **Clear semantics**: HTTP status codes map to outcomes

### Error Handling
- **Fail-fast**: Validate early, reject clearly
- **Informative**: Error messages guide resolution
- **Retry-friendly**: 503 with estimated wait time
- **No silent failures**: All errors logged and reported

### Client Expectations
1. **Poll, don't push**: Client polls status (no webhooks in MVP)
2. **Handle 503 gracefully**: Exponential backoff recommended
3. **Download promptly**: Results expire after retention period
4. **Validate inputs**: Client-side validation reduces server load

---

## Implementation Guidelines

### Code Organization
```
api_service.py       # Main FastAPI app (~200-300 lines)
slot_manager.py      # Single-slot state management (~100-150 lines)
config.yaml          # Configuration file
Dockerfile           # Container definition
docker-compose.yml   # Easy deployment setup
```

### State Management
- **In-memory only**: No database required for MVP
- **Volatile**: State lost on restart (acceptable for single-slot)
- **Minimal**: Track current job + recent completions (LRU cache)

### File Management
- **Auto-cleanup**: Background thread removes old files
- **Atomic writes**: Temp file + rename pattern
- **No locks**: Single-slot ensures no concurrent writes

### Error Recovery
- **Graceful degradation**: Return partial info on errors
- **Fail job, not service**: Individual job failures don't crash service
- **Log everything**: Structured logging for debugging

---

## Scalability Considerations

### What This Design Does NOT Support
❌ Multiple concurrent jobs  
❌ Job queuing  
❌ Distributed deployment  
❌ High availability  
❌ Load balancing  
❌ Horizontal scaling  

### Future Enhancements (Not in Scope)
- Multi-slot processing (requires queue system)
- Job persistence (requires database)
- Distributed workers (requires message broker)
- Auto-scaling (requires orchestration)
- Real-time webhooks (requires pub/sub)

### When to Revisit This Design
Consider a more complex architecture if:
1. **Traffic**: >1000 requests/hour consistently
2. **SLA**: <5 second response time required
3. **Availability**: 99.9%+ uptime needed
4. **Concurrency**: Multiple GPUs available
5. **Distribution**: Multi-region deployment needed

---

## Configuration Schema

```yaml
service:
  host: string (default: 0.0.0.0)
  port: integer (default: 8000)
  
processing:
  backend: onnx | pytorch (default: onnx)
  device: cpu | cuda (default: cpu)
  cpu_threads: integer (default: 4)
  execution_provider: cpu | cuda (default: cpu)
  
storage:
  output_dir: path (default: ./generated_audio)
  upload_dir: path (default: ./uploads)
  retention_hours: float (default: 1.0)
  max_upload_size_mb: integer (default: 10)
  
defaults:
  voice: string (default: Junhao)
  max_new_frames: integer (default: 375)
  voice_clone_max_text_tokens: integer (default: 75)
  do_sample: boolean (default: true)
  
limits:
  max_text_length: integer (default: 5000)
  request_timeout_seconds: integer (default: 300)
```

---

## Testing Strategy

### Unit Tests
- Slot manager state transitions
- Request validation logic
- File cleanup logic
- Configuration parsing

### Integration Tests
- Full job lifecycle (submit → poll → download)
- Error scenarios (busy, not found, invalid input)
- File retention and cleanup
- Backend switching (ONNX vs PyTorch)

### Load Tests
- Sequential job processing under load
- 503 handling under continuous requests
- Memory stability over 100+ jobs
- File cleanup under high turnover

### Manual Tests
- Docker build and run
- Health check endpoint
- API documentation (Swagger UI)
- Client examples (Python, cURL, JS)

---

## Monitoring & Observability

### Essential Metrics
1. **Slot utilization**: % time busy
2. **Job success rate**: completed / total
3. **Average processing time**: seconds per job
4. **Error rate**: failures / total
5. **Storage usage**: disk space consumed

### Logging Standards
- **Level**: INFO for requests, ERROR for failures
- **Format**: JSON structured logs
- **Fields**: timestamp, job_id, status, duration, error
- **Retention**: 7 days (configurable)

### Health Indicators
- Service responsive (HTTP 200 on /health)
- Model loaded successfully
- Disk space available (>1GB free)
- No crashes in last 5 minutes

---

## Security Considerations

### Trust Model
- **Network**: Assumes trusted network (VPN/internal)
- **Inputs**: Validates but doesn't sanitize for malicious content
- **Outputs**: Public within retention period

### Potential Risks
1. **DoS**: No rate limiting, vulnerable to spam
2. **Storage**: Could fill disk with uploads
3. **Content**: No content filtering (NSFW, hate speech, etc.)
4. **Privacy**: Text and audio not encrypted at rest

### Mitigation (If Needed)
- Add reverse proxy with rate limiting (nginx)
- Implement per-IP request limits
- Add content filtering middleware
- Enable disk quota alerts
- Add HTTPS termination at proxy

---

## Maintenance & Operations

### Routine Tasks
- Monitor disk usage (daily)
- Review error logs (weekly)
- Update dependencies (monthly)
- Backup model files (one-time)

### Deployment Checklist
- [ ] Config file reviewed and validated
- [ ] Storage directories created with permissions
- [ ] Model files downloaded and accessible
- [ ] Docker image built and tested
- [ ] Health check endpoint responding
- [ ] Sample request successful
- [ ] Logs being written correctly
- [ ] Cleanup job running

### Rollback Procedure
1. Stop new container
2. Start previous container version
3. Verify health check
4. Check logs for errors
5. Test sample request

---

## Version History

- **v0.1.0** (2026-05-10): Initial design and implementation
  - Single-slot async API
  - ONNX/PyTorch backend support
  - Docker deployment
  - Basic monitoring

---

## References

- [API.md](./API.md) - Full API documentation
- [README.md](./README.md) - Main project documentation
- [app.py](./app.py) - Existing web UI (reference)
- [moss_tts_nano_runtime.py](./moss_tts_nano_runtime.py) - TTS runtime (dependency)

---

## AI Agent Instructions

When working on this codebase, AI agents should:

1. **Respect the single-slot constraint**: Never implement queuing or parallelization
2. **Keep it simple**: Prefer single-file solutions over multi-module architectures
3. **Maintain async pattern**: Don't introduce synchronous blocking endpoints
4. **Preserve statelessness**: No persistent state beyond ephemeral job tracking
5. **Follow existing patterns**: Use same structure as moss_tts_nano_runtime.py
6. **Document changes**: Update this file when design decisions change
7. **Test thoroughly**: Every change should include integration test

### Adding Features
- ✅ New generation options (safe to add)
- ✅ Additional voices (safe to add)
- ✅ Better error messages (safe to add)
- ⚠️ Queuing system (requires design review)
- ⚠️ Multi-slot processing (requires design review)
- ⚠️ Persistent storage (requires design review)

---

Last Updated: 2026-05-10  
Document Owner: Architecture Team  
Review Cycle: Quarterly or on major changes
