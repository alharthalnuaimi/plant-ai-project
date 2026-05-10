"""
Plant health MVP API: vision → structured signals → rule-based survival → Llama narrative.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from core.errors import AppError
from core.observability import wire_observability
from routes.chat import router as chat_router
from routes.dataset_meta import router as dataset_meta_router
from routes.predict import router as predict_router
from routes.sensor import router as sensor_router
from routes.survival import router as survival_router

app = FastAPI(
    title="Plant Health MVP",
    description="Vision classifies images; Llama only reasons over structured context.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
wire_observability(app)

app.include_router(predict_router)
app.include_router(sensor_router)
app.include_router(survival_router)
app.include_router(chat_router)
app.include_router(dataset_meta_router)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "n/a")
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": str(exc.detail), "request_id": request_id},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "n/a")
    return JSONResponse(
        status_code=500,
        content={"error": "internal_server_error", "request_id": request_id},
    )


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "n/a")
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.code, "message": exc.message, "request_id": request_id},
    )


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
