from __future__ import annotations
import logging
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response
from fastapi.responses import FileResponse, JSONResponse
from config.settings import Settings, get_settings
from models.api import CreateReviewRequest, CreateReviewResponse, JobStatusResponse, JobResultResponse
from services.job_manager import JobManager
from services.pipeline_runner import PipelineRunner
from services.cache_service import CacheService, get_cache_service

logger = logging.getLogger(__name__)
router = APIRouter()

# Singletons (initialized lazily)
_job_manager: JobManager | None = None
_pipeline_runner: PipelineRunner | None = None
_cache: CacheService | None = None

def get_job_manager() -> JobManager:
    global _job_manager
    if _job_manager is None:
        _job_manager = JobManager()
    return _job_manager

def get_pipeline_runner_dep(
    settings: Settings = Depends(get_settings),
    job_manager: JobManager = Depends(get_job_manager),
) -> PipelineRunner:
    global _pipeline_runner, _cache
    if _pipeline_runner is None:
        _cache = get_cache_service(settings)
        _pipeline_runner = PipelineRunner(settings=settings, cache=_cache, job_manager=job_manager)
    return _pipeline_runner

@router.post("/literature-review", status_code=202, response_model=CreateReviewResponse)
async def create_review(
    request: CreateReviewRequest,
    background_tasks: BackgroundTasks,
    settings: Settings = Depends(get_settings),
    job_manager: JobManager = Depends(get_job_manager),
    pipeline_runner: PipelineRunner = Depends(get_pipeline_runner_dep),
):
    active = await job_manager.get_active_job_count()
    if active >= settings.MAX_CONCURRENT_JOBS:
        return JSONResponse(status_code=503, headers={"Retry-After": "30"},
            content={"error": "Server at capacity", "retry_after": 30})

    job_id = await job_manager.create_job(request.topic, request.config)
    background_tasks.add_task(pipeline_runner.run, job_id=job_id, topic=request.topic, config=request.config)
    return CreateReviewResponse(job_id=job_id, estimated_seconds=120)

@router.get("/literature-review/{job_id}/status", response_model=JobStatusResponse)
async def get_status(job_id: str, job_manager: JobManager = Depends(get_job_manager)):
    status = await job_manager.get_status(job_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return status

@router.get("/literature-review/{job_id}/result", response_model=JobResultResponse)
async def get_result(job_id: str, job_manager: JobManager = Depends(get_job_manager)):
    result = await job_manager.get_result(job_id)
    if result is None:
        status = await job_manager.get_status(job_id)
        if status is None:
            raise HTTPException(status_code=404, detail="Job not found")
        raise HTTPException(status_code=404, detail="Result not ready yet")
    return result

@router.get("/literature-review/{job_id}/download")
async def download_pdf(job_id: str, job_manager: JobManager = Depends(get_job_manager)):
    result = await job_manager.get_result(job_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Result not found")
    if result.review.pdf_path is None:
        raise HTTPException(status_code=503, detail="PDF not available for this review")
    return FileResponse(result.review.pdf_path, media_type="application/pdf",
        filename=f"literature-review-{job_id[:8]}.pdf")

@router.post("/literature-review/{job_id}/cancel", status_code=200)
async def cancel_review(job_id: str, job_manager: JobManager = Depends(get_job_manager)):
    status = await job_manager.get_status(job_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Job not found")
    await job_manager.cancel_job(job_id)
    return {"status": "cancelled", "job_id": job_id}
