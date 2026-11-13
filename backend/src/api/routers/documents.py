from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile

from src.api.dependencies.providers import get_delete_doc_uc, get_list_docs_uc, get_upload_doc_uc
from src.application.use_cases.delete_document import DeleteDocumentUseCase
from src.application.use_cases.list_documents import ListDocumentsUseCase
from src.application.use_cases.upload_document import UploadDocumentUseCase
from src.core.errors import ValidationError
from src.domain.value_objects.document_id import DocumentId

router = APIRouter()


@router.post("")
async def upload_document(
    file: Annotated[UploadFile, File()],
    uc: Annotated[UploadDocumentUseCase, Depends(get_upload_doc_uc)],
) -> dict[str, str]:
    filename = file.filename
    if not filename:
        raise ValidationError("Uploaded file must have a filename.")
    content = await file.read()
    file_type = filename.split(".")[-1] if "." in filename else "txt"
    doc, job = await uc.execute(filename, file_type, content)
    return {"document_id": str(doc.id), "job_id": job.job_id, "status": job.status.value}


@router.post("/{doc_id}/reindex")
async def reindex_document(
    doc_id: str, uc: Annotated[UploadDocumentUseCase, Depends(get_upload_doc_uc)]
) -> dict[str, str]:
    doc, job = await uc.reindex(DocumentId(doc_id))
    return {"document_id": str(doc.id), "job_id": job.job_id, "status": job.status.value}


@router.get("")
async def list_documents(
    uc: Annotated[ListDocumentsUseCase, Depends(get_list_docs_uc)],
) -> dict[str, list[dict[str, str]]]:
    docs = await uc.execute()
    return {"items": [{"id": str(d.id), "name": d.name, "status": d.status.value} for d in docs]}


@router.delete("/{doc_id}")
async def delete_document(
    doc_id: str, uc: Annotated[DeleteDocumentUseCase, Depends(get_delete_doc_uc)]
) -> dict[str, str]:
    await uc.execute(DocumentId(doc_id))
    return {"status": "deleted"}
