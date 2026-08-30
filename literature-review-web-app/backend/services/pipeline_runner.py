"""Pipeline runner service for the literature review application.

This module provides the :func:`run_pipeline` async function and the
:class:`PipelineRunner` class, which serve as the bridge between FastAPI's
``BackgroundTasks`` mechanism and the orchestrator pipeline.

:func:`run_pipeline` wraps the orchestrator call with structured error
handling — completing or failing the job in the :class:`JobManager`
depending on the outcome.

:class:`PipelineRunner` is a thin wrapper that holds injected dependencies
and exposes a single ``run`` method suitable for direct use with FastAPI's
``BackgroundTasks.add_task``.

Typical usage::

    runner = PipelineRunner(settings=settings, cache=cache, job_manager=job_manager)
    background_tasks.add_task(runner.run, job_id=job_id, topic=topic, config=config)
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from agents.orchestrator import run_pipeline as run_orchestrator_pipeline
from config.settings import Settings
from models.api import ReviewConfig
from models.job import Stage
from services.job_manager import JobManager

if TYPE_CHECKING:
    from services.cache_service import CacheService

logger = logging.getLogger(__name__)


async def run_pipeline(
    job_id: str,
    topic: str,
    config: ReviewConfig,
    settings: Settings,
    cache: "CacheService | None",
    job_manager: JobManager,
) -> None:
    """Execute the full literature review pipeline for a given job.

    Updates the job status at start and on completion via the provided
    :class:`~services.job_manager.JobManager`.  The orchestrator's
    :func:`~agents.orchestrator.run_pipeline` is called directly; all
    per-agent error handling and progress updates are managed by the
    orchestrator itself.

    On success the job is marked completed with the returned
    :class:`~models.paper.LiteratureReview`.  On a :class:`RuntimeError`
    (pipeline aborted by a critical agent failure) the job is failed with the
    exception message.  Any other unexpected exception is logged at ERROR
    level and the job is also failed with a descriptive message.

    Parameters
    ----------
    job_id:
        UUID string identifying the job in the :class:`JobManager`.
    topic:
        Research topic submitted by the user.
    config:
        :class:`~models.api.ReviewConfig` carrying pipeline options.
    settings:
        Application :class:`~config.settings.Settings` instance supplying
        API keys and service URLs.
    cache:
        Optional :class:`~services.cache_service.CacheService` for caching;
        pass ``None`` to disable caching.
    job_manager:
        :class:`~services.job_manager.JobManager` used to persist job state
        and broadcast progress to polling clients.
    """
    logger.info(
        "PipelineRunner: starting pipeline. job_id=%s topic=%r",
        job_id,
        topic,
    )

    # Transition the job from PENDING to the first running stage so polling
    # clients immediately see activity rather than sitting on "pending".
    await job_manager.update_status(
        job_id,
        Stage.TOPIC_UNDERSTOOD,
        0.0,
        "Pipeline starting…",
    )

    try:
        review = await run_orchestrator_pipeline(
            job_id=job_id,
            topic=topic,
            config=config,
            settings=settings,
            cache=cache,
            job_manager=job_manager,
        )
        await job_manager.complete_job(job_id, review)
        logger.info(
            "PipelineRunner: pipeline completed successfully. job_id=%s", job_id
        )

    except RuntimeError as exc:
        # Critical agent failure — the orchestrator intentionally aborted the
        # pipeline and raised RuntimeError with a descriptive message.
        logger.warning(
            "PipelineRunner: pipeline aborted (RuntimeError). job_id=%s error=%s",
            job_id,
            exc,
        )
        await job_manager.fail_job(job_id, str(exc))

    except Exception as exc:  # noqa: BLE001
        # Unexpected exception — log at ERROR so it surfaces in observability
        # tooling, then record the failure in the job store.
        logger.error(
            "PipelineRunner: unexpected error during pipeline. job_id=%s error=%s",
            job_id,
            exc,
            exc_info=True,
        )
        await job_manager.fail_job(job_id, f"Unexpected error: {exc}")


class PipelineRunner:
    """Dependency-injected wrapper around :func:`run_pipeline`.

    Holds the settings, optional cache, and job manager as instance
    attributes so that a single :meth:`run` method signature is compatible
    with FastAPI's ``BackgroundTasks.add_task`` interface.

    Parameters
    ----------
    settings:
        Application :class:`~config.settings.Settings` instance.
    cache:
        Optional :class:`~services.cache_service.CacheService`; ``None``
        disables caching.
    job_manager:
        :class:`~services.job_manager.JobManager` that owns the job store.
    """

    def __init__(
        self,
        settings: Settings,
        cache: "CacheService | None",
        job_manager: JobManager,
    ) -> None:
        self._settings = settings
        self._cache = cache
        self._job_manager = job_manager

    async def run(
        self,
        job_id: str,
        topic: str,
        config: ReviewConfig,
    ) -> None:
        """Run the pipeline for a single review job.

        This is the method intended for use with FastAPI's
        ``BackgroundTasks.add_task``::

            background_tasks.add_task(runner.run, job_id=job_id, topic=topic, config=config)

        Parameters
        ----------
        job_id:
            UUID string identifying the job.
        topic:
            Research topic submitted by the user.
        config:
            :class:`~models.api.ReviewConfig` carrying pipeline options.
        """
        await run_pipeline(
            job_id=job_id,
            topic=topic,
            config=config,
            settings=self._settings,
            cache=self._cache,
            job_manager=self._job_manager,
        )
