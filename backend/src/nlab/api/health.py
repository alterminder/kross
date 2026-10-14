from fastapi import APIRouter
from sqlalchemy import text

from nlab.api.deps import Db

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health(db: Db) -> dict[str, bool]:
    await db.execute(text("SELECT 1"))
    return {"ok": True}
