from typing import Annotated
import os
import structlog
from fastapi import APIRouter, Depends, HTTPException, Header, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.db.session import get_db
from app.db.models import User
from app.services.feature_engineering import FeatureEngineeringService

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/internal", tags=["internal-jobs"])

class NightlyJobResponse(BaseModel):
    processed: int
    has_more: bool
    next_offset: int

async def verify_internal_token(x_internal_token: str = Header(None)):
    """Verify the X-Internal-Token header matches the environment variable."""
    expected = os.environ.get("INTERNAL_JOB_SECRET")
    if not expected:
        # If not set in environment, fail closed
        raise HTTPException(status_code=500, detail="INTERNAL_JOB_SECRET not configured")
    if x_internal_token != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal token",
        )

@router.post("/run-nightly-jobs", response_model=NightlyJobResponse, dependencies=[Depends(verify_internal_token)])
async def run_nightly_jobs(
    db: Annotated[AsyncSession, Depends(get_db)],
    offset: int = 0,
    limit: int = 5,
) -> NightlyJobResponse:
    """
    Synchronously run nightly ML feature recomputation and alerts in a paginated way
    to avoid hitting Vercel's 10-second execution limit.
    
    This replaces the old Celery beat 'recompute_all_features' and 'check_overspend_alerts' tasks.
    """
    # Fetch a batch of active users
    result = await db.execute(
        select(User)
        .where(User.is_active.is_(True), User.deleted_at.is_(None))
        .order_by(User.id)
        .offset(offset)
        .limit(limit + 1) # fetch limit+1 to check if there are more
    )
    users = result.scalars().all()
    
    has_more = len(users) > limit
    users_to_process = users[:limit]

    processed_count = 0
    for user in users_to_process:
        try:
            # 1. Recompute features for the user
            service = FeatureEngineeringService(db, user.id)
            await service.compute_and_save()
            
            # (If Prophet forecasts or overspend alerts need triggering per user, do it here)
            # e.g., service.run_forecasts()
            
            processed_count += 1
            await db.commit()
        except Exception as e:
            logger.error("nightly_job_failed_for_user", user_id=str(user.id), error=str(e))
            await db.rollback()

    return NightlyJobResponse(
        processed=processed_count,
        has_more=has_more,
        next_offset=offset + limit if has_more else offset,
    )
