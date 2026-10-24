#!/usr/bin/env python3
from fastapi import APIRouter, Response, Query, Depends

from terrascope.db.disease_outbreaks_adapter import DiseaseOutbreaksAdapter

router = APIRouter(prefix="/api", tags=["Hazards"])


def get_disease_outbreaks_adapter() -> DiseaseOutbreaksAdapter:
    return DiseaseOutbreaksAdapter()


@router.get("/disease_outbreaks/geojson")
async def get_disease_outbreaks_geojson(
    active_days: float = Query(45, ge=1, le=365),
    adapter: DiseaseOutbreaksAdapter = Depends(get_disease_outbreaks_adapter),
):
    return Response(
        content=adapter.get_current_as_geojson(active_days),
        media_type="application/json",
    )
