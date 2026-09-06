import asyncio
import httpx
from sqlalchemy.exc import OperationalError
from app.main import app


def request(path):
    async def run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            return await client.get(path)

    return asyncio.run(run())


def test_liveness():
    assert request("/api/health/live").json()["status"] == "ok"


def test_readiness_failure_is_sanitized(monkeypatch):
    import app.main as main

    class Offline:
        def connect(self):
            raise OperationalError("secret connection details", {}, Exception("password"))

    monkeypatch.setattr(main, "get_engine", lambda: Offline())
    response = request("/api/health/ready")
    assert response.status_code == 503
    assert "password" not in response.text
    assert "secret" not in response.text
