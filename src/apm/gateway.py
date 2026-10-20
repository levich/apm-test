"""An explicit Docker API read allowlist, including a streamed events endpoint."""

import re
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Request
from starlette.background import BackgroundTask
from starlette.responses import Response, StreamingResponse


def allowed(method, path):
    path = re.sub(r"^/v\d+\.\d+", "", path)
    return method == "GET" and path in ("/_ping", "/version", "/containers/json", "/events")


def create_gateway(socket="/var/run/docker.sock"):
    @asynccontextmanager
    async def lifespan(app):
        async with httpx.AsyncClient(
            transport=httpx.AsyncHTTPTransport(uds=socket), base_url="http://docker", timeout=None
        ) as client:
            app.state.client = client
            yield

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.api_route("/{path:path}", methods=["GET", "HEAD", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
    async def proxy(path: str, request: Request):
        if not allowed(request.method, "/" + path):
            raise HTTPException(403, "Docker operation is outside the read allowlist")
        client = request.app.state.client
        outgoing = client.build_request("GET", "/" + path, params=request.query_params)
        try:
            response = await client.send(outgoing, stream=True)
        except httpx.HTTPError:
            return Response("Docker Engine unavailable", status_code=503)
        return StreamingResponse(
            response.aiter_raw(),
            status_code=response.status_code,
            media_type=response.headers.get("content-type", "application/json"),
            background=BackgroundTask(response.aclose),
        )

    return app
