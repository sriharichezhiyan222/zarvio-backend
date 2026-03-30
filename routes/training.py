from fastapi import APIRouter, Body, HTTPException, status
from typing import Dict, Any
from services.training_service import get_training_config, save_training_config

router = APIRouter(prefix="/api/training", tags=["training"])

@router.get("")
async def get_training():
    """Retrieve current AI training configuration."""
    return get_training_config()

@router.post("")
async def update_training(payload: Dict[str, Any] = Body(...)):
    """Update the AI training configuration."""
    success = save_training_config(payload)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save AI training configuration."
        )
    return {"status": "ok", "message": "AI Training updated successfully."}
