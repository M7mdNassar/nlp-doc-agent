from src.domain.entities.job import Job
from src.domain.ports.job_repository import JobRepository


class GetJobStatusUseCase:
    def __init__(self, job_repo: JobRepository):
        self.job_repo = job_repo

    async def execute(self, job_id: str) -> Job | None:
        return await self.job_repo.get(job_id)
