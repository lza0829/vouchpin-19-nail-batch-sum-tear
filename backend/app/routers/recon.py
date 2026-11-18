from __future__ import annotations
from fastapi import APIRouter
from app.services import recon_service as svc

router = APIRouter(tags=["recon"])


@router.get("/batches/{batch_id}/recon")
def recon_detail(batch_id: int):
    return svc.detail(batch_id)


@router.post("/batches/{batch_id}/recon")
def recon_run(batch_id: int):
    return svc.run(batch_id)


@router.post("/batches/{batch_id}/override")
def recon_override(batch_id: int):
    return svc.override_header(batch_id)


@router.post("/batches/{batch_id}/unseal")
def recon_unseal(batch_id: int):
    return svc.unseal(batch_id)
