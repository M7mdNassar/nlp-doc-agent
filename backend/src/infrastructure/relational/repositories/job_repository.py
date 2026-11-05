from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.job import Job, JobStatus
from src.domain.ports.job_repository import JobRepository as IJobRepository
from src.domain.value_objects.document_id import DocumentId
from src.infrastructure.relational.models import JobModel


class JobRepository(IJobRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def save(self, job: Job) -> None:
        stmt = select(JobModel).where(JobModel.job_id == job.job_id)
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()

        if model:
            model.status = job.status.value
            model.error = job.error
        else:
            model = JobModel(
                job_id=job.job_id,
                document_id=str(job.document_id),
                status=job.status.value,
                error=job.error,
            )
            self.session.add(model)

        await self.session.commit()

    async def get(self, job_id: str) -> Job | None:
        stmt = select(JobModel).where(JobModel.job_id == job_id)
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()

        if not model:
            return None

        return Job(
            job_id=model.job_id,
            document_id=DocumentId(model.document_id),
            status=JobStatus(model.status),
            error=model.error,
            updated_at=model.updated_at,
        )
