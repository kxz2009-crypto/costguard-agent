"""P0-04/05/06 FastAPI application factory (optional [split-server] extra).

The HTTP layer is a thin adapter: parse strict DTO -> call domain service
in one transaction scope -> map domain errors to the unified error
contract. No business rule lives here.

Error contract (P0 unified minimum):
    400 invalid input                     (client semantic error)
    404 not found / foreign tenant hidden (TenantViolation)
    409 conflict                          (device_uid collision, overlap,
                                           immutable-state conflicts)
    422 schema validation                 (pydantic, extra=forbid)
    500 unexpected                        (never exposes tracebacks)
"""

from __future__ import annotations

from fastapi import APIRouter, FastAPI, HTTPException, Request, Response

from ..db import connect as connect_db
from ..identity.device_uid import validate_device_uid
from ..schemas.dto import canonical_source_event_id  # re-export used by tests
from . import assignments as assignment_service
from . import members as member_service
from . import registration as device_service
from .assignments import AssignmentConflict
from .context import ServerContext, TenantViolation
from .schemas import (
    AssignmentCreateRequest, AssignmentResponse,
    DeviceRegisterRequest, DeviceResponse,
    MemberCreateRequest, MemberResponse, MemberUpdateRequest,
)

ERROR_DEVICE_UID_COLLISION = 409


class RegistrationConflict(Exception):
    """device_uid already belongs to a DIFFERENT organization."""


def create_app(db_path=None, context: ServerContext | None = None) -> FastAPI:
    """Build the Split API app against one resolved CostGuard home DB.

    `context` is the server-side authority used for every request in this
    process (single-org P0 server; real auth derives per-request contexts
    later WITHOUT changing the service signatures).
    """
    app = FastAPI(title="CostGuard Split API", version="0.1.0",
                  docs_url=None, redoc_url=None)   # public repo: minimal surface
    db = connect_db(path=db_path, check_same_thread=False)
    ctx = context
    router = APIRouter(prefix="/api/v1")

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    # ------------------------------------------------------------------
    # P0-04 device registration
    # ------------------------------------------------------------------
    @router.post("/devices/register", response_model=DeviceResponse,
                 status_code=201)
    def register_device(payload: DeviceRegisterRequest,
                        response: Response):
        try:
            device, created = device_service.register_device_api(
                db, context=ctx,
                device_uid=payload.device_uid,
                hostname_fingerprint=payload.hostname_fingerprint,
                username_fingerprint=payload.username_fingerprint,
                network_fingerprint=payload.network_fingerprint,
                os_name=payload.os, arch=payload.arch,
                collector_version=payload.collector_version)
        except RegistrationConflict:
            raise HTTPException(status_code=409, detail={
                "error": "device_uid_conflict",
                "message": "device_uid already registered to another "
                           "organization"})
        # spec: repeat registration is 200 (idempotent), first is 201
        if not created:
            response.status_code = 200
        return device

    @router.get("/devices/{device_id}", response_model=DeviceResponse)
    def get_device(device_id: str):
        try:
            return device_service.get_device_api(db, context=ctx,
                                                 device_id=device_id)
        except TenantViolation:
            raise HTTPException(status_code=404, detail="not found")

    # ------------------------------------------------------------------
    # P0-05 member CRUD
    # ------------------------------------------------------------------
    @router.post("/members", response_model=MemberResponse, status_code=201)
    def create_member(payload: MemberCreateRequest):
        return member_service.create_member_api(db, context=ctx,
                                                display_name=payload.display_name,
                                                email_optional=payload.email_optional)

    @router.get("/members", response_model=list[MemberResponse])
    def list_members():
        return member_service.list_members_api(db, context=ctx)

    @router.get("/members/{member_id}", response_model=MemberResponse)
    def get_member(member_id: str):
        try:
            return member_service.get_member_api(db, context=ctx,
                                                 member_id=member_id)
        except TenantViolation:
            raise HTTPException(status_code=404, detail="not found")

    @router.patch("/members/{member_id}", response_model=MemberResponse)
    def update_member(member_id: str, payload: MemberUpdateRequest):
        try:
            return member_service.update_member_api(
                db, context=ctx, member_id=member_id,
                display_name=payload.display_name,
                email_optional=payload.email_optional,
                status=payload.status)
        except TenantViolation:
            raise HTTPException(status_code=404, detail="not found")

    # ------------------------------------------------------------------
    # P0-06 manual assignment
    # ------------------------------------------------------------------
    @router.post("/devices/{device_id}/assignments",
                 response_model=AssignmentResponse, status_code=201)
    def create_assignment(device_id: str, payload: AssignmentCreateRequest):
        try:
            return assignment_service.create_assignment_api(
                db, context=ctx, device_id=device_id,
                member_id=payload.member_id,
                valid_from=payload.valid_from, reason=payload.reason)
        except TenantViolation:
            raise HTTPException(status_code=404, detail="not found")
        except AssignmentConflict:
            # Preserve the single domain exception type for the unified
            # top-level 409 handler below.
            raise

    app.include_router(router)

    # unified error shapes, never leak tracebacks
    from .registration import RegistrationConflict as _RegConflict

    @app.exception_handler(_RegConflict)
    async def _conflict(request, exc):
        return JSONResponse(status_code=409, content={
            "error": "device_uid_conflict",
            "message": "device_uid already registered to another "
                       "organization"})

    @app.exception_handler(AssignmentConflict)
    async def _assign_conflict(request, exc):
        return JSONResponse(status_code=409, content={
            "error": "assignment_conflict", "message": str(exc)})

    @app.exception_handler(Exception)
    async def _unhandled(request, exc):     # safety net: no tracebacks
        return JSONResponse({"error": "internal_error"}, status_code=500)

    return app


from fastapi.responses import JSONResponse  # noqa: E402  (kept near use)
