"""
Admin dataset management endpoints (Phase 6).
Exposes POST /admin/datasets/upload and GET /admin/datasets.
"""

from __future__ import annotations

import datetime
import io
import json
import os
import shutil
import uuid
import zipfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from services.readiness_check import evaluate_dataset_readiness

router = APIRouter(prefix="/admin/datasets", tags=["admin_datasets"])

BASE_DIR = Path("d:/antigravity/M.P.AI")
UPLOADS_ROOT = BASE_DIR / "dataset" / "uploads"
UPLOADS_ROOT.mkdir(parents=True, exist_ok=True)


@router.post("/upload")
async def upload_dataset_batch(file: UploadFile = File(...)) -> dict[str, Any]:
    """Upload a dataset ZIP file, validate format, run readiness check & store batch."""
    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Expected a .zip dataset archive")

    contents = await file.read()
    if len(contents) < 64:
        raise HTTPException(status_code=400, detail="Uploaded zip file is empty")

    upload_id = f"batch_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    batch_dir = UPLOADS_ROOT / upload_id
    batch_dir.mkdir(parents=True, exist_ok=True)

    # Extract ZIP
    try:
        with zipfile.ZipFile(io.BytesIO(contents)) as z:
            z.extractall(batch_dir)
    except Exception as exc:
        shutil.rmtree(batch_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail=f"Invalid zip archive: {exc}")

    # Evaluate readiness
    report = evaluate_dataset_readiness(batch_dir)

    # Write batch metadata
    meta = {
        "upload_id": upload_id,
        "filename": file.filename,
        "uploaded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "total_images": report["total_images"],
        "status": report["status"],
        "report": report,
    }
    (batch_dir / "batch_meta.json").write_text(json.dumps(meta, indent=2))

    return meta


@router.get("")
async def list_dataset_batches() -> list[dict[str, Any]]:
    """List all uploaded dataset batches and their readiness status."""
    batches = []
    if not UPLOADS_ROOT.exists():
        return []

    for d in UPLOADS_ROOT.iterdir():
        if d.is_dir():
            meta_file = d / "batch_meta.json"
            if meta_file.exists():
                try:
                    batches.append(json.loads(meta_file.read_text()))
                except Exception:
                    pass
            else:
                report = evaluate_dataset_readiness(d)
                batches.append({
                    "upload_id": d.name,
                    "filename": d.name,
                    "uploaded_at": datetime.datetime.fromtimestamp(d.stat().st_ctime, tz=datetime.timezone.utc).isoformat(),
                    "total_images": report["total_images"],
                    "status": report["status"],
                    "report": report,
                })

    return sorted(batches, key=lambda x: x.get("uploaded_at", ""), reverse=True)
