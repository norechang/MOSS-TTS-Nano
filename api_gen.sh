#!/bin/bash
# API Generation Test Script
# Similar to gen.sh but uses the deployed API service instead of direct Python call

set -e

# Configuration
API_URL="${API_URL:-http://localhost:8002}"
TEXT_FILE="${1:-sample1.txt}"
OUTPUT_DIR="${OUTPUT_DIR:-./api_test_output}"
VOICE="${VOICE:-Junhao}"
POLL_INTERVAL=2
MAX_WAIT=120

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo "======================================================================"
echo "MOSS-TTS-Nano API Generation Test"
echo "======================================================================"
echo "API URL: $API_URL"
echo "Text file: $TEXT_FILE"
echo "Voice: $VOICE"
echo "Output directory: $OUTPUT_DIR"
echo ""

# Check if text file exists
if [ ! -f "$TEXT_FILE" ]; then
    echo -e "${RED}Error: Text file '$TEXT_FILE' not found${NC}"
    echo "Usage: $0 [text_file] [voice]"
    echo "Example: $0 sample1.txt Junhao"
    exit 1
fi

# Read text from file
TEXT=$(cat "$TEXT_FILE")
echo -e "${YELLOW}Text to generate:${NC}"
echo "$TEXT"
echo ""

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Check API health
echo -e "${YELLOW}Checking API health...${NC}"
HEALTH=$(curl -s "$API_URL/health")
if [ $? -ne 0 ]; then
    echo -e "${RED}Error: Cannot connect to API at $API_URL${NC}"
    echo "Make sure the service is running:"
    echo "  docker compose up -d"
    exit 1
fi

STATUS=$(echo "$HEALTH" | jq -r '.status')
BACKEND=$(echo "$HEALTH" | jq -r '.backend')
DEVICE=$(echo "$HEALTH" | jq -r '.device')
SLOT_STATUS=$(echo "$HEALTH" | jq -r '.slot_status')

echo -e "${GREEN}✓ API is healthy${NC}"
echo "  Backend: $BACKEND"
echo "  Device: $DEVICE"
echo "  Slot status: $SLOT_STATUS"
echo ""

# Check if slot is available
if [ "$SLOT_STATUS" != "idle" ]; then
    echo -e "${RED}Warning: Processing slot is busy${NC}"
    echo "Waiting for slot to become available..."
    
    WAIT_TIME=0
    while [ "$SLOT_STATUS" != "idle" ] && [ $WAIT_TIME -lt $MAX_WAIT ]; do
        sleep $POLL_INTERVAL
        WAIT_TIME=$((WAIT_TIME + POLL_INTERVAL))
        HEALTH=$(curl -s "$API_URL/health")
        SLOT_STATUS=$(echo "$HEALTH" | jq -r '.slot_status')
        echo "  Waiting... ($WAIT_TIME seconds)"
    done
    
    if [ "$SLOT_STATUS" != "idle" ]; then
        echo -e "${RED}Error: Slot is still busy after $MAX_WAIT seconds${NC}"
        exit 1
    fi
fi

# Submit generation job
echo -e "${YELLOW}Submitting generation job...${NC}"
PAYLOAD=$(jq -n \
    --arg text "$TEXT" \
    --arg voice "$VOICE" \
    '{text: $text, voice: $voice}')

RESPONSE=$(curl -s -X POST "$API_URL/api/v1/generate" \
    -H "Content-Type: application/json" \
    -d "$PAYLOAD")

# Check if job was accepted
HTTP_STATUS=$(echo "$RESPONSE" | jq -r 'if has("job_id") then "202" else "error" end')

if [ "$HTTP_STATUS" == "error" ]; then
    echo -e "${RED}Error: Job submission failed${NC}"
    echo "$RESPONSE" | jq '.'
    exit 1
fi

JOB_ID=$(echo "$RESPONSE" | jq -r '.job_id')
echo -e "${GREEN}✓ Job submitted successfully${NC}"
echo "  Job ID: $JOB_ID"
echo ""

# Poll job status
echo -e "${YELLOW}Waiting for job completion...${NC}"
ELAPSED=0
STATUS="processing"

while [ "$STATUS" == "processing" ] || [ "$STATUS" == "pending" ]; do
    if [ $ELAPSED -ge $MAX_WAIT ]; then
        echo -e "${RED}Error: Job timeout after $MAX_WAIT seconds${NC}"
        exit 1
    fi
    
    sleep $POLL_INTERVAL
    ELAPSED=$((ELAPSED + POLL_INTERVAL))
    
    STATUS_RESPONSE=$(curl -s "$API_URL/api/v1/status/$JOB_ID")
    STATUS=$(echo "$STATUS_RESPONSE" | jq -r '.status')
    PROGRESS=$(echo "$STATUS_RESPONSE" | jq -r '.progress // 0')
    
    # Convert progress to percentage
    PERCENT=$(echo "$PROGRESS * 100" | bc -l | cut -d. -f1)
    
    echo "  Status: $STATUS | Progress: ${PERCENT}% | Elapsed: ${ELAPSED}s"
done

echo ""

# Check final status
if [ "$STATUS" != "completed" ]; then
    echo -e "${RED}Error: Job failed${NC}"
    ERROR=$(echo "$STATUS_RESPONSE" | jq -r '.error // "Unknown error"')
    echo "  Error: $ERROR"
    echo ""
    echo "Full response:"
    echo "$STATUS_RESPONSE" | jq '.'
    exit 1
fi

# Get job completion details
DURATION=$(echo "$STATUS_RESPONSE" | jq -r '.duration_seconds')
AUDIO_DURATION=$(echo "$STATUS_RESPONSE" | jq -r '.audio_duration_seconds')
SAMPLE_RATE=$(echo "$STATUS_RESPONSE" | jq -r '.sample_rate')

echo -e "${GREEN}✓ Job completed successfully${NC}"
echo "  Processing time: ${DURATION}s"
echo "  Audio duration: ${AUDIO_DURATION}s"
echo "  Sample rate: ${SAMPLE_RATE}Hz"
echo ""

# Download result
echo -e "${YELLOW}Downloading audio...${NC}"
OUTPUT_FILE="$OUTPUT_DIR/output_${JOB_ID}.wav"

curl -s "$API_URL/api/v1/result/$JOB_ID" -o "$OUTPUT_FILE"

if [ $? -ne 0 ]; then
    echo -e "${RED}Error: Failed to download audio${NC}"
    exit 1
fi

# Check if file exists and has content
if [ ! -f "$OUTPUT_FILE" ] || [ ! -s "$OUTPUT_FILE" ]; then
    echo -e "${RED}Error: Downloaded file is empty${NC}"
    exit 1
fi

FILE_SIZE=$(ls -lh "$OUTPUT_FILE" | awk '{print $5}')
echo -e "${GREEN}✓ Audio downloaded successfully${NC}"
echo "  File: $OUTPUT_FILE"
echo "  Size: $FILE_SIZE"
echo ""

# Show metrics
echo -e "${YELLOW}API Metrics:${NC}"
METRICS=$(curl -s "$API_URL/api/v1/metrics")
echo "$METRICS" | jq '.'
echo ""

echo "======================================================================"
echo -e "${GREEN}Generation completed successfully!${NC}"
echo "======================================================================"
echo "Output file: $OUTPUT_FILE"
echo ""
echo "To play the audio:"
echo "  ffplay \"$OUTPUT_FILE\""
echo "  # or"
echo "  aplay \"$OUTPUT_FILE\""
echo ""
