"""Records HTTP surface (P2.5).

HTTP only — parse, guard, delegate to `service`. Consent-denied and
not-your-record reads surface from the service as 404, never 403.
"""

from datetime import date
from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.storage import StorageProvider
from app.core.authz import Permission
from app.core.pagination import Page
from app.db.session import get_session
from app.modules.auth.dependencies import AuthContext, current_user, requires
from app.modules.records import service
from app.modules.records.dependencies import get_storage_provider
from app.modules.records.models import EntryType
from app.modules.records.schemas import (
    Document,
    EntryCreate,
    EntryDetail,
    EntryProvider,
    EntrySummary,
)

router = APIRouter(prefix="/api/v1", tags=["records"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
CurrentUser = Annotated[AuthContext, Depends(current_user)]
StorageDep = Annotated[StorageProvider, Depends(get_storage_provider)]


@router.get(
    "/patients/{patient_id}/entries",
    dependencies=[requires(Permission.RECORDS_READ)],
)
async def list_patient_entries(
    patient_id: UUID,
    ctx: CurrentUser,
    session: SessionDep,
    entry_type: Annotated[EntryType | None, Query(alias="entryType")] = None,
    from_date: Annotated[date | None, Query(alias="fromDate")] = None,
    to_date: Annotated[date | None, Query(alias="toDate")] = None,
    provider_id: Annotated[UUID | None, Query(alias="providerId")] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    cursor: str | None = None,
    limit: int = 50,
) -> Page[EntrySummary]:
    return await service.list_timeline(
        session,
        ctx.actor,
        patient_id,
        entry_type=entry_type,
        from_date=from_date,
        to_date=to_date,
        provider_id=provider_id,
        q=q,
        cursor=cursor,
        limit=limit,
    )


@router.get(
    "/patients/{patient_id}/entry-providers", dependencies=[requires(Permission.RECORDS_READ)]
)
async def timeline_providers(
    patient_id: UUID, ctx: CurrentUser, session: SessionDep
) -> list[EntryProvider]:
    return await service.timeline_providers(session, ctx.actor, patient_id)


@router.get(
    "/entries/{entry_id}",
    dependencies=[requires(Permission.RECORDS_READ)],
)
async def get_entry_detail(entry_id: UUID, ctx: CurrentUser, session: SessionDep) -> EntryDetail:
    return await service.get_entry(session, ctx.actor, entry_id)


@router.post(
    "/patients/{patient_id}/entries",
    status_code=status.HTTP_201_CREATED,
    dependencies=[requires(Permission.RECORDS_WRITE)],
)
async def file_entry(
    patient_id: UUID,
    payload: EntryCreate,
    ctx: CurrentUser,
    session: SessionDep,
) -> EntryDetail:
    return await service.insert_entry(session, ctx.actor, patient_id, payload)


@router.post(
    "/patients/{patient_id}/entries/{entry_id}/corrections",
    status_code=status.HTTP_201_CREATED,
    dependencies=[requires(Permission.RECORDS_WRITE)],
)
async def correct_entry(
    patient_id: UUID,
    entry_id: UUID,
    payload: EntryCreate,
    ctx: CurrentUser,
    session: SessionDep,
) -> EntryDetail:
    return await service.supersede_entry(session, ctx.actor, patient_id, entry_id, payload)


@router.post(
    "/patients/{patient_id}/entries/{entry_id}/documents",
    status_code=status.HTTP_201_CREATED,
    dependencies=[requires(Permission.RECORDS_WRITE)],
)
async def upload_document(
    patient_id: UUID,
    entry_id: UUID,
    ctx: CurrentUser,
    session: SessionDep,
    storage: StorageDep,
    file: Annotated[UploadFile, File()],
) -> Document:
    data = await file.read(25 * 1024 * 1024 + 1)
    await file.close()
    return await service.add_document(
        session,
        ctx.actor,
        patient_id,
        entry_id,
        storage=storage,
        data=data,
        filename=file.filename or "upload",
    )


@router.get(
    "/documents/{document_id}",
    dependencies=[requires(Permission.RECORDS_READ)],
)
async def serve_document(
    document_id: UUID,
    ctx: CurrentUser,
    session: SessionDep,
    storage: StorageDep,
) -> Response:
    doc, data = await service.get_document(session, ctx.actor, document_id, storage=storage)
    # RFC 5987: the filename can be non-Latin-1 (four Indian locales) and is
    # attacker-supplied — an ASCII `filename="..."` param would crash on
    # header encoding or allow parameter injection.
    disposition = f"attachment; filename*=UTF-8''{quote(doc.filename)}"
    return Response(
        content=data,
        media_type=doc.mime_type,
        headers={"Content-Disposition": disposition},
    )
