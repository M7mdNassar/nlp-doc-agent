"""
Initialization script for Qdrant.
This will run once the backend is built and Qdrant is up.
It creates the collections and payload indexes required for hybrid search.
"""
# Note: This is a placeholder. The actual implementation will use qdrant-client
# and be executed via a Makefile command or a FastAPI startup event.

import asyncio

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    PayloadSchemaType,
    SparseVectorParams,
    VectorParams,
)


async def init_db():
    client = AsyncQdrantClient(url="http://localhost:6333")

    # 1. Create the documents collection (Dense + Sparse)
    # We use bge-small (384 dims)
    await client.recreate_collection(
        collection_name="documents",
        vectors_config={"dense": VectorParams(size=384, distance=Distance.COSINE)},
        sparse_vectors_config={"sparse": SparseVectorParams()},
    )

    # 2. Create payload indexes for metadata filtering
    await client.create_payload_index(
        collection_name="documents",
        field_name="doc_id",
        field_schema=PayloadSchemaType.KEYWORD,
    )
    await client.create_payload_index(
        collection_name="documents",
        field_name="page",
        field_schema=PayloadSchemaType.INTEGER,
    )
    await client.create_payload_index(
        collection_name="documents",
        field_name="access_tags",
        field_schema=PayloadSchemaType.KEYWORD,
    )

    print("Qdrant collections and indexes initialized successfully.")


if __name__ == "__main__":
    asyncio.run(init_db())
