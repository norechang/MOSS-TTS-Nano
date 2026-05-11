"""
MOSS-TTS-Nano API Service

A lightweight, production-ready asynchronous API service for MOSS-TTS-Nano
with single-slot execution model.

Usage:
    python api_service.py
    python api_service.py --config config.yaml
    python api_service.py --backend onnx --device cpu --port 8000
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import gc
import io
import logging
import os
import tempfile
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import yaml
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from slot_manager import SingleSlotManager

# Import the appropriate runtime based on configuration
try:
    from moss_tts_nano_runtime import NanoTTSService, build_default_voice_presets
    PYTORCH_AVAILABLE = True
except ImportError:
    PYTORCH_AVAILABLE = False

try:
    from onnx_tts_runtime import OnnxTtsRuntime
    ONNX_AVAILABLE = True
except ImportError:
    ONNX_AVAILABLE = False

try:
    from text_normalization_pipeline import WeTextProcessingManager, prepare_tts_request_texts
    TEXT_NORMALIZATION_AVAILABLE = True
except ImportError:
    TEXT_NORMALIZATION_AVAILABLE = False


# ============================================================================
# Configuration
# ============================================================================

class ServiceConfig:
    """Service configuration loaded from YAML or command-line args."""
    
    def __init__(self, config_path: Optional[str] = None, **overrides):
        # Default configuration
        self.config = {
            "service": {
                "host": "0.0.0.0",
                "port": 8000,
                "title": "MOSS-TTS-Nano API",
                "description": "Lightweight asynchronous TTS API service",
                "version": "0.1.0",
            },
            "processing": {
                "backend": "onnx",
                "device": "cpu",
                "cpu_threads": 4,
                "execution_provider": "cpu",
                "model_dir": None,
                "checkpoint_path": None,
                "audio_tokenizer_path": None,
                "dtype": "auto",
                "attn_implementation": "auto",
                "clear_cache_before_generation": True,
                "clear_cache_after_generation": True,
            },
            "storage": {
                "output_dir": "./generated_audio",
                "upload_dir": "./uploads",
                "retention_hours": 1.0,
                "max_upload_size_mb": 10,
            },
            "defaults": {
                "voice": "Junhao",
                "max_new_frames": 375,
                "voice_clone_max_text_tokens": 75,
                "do_sample": True,
                "text_temperature": 1.0,
                "text_top_p": 1.0,
                "text_top_k": 50,
                "audio_temperature": 0.8,
                "audio_top_p": 0.95,
                "audio_top_k": 25,
                "audio_repetition_penalty": 1.2,
            },
            "limits": {
                "max_text_length": 5000,
                "request_timeout_seconds": 300,
            },
            "cors": {
                "enabled": True,
                "origins": ["*"],
                "methods": ["GET", "POST", "DELETE"],
                "headers": ["*"],
            },
            "logging": {
                "level": "INFO",
                "format": "text",
                "file": None,
            },
        }
        
        # Load from YAML file if provided
        if config_path and Path(config_path).exists():
            with open(config_path, "r") as f:
                yaml_config = yaml.safe_load(f)
                self._merge_config(self.config, yaml_config)
        
        # Apply command-line overrides
        self._apply_overrides(overrides)
        
        # Create directories
        Path(self.config["storage"]["output_dir"]).mkdir(parents=True, exist_ok=True)
        Path(self.config["storage"]["upload_dir"]).mkdir(parents=True, exist_ok=True)
    
    def _merge_config(self, base: dict, override: dict) -> None:
        """Recursively merge override config into base config."""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._merge_config(base[key], value)
            else:
                base[key] = value
    
    def _apply_overrides(self, overrides: dict) -> None:
        """Apply command-line overrides to configuration."""
        if "backend" in overrides and overrides["backend"]:
            self.config["processing"]["backend"] = overrides["backend"]
        if "device" in overrides and overrides["device"]:
            self.config["processing"]["device"] = overrides["device"]
        if "port" in overrides and overrides["port"]:
            self.config["service"]["port"] = overrides["port"]
        if "host" in overrides and overrides["host"]:
            self.config["service"]["host"] = overrides["host"]
    
    def get(self, *keys):
        """Get configuration value by dot-separated key path."""
        value = self.config
        for key in keys:
            value = value[key]
        return value


# ============================================================================
# Request/Response Models
# ============================================================================

class GenerationOptions(BaseModel):
    """Optional generation parameters."""
    max_new_frames: Optional[int] = Field(None, ge=64, le=1024)
    voice_clone_max_text_tokens: Optional[int] = Field(None, ge=25, le=200)
    do_sample: Optional[bool] = None
    text_temperature: Optional[float] = Field(None, ge=0.1, le=2.0)
    text_top_p: Optional[float] = Field(None, ge=0.1, le=1.0)
    text_top_k: Optional[int] = Field(None, ge=1, le=100)
    audio_temperature: Optional[float] = Field(None, ge=0.1, le=2.0)
    audio_top_p: Optional[float] = Field(None, ge=0.1, le=1.0)
    audio_top_k: Optional[int] = Field(None, ge=1, le=100)
    audio_repetition_penalty: Optional[float] = Field(None, ge=1.0, le=2.0)
    seed: Optional[int] = None


class GenerateRequest(BaseModel):
    """Request body for speech generation."""
    text: str = Field(..., min_length=1, max_length=5000)
    voice: Optional[str] = None
    reference_audio: Optional[str] = None  # base64 or upload_id
    options: Optional[GenerationOptions] = None


# ============================================================================
# TTS Runtime Manager
# ============================================================================

def clear_gpu_cache(device: str = "cpu", force: bool = False):
    """
    Clear GPU memory cache and Python garbage.
    
    Args:
        device: Device type ('cpu', 'cuda', 'mps')
        force: Force aggressive cache clearing even on CPU
    """
    # Always run garbage collection
    gc.collect()
    
    # Clear CUDA cache if using GPU
    if device.startswith("cuda"):
        try:
            import torch
            if torch.cuda.is_available():
                # Log memory before clearing
                allocated_before = torch.cuda.memory_allocated() / 1024**2  # MB
                reserved_before = torch.cuda.memory_reserved() / 1024**2  # MB
                
                # Clear cache and synchronize
                torch.cuda.empty_cache()
                torch.cuda.synchronize()
                
                # Log memory after clearing
                allocated_after = torch.cuda.memory_allocated() / 1024**2  # MB
                reserved_after = torch.cuda.memory_reserved() / 1024**2  # MB
                
                freed_allocated = allocated_before - allocated_after
                freed_reserved = reserved_before - reserved_after
                
                logging.info(
                    f"CUDA cache cleared: allocated {allocated_before:.1f}MB -> {allocated_after:.1f}MB "
                    f"(freed {freed_allocated:.1f}MB), reserved {reserved_before:.1f}MB -> {reserved_after:.1f}MB "
                    f"(freed {freed_reserved:.1f}MB)"
                )
        except ImportError:
            pass
    
    # Clear MPS cache for Apple Silicon
    elif device == "mps":
        try:
            import torch
            if hasattr(torch.mps, 'empty_cache'):
                torch.mps.empty_cache()
                logging.debug("Cleared MPS cache")
        except (ImportError, AttributeError):
            pass
    
    # For CPU or force mode, run additional garbage collection
    if force or device == "cpu":
        gc.collect()
        logging.debug("Ran garbage collection")


class TTSRuntimeManager:
    """Manages TTS runtime initialization and execution."""
    
    def __init__(self, config: ServiceConfig):
        self.config = config
        self.backend = config.get("processing", "backend")
        self.device = config.get("processing", "device")
        self.runtime = None
        self.voice_presets = {}
        self.text_normalizer_manager = None
        self._lock = threading.Lock()
    
    def initialize(self):
        """Initialize the TTS runtime."""
        with self._lock:
            if self.runtime is not None:
                return
            
            logging.info(f"Initializing TTS runtime: backend={self.backend}, device={self.device}")
            
            if self.backend == "onnx":
                if not ONNX_AVAILABLE:
                    raise RuntimeError("ONNX backend not available. Install onnxruntime.")
                self._initialize_onnx()
            elif self.backend == "pytorch":
                if not PYTORCH_AVAILABLE:
                    raise RuntimeError("PyTorch backend not available. Install torch and transformers.")
                self._initialize_pytorch()
            else:
                raise ValueError(f"Unknown backend: {self.backend}")
            
            logging.info("TTS runtime initialized successfully")
    
    def _initialize_onnx(self):
        """Initialize ONNX runtime."""
        from onnx_tts_runtime import OnnxTtsRuntime
        
        model_dir = self.config.get("processing", "model_dir")
        execution_provider = self.config.get("processing", "execution_provider")
        cpu_threads = self.config.get("processing", "cpu_threads")
        output_dir = self.config.get("storage", "output_dir")
        
        self.runtime = OnnxTtsRuntime(
            model_dir=model_dir,
            thread_count=cpu_threads,
            max_new_frames=self.config.get("defaults", "max_new_frames"),
            execution_provider=execution_provider,
            output_dir=output_dir,
        )
        
        # Get builtin voices from ONNX runtime
        builtin_voices = self.runtime.list_builtin_voices()
        for voice_info in builtin_voices:
            self.voice_presets[voice_info["voice"]] = voice_info
    
    def _initialize_pytorch(self):
        """Initialize PyTorch runtime."""
        from moss_tts_nano_runtime import NanoTTSService, build_default_voice_presets
        
        checkpoint_path = self.config.get("processing", "checkpoint_path")
        audio_tokenizer_path = self.config.get("processing", "audio_tokenizer_path")
        output_dir = self.config.get("storage", "output_dir")
        dtype = self.config.get("processing", "dtype") or "auto"
        attn_implementation = self.config.get("processing", "attn_implementation") or "auto"
        
        self.runtime = NanoTTSService(
            checkpoint_path=checkpoint_path or "OpenMOSS-Team/MOSS-TTS-Nano",
            audio_tokenizer_path=audio_tokenizer_path or "OpenMOSS-Team/MOSS-Audio-Tokenizer-Nano",
            device=self.device,
            dtype=dtype,
            attn_implementation=attn_implementation,
            output_dir=output_dir,
            voice_presets=build_default_voice_presets(),
        )
        
        # Initialize text normalization for PyTorch backend
        if TEXT_NORMALIZATION_AVAILABLE:
            logging.info("Initializing WeTextProcessing for text normalization...")
            self.text_normalizer_manager = WeTextProcessingManager()
            snapshot = self.text_normalizer_manager.ensure_ready()
            if snapshot.ready:
                logging.info("WeTextProcessing ready for API service: %s", snapshot.message)
            else:
                logging.warning("WeTextProcessing failed to initialize: %s", snapshot.error or snapshot.message)
                self.text_normalizer_manager = None
        else:
            logging.warning("Text normalization not available. Install WeTextProcessing for better results.")
        
        # Warm up the model
        logging.info("Warming up TTS model...")
        self.runtime.get_model()
        self.voice_presets = {name: {"voice": name, "description": preset.description} 
                             for name, preset in self.runtime.voice_presets.items()}
    
    def list_voices(self) -> list[dict]:
        """List available voices."""
        return [{"name": name, **info} for name, info in self.voice_presets.items()]
    
    def synthesize(
        self,
        text: str,
        voice: Optional[str],
        reference_audio_path: Optional[Path],
        options: Optional[GenerationOptions],
        output_path: Path,
    ) -> dict:
        """
        Synthesize speech with the loaded runtime.
        
        Automatically clears GPU/CPU cache before and after generation
        to prevent memory accumulation issues.
        
        Returns:
            Dictionary with generation results
        """
        # Clear cache before synthesis to free up memory
        if self.config.get("processing", "clear_cache_before_generation"):
            clear_gpu_cache(self.device, force=False)
            logging.debug(f"Cleared cache before generation (device={self.device})")
        
        try:
            # Merge options with defaults
            gen_options = self._merge_options(options)
            
            if self.backend == "onnx":
                result = self._synthesize_onnx(text, voice, reference_audio_path, gen_options, output_path)
            else:
                result = self._synthesize_pytorch(text, voice, reference_audio_path, gen_options, output_path)
            
            return result
            
        finally:
            # Always clear cache after synthesis, even if there was an error
            if self.config.get("processing", "clear_cache_after_generation"):
                clear_gpu_cache(self.device, force=True)
                logging.debug(f"Cleared cache after generation (device={self.device})")
    
    def _merge_options(self, options: Optional[GenerationOptions]) -> dict:
        """Merge request options with defaults."""
        defaults = self.config.get("defaults")
        merged = dict(defaults)
        
        if options:
            for key, value in options.model_dump(exclude_none=True).items():
                merged[key] = value
        
        return merged
    
    def _synthesize_onnx(
        self,
        text: str,
        voice: Optional[str],
        reference_audio_path: Optional[Path],
        options: dict,
        output_path: Path,
    ) -> dict:
        """Synthesize with ONNX runtime."""
        start_time = time.time()
        
        # Use reference audio if provided, otherwise use voice preset
        prompt_audio_path = None
        if reference_audio_path:
            prompt_audio_path = str(reference_audio_path)
        elif voice:
            # Voice preset will be resolved by the runtime
            pass
        
        result = self.runtime.synthesize(
            text=text,
            voice=voice,
            prompt_audio_path=prompt_audio_path,
            output_audio_path=str(output_path),
            max_new_frames=options["max_new_frames"],
            voice_clone_max_text_tokens=options["voice_clone_max_text_tokens"],
            do_sample=options["do_sample"],
            seed=options.get("seed"),
        )
        
        duration = time.time() - start_time
        
        return {
            "audio_path": result["audio_path"],
            "sample_rate": result.get("sample_rate", 48000),
            "audio_duration_seconds": result.get("audio_duration_seconds", 0.0),
            "processing_time": duration,
        }
    
    def _synthesize_pytorch(
        self,
        text: str,
        voice: Optional[str],
        reference_audio_path: Optional[Path],
        options: dict,
        output_path: Path,
    ) -> dict:
        """Synthesize with PyTorch runtime."""
        # Apply text normalization like infer.py does
        normalized_text = text
        if TEXT_NORMALIZATION_AVAILABLE and self.text_normalizer_manager is not None:
            try:
                prepared_texts = prepare_tts_request_texts(
                    text=text,
                    prompt_text="",
                    voice=voice or "",
                    enable_wetext=True,
                    enable_normalize_tts_text=True,
                    text_normalizer_manager=self.text_normalizer_manager,
                )
                normalized_text = str(prepared_texts["text"])
                logging.info(
                    "Applied text normalization: method=%s language=%s chars_before=%d chars_after=%d",
                    prepared_texts["normalization_method"],
                    prepared_texts["text_normalization_language"] or "n/a",
                    len(text),
                    len(normalized_text),
                )
            except Exception as e:
                logging.warning("Text normalization failed, using original text: %s", str(e))
                normalized_text = text
        
        result = self.runtime.synthesize(
            text=normalized_text,
            voice=voice,
            mode="voice_clone",
            output_audio_path=output_path,
            prompt_audio_path=reference_audio_path,
            max_new_frames=options["max_new_frames"],
            voice_clone_max_text_tokens=options["voice_clone_max_text_tokens"],
            do_sample=options["do_sample"],
            text_temperature=options["text_temperature"],
            text_top_p=options["text_top_p"],
            text_top_k=options["text_top_k"],
            audio_temperature=options["audio_temperature"],
            audio_top_p=options["audio_top_p"],
            audio_top_k=options["audio_top_k"],
            audio_repetition_penalty=options["audio_repetition_penalty"],
            seed=options.get("seed"),
        )
        
        # Calculate audio duration
        import numpy as np
        waveform = np.asarray(result["waveform_numpy"])
        sample_count = waveform.shape[0] if waveform.ndim >= 1 else 0
        sample_rate = result["sample_rate"]
        audio_duration = sample_count / sample_rate if sample_rate > 0 else 0.0
        
        return {
            "audio_path": result["audio_path"],
            "sample_rate": sample_rate,
            "audio_duration_seconds": audio_duration,
            "processing_time": result["elapsed_seconds"],
        }


# ============================================================================
# Global State
# ============================================================================

config: ServiceConfig = None
slot_manager: SingleSlotManager = None
runtime_manager: TTSRuntimeManager = None
cleanup_task: Optional[asyncio.Task] = None


# ============================================================================
# Background Tasks
# ============================================================================

async def cleanup_old_files():
    """Periodically clean up old files and jobs."""
    while True:
        try:
            await asyncio.sleep(300)  # Run every 5 minutes
            
            retention_hours = config.get("storage", "retention_hours")
            cutoff_time = time.time() - (retention_hours * 3600)
            
            # Clean up generated audio files
            output_dir = Path(config.get("storage", "output_dir"))
            for file_path in output_dir.glob("*.wav"):
                try:
                    if file_path.stat().st_mtime < cutoff_time:
                        file_path.unlink()
                        logging.debug(f"Deleted old file: {file_path}")
                except Exception as e:
                    logging.warning(f"Failed to delete file {file_path}: {e}")
            
            # Clean up uploaded reference audio
            upload_dir = Path(config.get("storage", "upload_dir"))
            for file_path in upload_dir.glob("*"):
                try:
                    if file_path.stat().st_mtime < cutoff_time:
                        file_path.unlink()
                        logging.debug(f"Deleted old upload: {file_path}")
                except Exception as e:
                    logging.warning(f"Failed to delete upload {file_path}: {e}")
            
            # Clean up old jobs from memory
            cleaned = slot_manager.cleanup_old_results(retention_hours)
            if cleaned > 0:
                logging.info(f"Cleaned up {cleaned} old jobs from memory")
                
        except Exception as e:
            logging.error(f"Error in cleanup task: {e}")


# ============================================================================
# FastAPI Application
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global cleanup_task
    
    # Startup
    logging.info("Starting MOSS-TTS-Nano API service...")
    runtime_manager.initialize()
    cleanup_task = asyncio.create_task(cleanup_old_files())
    logging.info("Service started successfully")
    
    yield
    
    # Shutdown
    logging.info("Shutting down service...")
    if cleanup_task:
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass
    logging.info("Service stopped")


def create_app(config_obj: ServiceConfig) -> FastAPI:
    """Create and configure the FastAPI application."""
    global config, slot_manager, runtime_manager
    
    config = config_obj
    slot_manager = SingleSlotManager(max_completed_jobs=100)
    runtime_manager = TTSRuntimeManager(config)
    
    app = FastAPI(
        title=config.get("service", "title"),
        description=config.get("service", "description"),
        version=config.get("service", "version"),
        lifespan=lifespan,
    )
    
    # CORS middleware
    if config.get("cors", "enabled"):
        app.add_middleware(
            CORSMiddleware,
            allow_origins=config.get("cors", "origins"),
            allow_credentials=True,
            allow_methods=config.get("cors", "methods"),
            allow_headers=config.get("cors", "headers"),
        )
    
    # Register routes
    register_routes(app)
    
    return app


# ============================================================================
# API Endpoints
# ============================================================================

def register_routes(app: FastAPI):
    """Register all API routes to the FastAPI app."""
    
    @app.post("/api/v1/generate")
    async def generate_speech(request: GenerateRequest):
        """
        Submit a speech generation job.
        
        Returns 202 if accepted, 503 if slot is busy.
        """
        # Check if slot is available
        if not slot_manager.is_available():
            slot_status = slot_manager.get_slot_status()
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "service_busy",
                    "message": "Processing slot is currently occupied. Please try again later.",
                    "current_job_id": slot_status.get("current_job_id"),
                    "estimated_wait_seconds": slot_status.get("estimated_wait_seconds"),
                }
            )
        
        # Validate text length
        max_length = config.get("limits", "max_text_length")
        if len(request.text) > max_length:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "validation_error",
                    "message": f"Text exceeds maximum length of {max_length} characters",
                }
            )
        
        # Create job
        try:
            job = slot_manager.create_job(
                text=request.text,
                voice=request.voice or config.get("defaults", "voice"),
                metadata={"options": request.options.model_dump() if request.options else {}},
            )
        except RuntimeError as e:
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "service_busy",
                    "message": str(e),
                }
            )
        
        # Process job in background
        asyncio.create_task(process_job(job.job_id, request))
        
        return JSONResponse(
            status_code=202,
            content={
                "job_id": job.job_id,
                "status": "processing",
                "created_at": job.to_dict()["created_at"],
                "message": "Job accepted and processing started",
            }
        )




    async def process_job(job_id: str, request: GenerateRequest):
        """Process a speech generation job in the background."""
        try:
            # Handle reference audio
            reference_audio_path = None
            if request.reference_audio:
                # TODO: Handle base64 or upload_id
                pass
        
            # Generate output path
            output_dir = Path(config.get("storage", "output_dir"))
            output_path = output_dir / f"{job_id}.wav"
        
            # Update progress
            slot_manager.update_progress(job_id, 0.1)
        
            # Synthesize speech
            result = await asyncio.to_thread(
                runtime_manager.synthesize,
                text=request.text,
                voice=request.voice,
                reference_audio_path=reference_audio_path,
                options=request.options,
                output_path=output_path,
            )
        
            # Mark job as completed
            slot_manager.complete_job(
                job_id=job_id,
                result_path=Path(result["audio_path"]),
                audio_duration_seconds=result["audio_duration_seconds"],
                sample_rate=result["sample_rate"],
            )
        
            logging.info(f"Job {job_id} completed successfully")
        
        except Exception as e:
            logging.error(f"Job {job_id} failed: {e}", exc_info=True)
            slot_manager.fail_job(
                job_id=job_id,
                error="generation_error",
                error_details=str(e),
            )


    @app.get("/api/v1/status/{job_id}")
    async def get_job_status(job_id: str):
        """Get the status of a job."""
        job = slot_manager.get_job(job_id)
        if job is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "job_not_found",
                    "message": "Job ID not found or has expired",
                }
            )
    
        return job.to_dict()


    @app.get("/api/v1/result/{job_id}")
    async def get_job_result(job_id: str):
        """Download the generated audio file."""
        job = slot_manager.get_job(job_id)
        if job is None or job.status != "completed" or job.result_path is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "result_not_found",
                    "message": "Result not available. Job may not be completed or has expired.",
                }
            )
    
        if not job.result_path.exists():
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "result_not_found",
                    "message": "Result file has been deleted (expired).",
                }
            )
    
        return FileResponse(
            path=job.result_path,
            media_type="audio/wav",
            filename=f"tts_output_{job_id}.wav",
        )


    @app.get("/api/v1/slot")
    async def get_slot_status():
        """Check if the processing slot is available."""
        return slot_manager.get_slot_status()


    @app.get("/api/v1/voices")
    async def list_voices():
        """List available preset voices."""
        voices = runtime_manager.list_voices()
        default_voice = config.get("defaults", "voice")
    
        return {
            "voices": voices,
            "default_voice": default_voice,
            "total_count": len(voices),
        }


    @app.post("/api/v1/voices/upload")
    async def upload_reference_audio(file: UploadFile = File(...)):
        """Upload a reference audio file for voice cloning."""
        # Check file size
        max_size = config.get("storage", "max_upload_size_mb") * 1024 * 1024
        content = await file.read()
        if len(content) > max_size:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "file_too_large",
                    "message": f"File size exceeds maximum of {config.get('storage', 'max_upload_size_mb')} MB",
                }
            )
    
        # Save file
        upload_dir = Path(config.get("storage", "upload_dir"))
        upload_id = f"ref_audio_{int(time.time())}_{file.filename}"
        upload_path = upload_dir / upload_id
    
        with open(upload_path, "wb") as f:
            f.write(content)
    
        # Calculate expiration time
        retention_hours = config.get("storage", "retention_hours")
        expires_at = time.time() + (retention_hours * 3600)
    
        return {
            "upload_id": upload_id,
            "filename": file.filename,
            "message": "Reference audio uploaded successfully",
            "expires_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(expires_at)),
        }


    @app.get("/api/v1/metrics")
    async def get_metrics():
        """Get service usage metrics."""
        return slot_manager.get_metrics()


    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        slot_status = slot_manager.get_slot_status()
        metrics = slot_manager.get_metrics()
    
        return {
            "status": "healthy",
            "service": "moss-tts-nano-api",
            "version": config.get("service", "version"),
            "backend": config.get("processing", "backend"),
            "device": config.get("processing", "device"),
            "slot_status": slot_status["status"],
            "uptime_seconds": metrics["uptime_seconds"],
        }



# ============================================================================
# Main Entry Point
# ============================================================================

def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="MOSS-TTS-Nano API Service"
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config.yaml",
        help="Path to configuration file (default: config.yaml)"
    )
    parser.add_argument(
        "--backend",
        type=str,
        choices=["onnx", "pytorch"],
        help="TTS backend (onnx or pytorch)"
    )
    parser.add_argument(
        "--device",
        type=str,
        choices=["cpu", "cuda"],
        help="Processing device (cpu or cuda)"
    )
    parser.add_argument(
        "--port",
        type=int,
        help="Server port"
    )
    parser.add_argument(
        "--host",
        type=str,
        help="Server host"
    )
    return parser.parse_args()


def setup_logging(config: ServiceConfig):
    """Setup logging configuration."""
    level = getattr(logging, config.get("logging", "level"))
    log_format = config.get("logging", "format")
    log_file = config.get("logging", "file")
    
    if log_format == "json":
        import json
        
        class JsonFormatter(logging.Formatter):
            def format(self, record):
                return json.dumps({
                    "timestamp": self.formatTime(record),
                    "level": record.levelname,
                    "logger": record.name,
                    "message": record.getMessage(),
                })
        
        formatter = JsonFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
    
    handlers = []
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    handlers.append(console_handler)
    
    # File handler
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)
    
    logging.basicConfig(
        level=level,
        handlers=handlers,
    )


def main():
    """Main entry point."""
    global app
    
    args = parse_args()
    
    # Load configuration
    config_path = args.config if Path(args.config).exists() else None
    service_config = ServiceConfig(
        config_path=config_path,
        backend=args.backend,
        device=args.device,
        port=args.port,
        host=args.host,
    )
    
    # Setup logging
    setup_logging(service_config)
    
    # Create app
    app = create_app(service_config)
    
    # Run server
    import uvicorn
    
    host = service_config.get("service", "host")
    port = service_config.get("service", "port")
    
    logging.info(f"Starting server on {host}:{port}")
    logging.info(f"Backend: {service_config.get('processing', 'backend')}")
    logging.info(f"Device: {service_config.get('processing', 'device')}")
    logging.info(f"API documentation: http://{host}:{port}/docs")
    
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_config=None,  # Use our own logging config
    )


if __name__ == "__main__":
    main()
