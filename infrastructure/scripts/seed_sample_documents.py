"""
Script to seed sample documents.
This will act as a bridge to test the ingestion pipeline once it's built.
"""

import asyncio


async def seed():
    print("Starting sample document seeding...")
    # 1. Look for files in a /samples directory
    # 2. Call the ingestion pipeline function
    # 3. Print results
    print(
        "Ingestion pipeline not yet implemented. This script will be wired up in the backend phase."
    )


if __name__ == "__main__":
    asyncio.run(seed())
