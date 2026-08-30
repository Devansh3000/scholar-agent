from __future__ import annotations
from fastapi import APIRouter, Depends
from config.settings import Settings, get_settings

router = APIRouter()

@router.get("/health")
async def health_check(settings: Settings = Depends(get_settings)):
    return {"status": "ok", "version": settings.APP_VERSION}
