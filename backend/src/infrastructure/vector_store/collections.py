import structlog
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, PayloadSchemaType, SparseVectorParams, VectorParams

from .schema import (
    COLLECTION_NAME,
    DENSE_VECTOR_NAME,
    PAYLOAD_ACCESS_TAGS,
    PAYLOAD_DOC_ID,
    PAYLOAD_PAGE,
    SPARSE_VECTOR_NAME,
)

logger = structlog.get_logger(__name__)


async def init_qdrant_collections(client: AsyncQdrantClient) -> None:
    """Creates the collection and indexes if they don't exist."""
    collections = await client.get_collections()
    if any(c.name == COLLECTION_NAME for c in collections.collections):
        logger.info(f"Collection {COLLECTION_NAME} already exists.")
    else:
        logger.info(f"Creating collection {COLLECTION_NAME}...")
        await client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config={DENSE_VECTOR_NAME: VectorParams(size=384, distance=Distance.COSINE)},
            sparse_vectors_config={SPARSE_VECTOR_NAME: SparseVectorParams()},
        )

    # Create payload indexes for fast filtering
    await client.create_payload_index(COLLECTION_NAME, PAYLOAD_DOC_ID, PayloadSchemaType.KEYWORD)
    await client.create_payload_index(COLLECTION_NAME, PAYLOAD_PAGE, PayloadSchemaType.INTEGER)
    await client.create_payload_index(
        COLLECTION_NAME, PAYLOAD_ACCESS_TAGS, PayloadSchemaType.KEYWORD
    )
    for key in ("name_key", "author_key", "file_type", "date", "chapter", "section_key"):
        await client.create_payload_index(COLLECTION_NAME, key, PayloadSchemaType.KEYWORD)

    logger.info(f"Collection {COLLECTION_NAME} and indexes created.")
