from typing import Protocol

from ..entities.job import Job


class JobRepository(Protocol):
    async def save(self, job: Job) -> None: ...

    async def get(self, job_id: str) -> Job | None: ...
    async def latest_for_document(self, document_id: str) -> Job | None: ...
