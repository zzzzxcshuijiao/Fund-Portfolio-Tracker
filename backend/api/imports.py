"""Import API endpoints."""

from fastapi import APIRouter, Depends, UploadFile, File
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.schemas.import_result import ImportResult, ImportHistoryItem
from backend.schemas.holding_change import HoldingChangeResponse

router = APIRouter()


@router.post("/upload", response_model=ImportResult)
async def upload_excel(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Upload and import fund holdings Excel file."""
    from backend.services.import_service import ImportService
    return await ImportService(db).import_excel(file)


@router.get("/history", response_model=list[ImportHistoryItem])
def get_import_history(db: Session = Depends(get_db)):
    """Get import history records."""
    from backend.services.import_service import ImportService
    return ImportService(db).get_import_history()


@router.get("/{import_id}/changes", response_model=list[HoldingChangeResponse])
def get_import_changes(import_id: int, db: Session = Depends(get_db)):
    """Get holding changes for a specific import."""
    from backend.services.import_service import ImportService
    return ImportService(db).get_import_changes(import_id)
