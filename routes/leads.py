from fastapi import APIRouter, Body, File, HTTPException, UploadFile, status
from models.lead_model import Lead
from services.csv_upload_service import upload_leads_from_bytes, upload_leads_from_csv
from services.lead_service import create_lead, list_leads

router = APIRouter(prefix="/leads", tags=["leads"])


@router.get("")
async def list_leads_endpoint():
    """Return all leads from the Supabase "leads" table."""
    try:
        leads = await list_leads()
        return leads
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_lead_endpoint(lead: Lead):
    """Create a new lead and store it in the Supabase "leads" table."""
    try:
        lead_data = await create_lead(lead.dict(exclude_none=True))
        lead_id = None
        if isinstance(lead_data, dict):
            lead_id = lead_data.get("id") or lead_data.get("lead_id")
        return {"status": "ok", "id": lead_id, "lead": lead_data}
    except RuntimeError as exc:
        # Missing Supabase config or other explicit runtime issues.
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/upload-csv")
async def upload_leads_csv_endpoint(file: UploadFile = File(...)):
    """Upload a CSV of leads and store scored prospects."""
    try:
        result = await upload_leads_from_csv(file)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.post("/upload-csv/raw")
async def upload_leads_csv_raw_endpoint(raw_body: bytes = Body(...)):
    """Upload a raw CSV body (application/octet-stream) and store scored prospects."""
    try:
        result = await upload_leads_from_bytes(raw_body)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
