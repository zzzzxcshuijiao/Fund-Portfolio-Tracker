"""NAV (Net Asset Value) API endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.database import get_db

router = APIRouter()


@router.post("/refresh")
async def refresh_nav(db: Session = Depends(get_db)):
    """Manually trigger NAV update for all held funds."""
    from backend.services.nav_service import NavService
    result = await NavService(db).refresh_all_nav()
    return result


@router.get("/status")
def get_nav_status(db: Session = Depends(get_db)):
    """Get latest NAV update status."""
    from backend.services.nav_service import NavService
    return NavService(db).get_nav_status()
