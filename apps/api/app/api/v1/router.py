from fastapi import APIRouter

from app.api.v1.routers import assistant, auth, evals, health, incidents, knowledge, prompts

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(incidents.router)
api_router.include_router(assistant.router)
api_router.include_router(knowledge.router)
api_router.include_router(prompts.router)
api_router.include_router(evals.router)
