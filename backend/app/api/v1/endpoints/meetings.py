"""
Meeting endpoints: upload, list (paginated), detail, update, delete, download.

Thin adapters over MeetingService. The upload endpoint accepts multipart
form-data; FastAPI's UploadFile spools large bodies to a temp file, so the
handler holds a file-like object, never the whole payload in memory.
"""

import uuid
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse

from app.core.dependencies import CurrentUser, DbSession, get_client_ip
from app.core.rate_limit import limiter
from app.schemas.common import APIResponse
from app.schemas.intelligence import (
    ActionItemResponse,
    ActionItemUpdateRequest,
    InsightResponse,
    IntelligenceResponse,
    SummaryResponse,
)
from app.schemas.meeting import (
    MeetingDetailResponse,
    MeetingDownloadResponse,
    MeetingResponse,
    MeetingUpdateRequest,
)
from app.schemas.speaker import SpeakerRenameRequest, SpeakerResponse
from app.schemas.transcript import (
    ProcessingStatusResponse,
    TranscriptResponse,
    TranscriptSegmentResponse,
)
from app.services.meeting_service import MeetingService
from app.services.pipeline_dispatcher import (
    PipelineDispatcher,
    get_pipeline_dispatcher,
)
from app.storage import StorageProvider, get_storage_provider
from app.storage.local import LocalStorage

router = APIRouter(prefix="/meetings", tags=["Meetings"])


def get_meeting_service(
    db: DbSession,
    storage: Annotated[StorageProvider, Depends(get_storage_provider)],
) -> MeetingService:
    return MeetingService(db, storage)


MeetingSvc = Annotated[MeetingService, Depends(get_meeting_service)]
Dispatcher = Annotated[PipelineDispatcher, Depends(get_pipeline_dispatcher)]


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Upload a meeting recording (mp3/wav/mp4)",
)
@limiter.limit("20/minute")
def upload_meeting(
    request: Request,
    response: Response,
    svc: MeetingSvc,
    dispatcher: Dispatcher,
    user: CurrentUser,
    file: Annotated[UploadFile, File(description="Audio/video file")],
    title: Annotated[str | None, Form()] = None,
) -> APIResponse[MeetingDetailResponse]:
    meeting = svc.create_from_upload(
        organization_id=user.organization_id,
        owner_id=user.id,
        filename=file.filename or "upload",
        fileobj=file.file,  # sync SpooledTemporaryFile — matches sync storage
        title=title,
        ip_address=get_client_ip(request),
    )
    # Kick off background processing only AFTER the upload committed — if the
    # DB write had failed, there'd be nothing for the worker to process.
    dispatcher.enqueue_processing(meeting.id)

    detail = svc.get_detail(meeting_id=meeting.id, organization_id=user.organization_id)
    return APIResponse(data=MeetingDetailResponse.model_validate(detail))


@router.get("", summary="List meetings (paginated, newest first)")
def list_meetings(
    svc: MeetingSvc,
    user: CurrentUser,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    search: Annotated[str | None, Query(max_length=200)] = None,
) -> APIResponse[list[MeetingResponse]]:
    items, meta = svc.list_meetings(
        organization_id=user.organization_id,
        page=page,
        page_size=page_size,
        search=search,
    )
    return APIResponse(
        data=[MeetingResponse.model_validate(m) for m in items], meta=meta
    )


@router.get("/{meeting_id}", summary="Meeting detail with files")
def get_meeting(
    meeting_id: uuid.UUID, svc: MeetingSvc, user: CurrentUser
) -> APIResponse[MeetingDetailResponse]:
    meeting = svc.get_detail(meeting_id=meeting_id, organization_id=user.organization_id)
    return APIResponse(data=MeetingDetailResponse.model_validate(meeting))


@router.patch("/{meeting_id}", summary="Update meeting metadata")
def update_meeting(
    meeting_id: uuid.UUID,
    body: MeetingUpdateRequest,
    svc: MeetingSvc,
    user: CurrentUser,
) -> APIResponse[MeetingResponse]:
    meeting = svc.update(
        meeting_id=meeting_id,
        organization_id=user.organization_id,
        title=body.title,
        description=body.description,
        tags=body.tags,
    )
    return APIResponse(data=MeetingResponse.model_validate(meeting))


@router.delete("/{meeting_id}", summary="Soft-delete a meeting")
def delete_meeting(
    meeting_id: uuid.UUID, request: Request, svc: MeetingSvc, user: CurrentUser
) -> APIResponse[dict]:
    svc.delete(
        meeting_id=meeting_id,
        organization_id=user.organization_id,
        user_id=user.id,
        ip_address=get_client_ip(request),
    )
    return APIResponse(data={"message": "Meeting deleted"})


@router.get("/{meeting_id}/status", summary="Poll processing status")
def get_status(
    meeting_id: uuid.UUID, svc: MeetingSvc, user: CurrentUser
) -> APIResponse[ProcessingStatusResponse]:
    """Lightweight endpoint the frontend polls while the pipeline runs."""
    meeting = svc.get_detail(meeting_id=meeting_id, organization_id=user.organization_id)
    return APIResponse(
        data=ProcessingStatusResponse(
            meeting_id=meeting.id,
            status=meeting.status,
            error_message=meeting.error_message,
            duration_seconds=meeting.duration_seconds,
            updated_at=meeting.updated_at,
        )
    )


@router.get("/{meeting_id}/transcript", summary="Get the transcript segments")
def get_transcript(
    meeting_id: uuid.UUID, svc: MeetingSvc, user: CurrentUser
) -> APIResponse[TranscriptResponse]:
    meeting, segments = svc.get_transcript(
        meeting_id=meeting_id, organization_id=user.organization_id
    )
    return APIResponse(
        data=TranscriptResponse(
            meeting_id=meeting.id,
            status=meeting.status,
            duration_seconds=meeting.duration_seconds,
            segment_count=len(segments),
            segments=[TranscriptSegmentResponse.from_segment(s) for s in segments],
        )
    )


@router.get("/{meeting_id}/speakers", summary="List speakers in a meeting")
def list_speakers(
    meeting_id: uuid.UUID, svc: MeetingSvc, user: CurrentUser
) -> APIResponse[list[SpeakerResponse]]:
    speakers = svc.list_speakers(
        meeting_id=meeting_id, organization_id=user.organization_id
    )
    return APIResponse(data=[SpeakerResponse.model_validate(s) for s in speakers])


@router.patch(
    "/{meeting_id}/speakers/{speaker_id}", summary="Rename a speaker"
)
def rename_speaker(
    meeting_id: uuid.UUID,
    speaker_id: uuid.UUID,
    body: SpeakerRenameRequest,
    svc: MeetingSvc,
    user: CurrentUser,
) -> APIResponse[SpeakerResponse]:
    speaker = svc.rename_speaker(
        meeting_id=meeting_id,
        speaker_id=speaker_id,
        organization_id=user.organization_id,
        display_name=body.display_name,
    )
    return APIResponse(data=SpeakerResponse.model_validate(speaker))


@router.post("/{meeting_id}/reprocess", summary="Re-run the pipeline")
def reprocess_meeting(
    meeting_id: uuid.UUID,
    request: Request,
    svc: MeetingSvc,
    dispatcher: Dispatcher,
    user: CurrentUser,
) -> APIResponse[dict]:
    meeting = svc.request_reprocess(
        meeting_id=meeting_id,
        organization_id=user.organization_id,
        user_id=user.id,
        ip_address=get_client_ip(request),
    )
    dispatcher.enqueue_processing(meeting.id)
    return APIResponse(data={"message": "Reprocessing started", "status": meeting.status})


@router.get("/{meeting_id}/intelligence", summary="Summaries, insights & action items")
def get_intelligence(
    meeting_id: uuid.UUID, svc: MeetingSvc, user: CurrentUser
) -> APIResponse[IntelligenceResponse]:
    meeting, summaries, insights, action_items = svc.get_intelligence(
        meeting_id=meeting_id, organization_id=user.organization_id
    )
    return APIResponse(
        data=IntelligenceResponse(
            meeting_id=meeting.id,
            summaries=[SummaryResponse.model_validate(s) for s in summaries],
            insights=[InsightResponse.model_validate(i) for i in insights],
            action_items=[ActionItemResponse.model_validate(a) for a in action_items],
        )
    )


@router.patch(
    "/{meeting_id}/action-items/{item_id}", summary="Update an action item"
)
def update_action_item(
    meeting_id: uuid.UUID,
    item_id: uuid.UUID,
    body: ActionItemUpdateRequest,
    svc: MeetingSvc,
    user: CurrentUser,
) -> APIResponse[ActionItemResponse]:
    item = svc.update_action_item(
        meeting_id=meeting_id,
        item_id=item_id,
        organization_id=user.organization_id,
        status=body.status,
        assignee_user_id=body.assignee_user_id,
        priority=body.priority,
        description=body.description,
    )
    return APIResponse(data=ActionItemResponse.model_validate(item))


@router.get("/{meeting_id}/download", summary="Get a time-limited download URL")
def get_download_url(
    meeting_id: uuid.UUID, svc: MeetingSvc, user: CurrentUser
) -> APIResponse[MeetingDownloadResponse]:
    from app.core.config import get_settings

    url = svc.get_download_url(meeting_id=meeting_id, organization_id=user.organization_id)
    return APIResponse(
        data=MeetingDownloadResponse(
            download_url=url,
            expires_in_seconds=get_settings().PRESIGNED_URL_EXPIRE_SECONDS,
        )
    )


# ---------------------------------------------------------------------------
# Local-storage download route (S3/MinIO serve presigned URLs directly, so
# this is only wired for STORAGE_PROVIDER=local). The path is what
# LocalStorage.presigned_url() points at.
# ---------------------------------------------------------------------------
@router.get(
    "/files/{storage_path:path}",
    summary="Stream a file (local storage backend only)",
    include_in_schema=False,
)
def download_local_file(
    storage_path: str,
    user: CurrentUser,
    storage: Annotated[StorageProvider, Depends(get_storage_provider)],
) -> StreamingResponse:
    # This route only makes sense for the local backend; refuse otherwise.
    if not isinstance(storage, LocalStorage):
        from app.core.exceptions import NotFoundError

        raise NotFoundError("Direct download not available for this storage backend")
    if not storage.exists(storage_path):
        from app.core.exceptions import NotFoundError

        raise NotFoundError("File not found")
    return StreamingResponse(
        storage.download_stream(storage_path), media_type="application/octet-stream"
    )
