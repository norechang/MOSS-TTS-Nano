"""
Single-slot job manager for MOSS-TTS-Nano API service.

This module implements a simple, lightweight job management system that enforces
a single-slot execution model: only one job can be processed at a time.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional

JobStatus = Literal["processing", "completed", "failed"]


@dataclass
class JobInfo:
    """Information about a TTS generation job."""
    
    job_id: str
    status: JobStatus
    created_at: float
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    text: str = ""
    voice: Optional[str] = None
    progress: float = 0.0
    error: Optional[str] = None
    error_details: Optional[str] = None
    result_path: Optional[Path] = None
    audio_duration_seconds: Optional[float] = None
    sample_rate: int = 48000
    metadata: dict = field(default_factory=dict)

    @property
    def duration_seconds(self) -> Optional[float]:
        """Calculate job duration in seconds."""
        if self.started_at is None:
            return None
        end_time = self.completed_at if self.completed_at is not None else time.time()
        return end_time - self.started_at

    def to_dict(self) -> dict:
        """Convert job info to dictionary for API response."""
        return {
            "job_id": self.job_id,
            "status": self.status,
            "progress": self.progress,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.created_at)),
            "started_at": (
                time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.started_at))
                if self.started_at is not None
                else None
            ),
            "completed_at": (
                time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.completed_at))
                if self.completed_at is not None
                else None
            ),
            "duration_seconds": self.duration_seconds,
            "error": self.error,
            "message": self._get_message(),
            "result_url": f"/api/v1/result/{self.job_id}" if self.status == "completed" else None,
            "audio_duration_seconds": self.audio_duration_seconds,
            "sample_rate": self.sample_rate,
        }

    def _get_message(self) -> str:
        """Get human-readable status message."""
        if self.status == "processing":
            return "Generating speech..."
        elif self.status == "completed":
            return "Speech generation completed successfully"
        elif self.status == "failed":
            return f"Speech generation failed: {self.error or 'Unknown error'}"
        return "Unknown status"


class SingleSlotManager:
    """
    Manages a single processing slot for TTS generation jobs.
    
    This manager enforces sequential job execution: only one job can be
    active at a time. New jobs are rejected with a "service busy" error
    when the slot is occupied.
    """

    def __init__(self, max_completed_jobs: int = 100):
        """
        Initialize the single-slot manager.
        
        Args:
            max_completed_jobs: Maximum number of completed jobs to keep in memory
        """
        self._lock = threading.RLock()
        self._current_job: Optional[JobInfo] = None
        self._completed_jobs: OrderedDict[str, JobInfo] = OrderedDict()
        self._max_completed_jobs = max_completed_jobs
        
        # Statistics
        self._total_jobs = 0
        self._total_completed = 0
        self._total_failed = 0
        self._total_processing_time = 0.0
        self._service_start_time = time.time()

    def is_available(self) -> bool:
        """Check if the processing slot is available."""
        with self._lock:
            return self._current_job is None

    def get_current_job(self) -> Optional[JobInfo]:
        """Get the currently processing job."""
        with self._lock:
            return self._current_job

    def create_job(self, text: str, voice: Optional[str] = None, metadata: Optional[dict] = None) -> JobInfo:
        """
        Create a new job and occupy the processing slot.
        
        Args:
            text: Text to synthesize
            voice: Voice name
            metadata: Additional job metadata
            
        Returns:
            JobInfo object for the created job
            
        Raises:
            RuntimeError: If the processing slot is already occupied
        """
        with self._lock:
            if self._current_job is not None:
                raise RuntimeError("Processing slot is occupied")

            job_id = f"job_{uuid.uuid4().hex}"
            job = JobInfo(
                job_id=job_id,
                status="processing",
                created_at=time.time(),
                started_at=time.time(),
                text=text,
                voice=voice,
                metadata=metadata or {},
            )
            
            self._current_job = job
            self._total_jobs += 1
            
            return job

    def update_progress(self, job_id: str, progress: float) -> None:
        """
        Update job progress.
        
        Args:
            job_id: Job ID
            progress: Progress value (0.0 to 1.0)
        """
        with self._lock:
            if self._current_job is not None and self._current_job.job_id == job_id:
                self._current_job.progress = max(0.0, min(1.0, progress))

    def complete_job(
        self,
        job_id: str,
        result_path: Path,
        audio_duration_seconds: float,
        sample_rate: int = 48000,
    ) -> None:
        """
        Mark job as completed and free the processing slot.
        
        Args:
            job_id: Job ID
            result_path: Path to generated audio file
            audio_duration_seconds: Duration of generated audio
            sample_rate: Audio sample rate
        """
        with self._lock:
            if self._current_job is None or self._current_job.job_id != job_id:
                return

            self._current_job.status = "completed"
            self._current_job.completed_at = time.time()
            self._current_job.progress = 1.0
            self._current_job.result_path = result_path
            self._current_job.audio_duration_seconds = audio_duration_seconds
            self._current_job.sample_rate = sample_rate

            # Move to completed jobs
            self._completed_jobs[job_id] = self._current_job
            self._current_job = None
            
            # Update statistics
            self._total_completed += 1
            if self._completed_jobs[job_id].duration_seconds:
                self._total_processing_time += self._completed_jobs[job_id].duration_seconds

            # Limit completed jobs cache
            while len(self._completed_jobs) > self._max_completed_jobs:
                self._completed_jobs.popitem(last=False)

    def fail_job(self, job_id: str, error: str, error_details: Optional[str] = None) -> None:
        """
        Mark job as failed and free the processing slot.
        
        Args:
            job_id: Job ID
            error: Error message
            error_details: Detailed error information
        """
        with self._lock:
            if self._current_job is None or self._current_job.job_id != job_id:
                return

            self._current_job.status = "failed"
            self._current_job.completed_at = time.time()
            self._current_job.error = error
            self._current_job.error_details = error_details

            # Move to completed jobs
            self._completed_jobs[job_id] = self._current_job
            self._current_job = None
            
            # Update statistics
            self._total_failed += 1

            # Limit completed jobs cache
            while len(self._completed_jobs) > self._max_completed_jobs:
                self._completed_jobs.popitem(last=False)

    def get_job(self, job_id: str) -> Optional[JobInfo]:
        """
        Get job information by ID.
        
        Args:
            job_id: Job ID
            
        Returns:
            JobInfo if found, None otherwise
        """
        with self._lock:
            if self._current_job is not None and self._current_job.job_id == job_id:
                return self._current_job
            return self._completed_jobs.get(job_id)

    def get_slot_status(self) -> dict:
        """
        Get current slot status information.
        
        Returns:
            Dictionary with slot status details
        """
        with self._lock:
            if self._current_job is None:
                return {
                    "available": True,
                    "status": "idle",
                    "message": "Processing slot is available",
                }
            
            # Estimate wait time based on progress
            estimated_wait = None
            if self._current_job.duration_seconds and self._current_job.progress > 0.1:
                elapsed = self._current_job.duration_seconds
                estimated_total = elapsed / self._current_job.progress
                estimated_wait = max(1, int(estimated_total - elapsed))
            
            return {
                "available": False,
                "status": "busy",
                "current_job_id": self._current_job.job_id,
                "current_job_progress": self._current_job.progress,
                "estimated_wait_seconds": estimated_wait,
                "message": "Processing slot is currently occupied",
            }

    def get_metrics(self) -> dict:
        """
        Get service usage metrics.
        
        Returns:
            Dictionary with service metrics
        """
        with self._lock:
            uptime = time.time() - self._service_start_time
            avg_time = (
                self._total_processing_time / self._total_completed
                if self._total_completed > 0
                else 0.0
            )
            
            return {
                "total_jobs_processed": self._total_jobs,
                "jobs_completed": self._total_completed,
                "jobs_failed": self._total_failed,
                "average_processing_time_seconds": round(avg_time, 2),
                "current_status": "busy" if self._current_job is not None else "idle",
                "uptime_seconds": int(uptime),
                "service_start_time": time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ",
                    time.gmtime(self._service_start_time)
                ),
            }

    def cleanup_old_results(self, retention_hours: float = 1.0) -> int:
        """
        Clean up old completed jobs from memory.
        
        Args:
            retention_hours: How long to keep completed jobs in memory
            
        Returns:
            Number of jobs cleaned up
        """
        with self._lock:
            cutoff_time = time.time() - (retention_hours * 3600)
            jobs_to_remove = []
            
            for job_id, job in self._completed_jobs.items():
                if job.completed_at and job.completed_at < cutoff_time:
                    jobs_to_remove.append(job_id)
            
            for job_id in jobs_to_remove:
                del self._completed_jobs[job_id]
            
            return len(jobs_to_remove)
