"""
Admin dataset management endpoints (Phase 6).
Exposes POST /admin/datasets/upload and GET /admin/datasets.
"""

from __future__ import annotations

import datetime
import io
import json
import logging
import os
import shutil
import uuid
import zipfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from services.readiness_check import evaluate_dataset_readiness

router = APIRouter(prefix="/admin/datasets", tags=["admin_datasets"])
log = logging.getLogger("plantvision.admin_datasets")

# Resolve dataset uploads directory relative to the repo root.
# Override with DATASET_UPLOADS_PATH env var for Railway volumes.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
UPLOADS_ROOT = Path(os.getenv("DATASET_UPLOADS_PATH", str(_REPO_ROOT / "dataset" / "uploads")))
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

    # Evaluate readiness. A failure must not leave a folder that breaks the listing.
    try:
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
    except Exception as exc:  # noqa: BLE001 - the zip's contents are untrusted
        log.warning("Dataset readiness failed for %s: %s", upload_id, type(exc).__name__)
        shutil.rmtree(batch_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail="Dataset archive could not be evaluated") from exc

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
                try:
                    report = evaluate_dataset_readiness(d)
                except Exception as exc:  # noqa: BLE001 - one bad folder must not break the listing
                    log.warning("Skipping dataset folder %s: %s", d.name, type(exc).__name__)
                    continue
                batches.append({
                    "upload_id": d.name,
                    "filename": d.name,
                    "uploaded_at": datetime.datetime.fromtimestamp(d.stat().st_ctime, tz=datetime.timezone.utc).isoformat(),
                    "total_images": report["total_images"],
                    "status": report["status"],
                    "report": report,
                })

    return sorted(batches, key=lambda x: x.get("uploaded_at", ""), reverse=True)
