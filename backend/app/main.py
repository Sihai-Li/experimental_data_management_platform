from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from app.db import get_engine

app = FastAPI(title="Lab Data Platform", version="0.2.0")


@app.get("/api/health/live")
def live():
    return {"status": "ok", "service": "lab-platform", "phase": "P02"}


@app.get("/api/health/ready")
def ready():
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
            revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            if revision != "0001":
                return JSONResponse(
                    status_code=503, content={"status": "unavailable", "database": "migration_required"}
                )
    except SQLAlchemyError:
        return JSONResponse(status_code=503, content={"status": "unavailable", "database": "unavailable"})
    return {"status": "ok", "database": "ready", "schema_revision": revision}
