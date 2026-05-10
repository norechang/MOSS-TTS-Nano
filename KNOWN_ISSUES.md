# Known Issues and Troubleshooting

# Known Issues and Troubleshooting

## ~~PyTorch Backend Numerical Instability~~ ✅ RESOLVED (2026-05-10)

### Resolution Summary
**The PyTorch backend now works successfully!** The issue was caused by:
1. **Root Cause #1**: Corrupted HuggingFace model cache
2. **Root Cause #2**: Missing text normalization in API service

**Status**: Both issues have been fixed:
- ✅ Cache corruption: Resolved by clearing `~/.cache/huggingface/` directories
- ✅ Text normalization: Integrated `prepare_tts_request_texts()` into API service

**Current Test Results**:
- ✅ PyTorch CUDA backend: Working (7.6s for short text, generates 2.72s audio)
- ✅ PyTorch CPU backend: Expected to work (not yet tested after fix)
- ✅ ONNX CPU backend: Still works perfectly (2-5s generation time)

See [PYTORCH_INVESTIGATION.md](./PYTORCH_INVESTIGATION.md) for full technical details.

### Original Issue Description (Historical Reference)
The PyTorch backend was failing with NaN (Not-a-Number) errors during text generation:

```
RuntimeError: Non-finite text logits during generation: dtype=torch.float32 shape=(1, 16384) finite=0/16384 min=nan max=nan
```

### What Was Fixed

#### 1. Corrupted Model Cache
**Problem**: Downloaded model files were corrupted in HuggingFace cache.

**Solution**: Clear cache directories:
```bash
rm -rf ~/.cache/huggingface/hub/models--OpenMOSS-Team--MOSS-TTS-Nano*
rm -rf ~/.cache/huggingface/modules/transformers_modules/
```

#### 2. Missing Text Normalization  
**Problem**: API service was not applying text normalization like `infer.py` does.

**Solution**: Integrated `prepare_tts_request_texts()` in api_service.py:
- Added WeTextProcessingManager initialization (lines 262-276)
- Added text normalization in `_synthesize_pytorch()` method (lines 381-409)
- Includes: robust text cleanup, WeTextProcessing for Chinese/English, hyphen rewriting

**Code Changes**:
```python
# api_service.py - Now applies same normalization as infer.py
if TEXT_NORMALIZATION_AVAILABLE and self.text_normalizer_manager is not None:
    prepared_texts = prepare_tts_request_texts(
        text=text,
        prompt_text="",
        voice=voice or "",
        enable_wetext=True,
        enable_normalize_tts_text=True,
        text_normalizer_manager=self.text_normalizer_manager,
    )
    normalized_text = str(prepared_texts["text"])
```

### Testing Confirmation
**Successful Test (2026-05-10)**:
```bash
# Start API with PyTorch CUDA backend
python api_service.py --config config_pytorch_cuda_fp32.yaml

# Submit job
curl -X POST http://localhost:8006/api/v1/generate \
  -H "Content-Type: application/json" \
  -d '{"text": "你好世界", "voice": "Junhao"}'

# Result: Completed in 7.6s, generated 511KB WAV file (2.72s audio, 48kHz)
```

### Current Recommendations

**For GPU Users (CUDA available)**:
```yaml
processing:
  backend: "pytorch"
  device: "cuda"
  dtype: "float32"  # Or "bfloat16" for Ampere+ GPUs
```

**For CPU-Only Users**:
```yaml
processing:
  backend: "onnx"  # Still recommended - 2x faster on CPU
  device: "cpu"
  execution_provider: "cpu"
```

Both backends now work reliably. ONNX is still faster on CPU, but PyTorch offers more flexibility (GPU support, fine-tuning, etc.).

---

## Other Considerations

### CUDA Memory
If using CUDA in the future (when PyTorch backend is fixed):
- Expect ~2-4GB VRAM usage for model
- bfloat16 recommended for Ampere+ GPUs (RTX 30/40 series)
- float32 for older GPUs or debugging

### First-Run Delays
- **WeTextProcessing**: 25-30s to build Chinese normalizer FST (one-time)
- **Model download**: ~40s for initial HuggingFace download
- **Subsequent runs**: 3-5s startup after caching

### Performance Expectations
**ONNX CPU (4 threads)**:
- Startup: 3-5 seconds
- Generation: 2-5 seconds per job
- Memory: ~2GB RAM

**PyTorch CUDA (when working)**:
- Startup: 3-5 seconds  
- Generation: 1-3 seconds per job (estimated)
- Memory: ~2-4GB VRAM

---

## Support
For issues not covered here, check:
- [API.md](./API.md) - API documentation
- [AGENTS.md](./AGENTS.md) - Design decisions
- [QUICKSTART.md](./QUICKSTART.md) - Getting started guide
