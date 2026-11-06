from typing import Annotated

from fastapi import APIRouter, Depends

from src.api.dependencies.providers import get_job_status_uc
from src.application.use_cases.get_job_status import GetJobStatusUseCase
from src.core.errors import NotFoundError

router = APIRouter()


@router.get("/{job_id}")
async def get_job_status(
    job_id: str,
    uc: Annotated[GetJobStatusUseCase, Depends(get_job_status_uc)],
) -> dict[str, str | None]:
    job = await uc.execute(job_id)
    if job is None:
        raise NotFoundError("Job", job_id)
    return {
        "job_id": job.job_id,
        "document_id": str(job.document_id),
        "status": job.status.value,
        "error": job.error,
        "updated_at": job.updated_at.isoformat(),
    }
