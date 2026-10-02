"""Authenticated operator API: enqueue immediately, never crawl in a request."""

from __future__ import annotations

import hmac
from collections.abc import Awaitable, Callable, Sequence

from aiohttp import web
from pydantic import ValidationError

from .jobs import JobManager
from .models import AcquisitionError, CrawlPolicy, Model


def create_app(manager: JobManager, token: str) -> web.Application:
    if len(token) < 32 or not token.isascii():
        raise ValueError("operator API token must contain at least 32 ASCII characters")

    @web.middleware
    async def auth(
        request: web.Request, handler: Callable[[web.Request], Awaitable[web.StreamResponse]]
    ) -> web.StreamResponse:
        supplied = request.headers.get("Authorization", "")
        if not hmac.compare_digest(supplied.encode(), ("Bearer " + token).encode()):
            return web.json_response({"error": "unauthorized"}, status=401)
        try:
            return await handler(request)
        except KeyError:
            return web.json_response({"error": "job_not_found"}, status=404)
        except (ValueError, ValidationError, TypeError):
            return web.json_response({"error": "invalid_request"}, status=400)
        except AcquisitionError as exc:
            return web.json_response(
                {"error": exc.code}, status=429 if exc.code == "job_admission_limit" else 400
            )

    app = web.Application(middlewares=[auth], client_max_size=32768)

    async def submit(request: web.Request) -> web.Response:
        body = await request.json()
        if not isinstance(body, dict) or set(body) - {"seeds", "policy"}:
            raise ValueError("invalid_request")
        seeds = body.get("seeds")
        if not isinstance(seeds, list) or not all(isinstance(seed, str) for seed in seeds):
            raise ValueError("invalid_seeds")
        job = manager.submit(seeds, CrawlPolicy.model_validate(body.get("policy", {})))
        return web.json_response({"job_id": job.job_id, "status": job.status}, status=202)

    async def status(request: web.Request) -> web.Response:
        return web.json_response(
            manager.repository.get_job(request.match_info["job_id"]).model_dump(mode="json")
        )

    async def listing(request: web.Request) -> web.Response:
        job_id = request.match_info["job_id"]
        manager.repository.get_job(job_id)
        offset, limit = (
            int(request.query.get("offset", "0")),
            int(request.query.get("limit", "100")),
        )
        if offset < 0 or not 1 <= limit <= 100:
            raise ValueError("invalid_pagination")
        kind = request.match_info["kind"]
        methods: dict[str, Callable[[str, int, int], Sequence[Model]]] = {
            "resources": manager.repository.resources,
            "artifacts": manager.repository.artifacts,
            "attempts": manager.repository.attempts,
            "discoveries": manager.repository.discoveries,
        }
        if kind not in methods:
            return web.json_response({"error": "not_found"}, status=404)
        rows = methods[kind](job_id, offset, limit)
        return web.json_response([row.model_dump(mode="json") for row in rows])

    async def cancel(request: web.Request) -> web.Response:
        result = await manager.cancel(request.match_info["job_id"])
        return web.json_response({"job_id": result.job_id, "status": result.status})

    async def cleanup(_app: web.Application) -> None:
        await manager.close()

    app.add_routes(
        [
            web.post("/crawl", submit),
            web.get("/crawl/{job_id}", status),
            web.get("/crawl/{job_id}/{kind}", listing),
            web.post("/crawl/{job_id}/cancel", cancel),
        ]
    )
    app.on_cleanup.append(cleanup)
    return app
