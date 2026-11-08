"""Upload local sample files through the actual backend ingestion API."""

import argparse
import asyncio
import json
from pathlib import Path

import httpx


async def seed(files: list[Path], base_url: str) -> None:
    async with httpx.AsyncClient(base_url=base_url, timeout=60) as client:
        for path in files:
            with path.open("rb") as upload:
                response = await client.post("/documents", files={"file": (path.name, upload)})
            response.raise_for_status()
            print(json.dumps({"file": path.name, **response.json()}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--url", default="http://localhost:8000")
    arguments = parser.parse_args()
    asyncio.run(seed(arguments.files, arguments.url))
