from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import List, Optional
import datetime

router = APIRouter()

class IncidentSchema(BaseModel):
    id: str
    title: str
    severity: str = "HIGH"
    status: str = "INVESTIGATING"
    service: str = "Core Platform"
    owner: str = "On-call Engineer"
    created_at: str = Field(default_factory=lambda: datetime.datetime.now().isoformat())

_INCIDENTS_DB = [
    {"id": "INC-1049", "title": "Payment Gateway Webhook Timeout", "severity": "CRITICAL", "status": "INVESTIGATING", "service": "Billing Service", "owner": "Alex Rivera"},
    {"id": "INC-1048", "title": "High CPU on Elasticsearch Cluster 02", "severity": "HIGH", "status": "IDENTIFIED", "service": "Search Cluster", "owner": "Devon Lee"},
    {"id": "INC-1047", "title": "Redis Cache Memory Pressure in EU-West", "severity": "MEDIUM", "status": "MONITORING", "service": "Cache Layer", "owner": "Sarah Connor"},
]

@router.get("/", response_model=List[IncidentSchema])
async def list_incidents(severity: Optional[str] = None):
    """List all registered incidents with optional severity filter."""
    if severity:
        return [i for i in _INCIDENTS_DB if i.get("severity") == severity.upper()]
    return _INCIDENTS_DB

@router.post("/", response_model=IncidentSchema)
async def create_incident(inc: IncidentSchema):
    """Declare a new incident in the platform."""
    _INCIDENTS_DB.append(inc.dict())
    return inc

@router.get("/{incident_id}", response_model=IncidentSchema)
async def get_incident(incident_id: str):
    for i in _INCIDENTS_DB:
        if i["id"].lower() == incident_id.lower():
            return i
    raise HTTPException(status_code=404, detail="Incident not found")
