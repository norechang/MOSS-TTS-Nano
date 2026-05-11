# API Generation Test Script

`api_gen.sh` is a convenient bash script for testing the deployed MOSS-TTS-Nano API service. It provides a similar interface to `gen.sh` but uses the REST API instead of direct Python calls.

## Features

- ✅ Health check before submission
- ✅ Automatic slot availability detection
- ✅ Real-time progress monitoring
- ✅ Automatic audio download
- ✅ Detailed metrics reporting
- ✅ Colored output for better readability
- ✅ Error handling and validation

## Prerequisites

- `curl` - for HTTP requests
- `jq` - for JSON parsing
- `bc` - for floating-point calculations

Install dependencies:
```bash
# Ubuntu/Debian
sudo apt install curl jq bc

# macOS
brew install curl jq bc

# RHEL/CentOS
sudo yum install curl jq bc
```

## Usage

### Basic Usage

```bash
./api_gen.sh [text_file] [voice]
```

**Parameters:**
- `text_file` - Path to text file (default: `sample1.txt`)
- `voice` - Voice name (default: `Junhao`)

### Examples

```bash
# Generate with default settings (sample1.txt, Junhao voice)
./api_gen.sh

# Generate from specific text file
./api_gen.sh my_text.txt

# Generate with different voice
./api_gen.sh sample1.txt Ava

# Use custom API URL
API_URL=http://192.168.1.100:8002 ./api_gen.sh sample1.txt
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `API_URL` | API service URL | `http://localhost:8002` |
| `OUTPUT_DIR` | Output directory for audio files | `./api_test_output` |
| `VOICE` | Default voice name | `Junhao` |

### Advanced Usage

```bash
# Remote API server
API_URL=https://tts.example.com ./api_gen.sh input.txt

# Custom output directory
OUTPUT_DIR=/tmp/tts_output ./api_gen.sh input.txt

# Combine multiple options
API_URL=http://192.168.1.10:8002 \
OUTPUT_DIR=~/audio \
VOICE=Zhiming \
./api_gen.sh chinese_text.txt
```

## Output

The script provides detailed progress information:

```
======================================================================
MOSS-TTS-Nano API Generation Test
======================================================================
API URL: http://localhost:8002
Text file: sample1.txt
Voice: Junhao
Output directory: ./api_test_output

Text to generate:
今日科技新聞摘要...

✓ API is healthy
  Backend: onnx
  Device: cpu
  Slot status: idle

✓ Job submitted successfully
  Job ID: job_abc123...

Waiting for job completion...
  Status: processing | Progress: 50% | Elapsed: 10s

✓ Job completed successfully
  Processing time: 20.5s
  Audio duration: 15.2s
  Sample rate: 48000Hz

✓ Audio downloaded successfully
  File: ./api_test_output/output_job_abc123.wav
  Size: 5.2M

API Metrics:
{
  "total_jobs_processed": 42,
  "jobs_completed": 42,
  "jobs_failed": 0,
  "average_processing_time_seconds": 18.3,
  ...
}

======================================================================
Generation completed successfully!
======================================================================
```

## Workflow

1. **Health Check**: Verifies API is running and healthy
2. **Slot Check**: Waits if processing slot is busy
3. **Job Submission**: Submits text to `/api/v1/generate`
4. **Progress Monitoring**: Polls `/api/v1/status/{job_id}` every 2 seconds
5. **Result Download**: Downloads audio from `/api/v1/result/{job_id}`
6. **Metrics Display**: Shows service metrics

## Error Handling

The script handles common errors gracefully:

- **API Unavailable**: Connection refused or timeout
- **Slot Busy**: Waits for slot to become available (max 120s)
- **Job Timeout**: Fails if job doesn't complete in 120s
- **Job Failed**: Displays error message from API
- **Download Failed**: Reports download errors

## Exit Codes

- `0` - Success
- `1` - Error (API unavailable, job failed, timeout, etc.)

## Comparison with gen.sh

| Feature | gen.sh | api_gen.sh |
|---------|--------|------------|
| **Interface** | Direct Python call | REST API |
| **Dependencies** | Python, conda, model files | curl, jq |
| **Environment** | Requires conda env | Works anywhere |
| **Deployment** | Local only | Local or remote |
| **Concurrency** | Single-threaded | Managed by API |
| **Monitoring** | Limited | Full progress tracking |
| **Output** | Direct file | Downloaded via API |

## Examples

### Generate Chinese Text

```bash
echo "欢迎使用MOSS语音合成系统" > chinese.txt
./api_gen.sh chinese.txt Junhao
```

### Generate English Text

```bash
echo "Welcome to MOSS text-to-speech system" > english.txt
./api_gen.sh english.txt Ava
```

### Batch Processing

```bash
#!/bin/bash
for file in texts/*.txt; do
    echo "Processing $file..."
    ./api_gen.sh "$file"
done
```

### Remote Server

```bash
# Deploy API on server
ssh user@server "cd /path/to/moss && docker compose up -d"

# Generate from local machine
API_URL=http://server:8002 ./api_gen.sh my_text.txt
```

## Troubleshooting

### Cannot connect to API

```bash
# Check if service is running
curl http://localhost:8002/health

# Start service if not running
docker compose up -d

# Check logs
docker compose logs -f
```

### Slot is busy

```bash
# Check slot status
curl http://localhost:8002/api/v1/slot | jq

# Wait or cancel current job if needed
```

### jq not found

```bash
# Install jq
sudo apt install jq  # Ubuntu/Debian
brew install jq      # macOS
```

## Files Generated

- **Audio files**: `{OUTPUT_DIR}/output_{job_id}.wav`
- **Format**: WAV, 48kHz, 16-bit stereo
- **Naming**: Includes job ID for uniqueness

## Performance Tips

1. **Use ONNX backend** for faster CPU processing (2-5s typical)
2. **Use PyTorch CUDA** for GPU acceleration if available
3. **Check slot status** before submitting multiple jobs
4. **Adjust timeout** for very long texts (modify `MAX_WAIT` in script)

## See Also

- [API.md](API.md) - Complete API documentation
- [README_API.md](README_API.md) - API service guide
- [api_validate/](api_validate/) - Comprehensive test suite
- [QUICKSTART.md](QUICKSTART.md) - Getting started guide

## License

Same as MOSS-TTS-Nano project.
