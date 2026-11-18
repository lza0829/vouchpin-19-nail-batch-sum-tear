from __future__ import annotations
from typing import Any
from fastapi import APIRouter
from app.services import settings_service as svc

router = APIRouter(tags=["settings"])


@router.get("/settings/day")
def get_day():
    return svc.get_day()


@router.put("/settings/day")
def put_day(body: dict[str, Any]):
    return svc.set_day(body)


@router.get("/settings/strategy")
def get_strategy():
    return svc.get_strategy()


@router.put("/settings/strategy")
def put_strategy(body: dict[str, Any]):
    return svc.set_strategy(body)
