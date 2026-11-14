from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.job import Job, JobStatus
from src.domain.ports.job_repository import JobRepository as IJobRepository
from src.domain.value_objects.document_id import DocumentId
from src.infrastructure.relational.models import IngestionClaimModel, JobModel


class JobRepository(IJobRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def claim(self, job: Job) -> bool:
        result = await self.session.execute(
            insert(IngestionClaimModel)
            .values(document_id=str(job.document_id), job_id=job.job_id)
            .on_conflict_do_nothing(index_elements=["document_id"])
            .returning(IngestionClaimModel.document_id)
        )
        if result.scalar_one_or_none() is None:
            await self.session.rollback()
            return False
        # The claim and queued job become visible in one transaction.
        self.session.add(
            JobModel(
                job_id=job.job_id,
                document_id=str(job.document_id),
                status=job.status.value,
                error=job.error,
            )
        )
        await self.session.commit()
        return True

    async def save(self, job: Job) -> None:
        stmt = select(JobModel).where(JobModel.job_id == job.job_id)
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()

        if model:
            model.status = job.status.value
            model.error = job.error
            model.updated_at = datetime.now(UTC)
        else:
            model = JobModel(
                job_id=job.job_id,
                document_id=str(job.document_id),
                status=job.status.value,
                error=job.error,
            )
            self.session.add(model)

        if job.status in {JobStatus.COMPLETED, JobStatus.FAILED}:
            await self.session.execute(
                delete(IngestionClaimModel).where(
                    IngestionClaimModel.document_id == str(job.document_id),
                    IngestionClaimModel.job_id == job.job_id,
                )
            )
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

    async def latest_for_document(self, document_id: str) -> Job | None:
        result = await self.session.execute(
            select(JobModel.job_id)
            .where(JobModel.document_id == document_id)
            .order_by(JobModel.updated_at.desc())
            .limit(1)
        )
        job_id = result.scalar_one_or_none()
        return await self.get(job_id) if job_id else None
