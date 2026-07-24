from fastapi import APIRouter

router = APIRouter(tags=["health"])

@router.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "AI Agents API",
        "mode": "async-first"
    }