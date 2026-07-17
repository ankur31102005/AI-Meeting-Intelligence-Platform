"""
API v1 aggregate router.

Every endpoint module registers here exactly once; `app.main` mounts this
single router under `settings.API_V1_PREFIX`. Adding a new resource in later
modules = one import + one include_router line.
"""

from fastapi import APIRouter

from app.api.v1.endpoints import auth, chat, health, meetings

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(meetings.router)
api_router.include_router(chat.router)
