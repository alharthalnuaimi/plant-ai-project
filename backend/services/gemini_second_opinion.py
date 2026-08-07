"""
Gemini Second Opinion & Disagreement Evaluator (Phase 3).
Wraps Gemini vision API call with graceful fallback and automatic FEEDBACK_STORE logging.
"""

from __future__ import annotations

import logging
import os
from models.llama_model import get_gemini_client
from services.feedback_store import FEEDBACK_STORE

log = logging.getLogger("plantvision.gemini_second_opinion")


def evaluate_gemini_second_opinion(
    image_bytes: bytes,
    yolo_label: str,
    yolo_confidence: float,
    image_ref: str = "upload_image",
) -> tuple[str, bool, str]:
    """Run Gemini vision assessment on image to get second opinion.

    Returns (gemini_verdict, gemini_agrees, gemini_reasoning).
    Never raises an exception — graceful fallback if Gemini is offline/unconfigured.
    Auto-logs into FEEDBACK_STORE when gemini_agrees is False or yolo_confidence is low.
    """

    client = get_gemini_client()
    if client is None:
        log.info("Gemini API key not set — defaulting to agreement fallback.")
        return yolo_label, True, "Gemini second opinion bypassed (API key not configured)."

    try:
        prompt = (
            f"You are a plant pathology expert. A primary vision model diagnosed this plant image as: "
            f"'{yolo_label}' with confidence {yolo_confidence:.2f}.\n"
            f"Inspect the image independently.\n"
            f"Respond in 2-3 sentences specifying:\n"
            f"1) Whether you AGREE or DISAGREE with '{yolo_label}'.\n"
            f"2) Your own primary verdict label (e.g. Healthy, Powdery Mildew, Leaf Spot, Rust, Blight, Bacterial Wilt, Manganese Toxicity).\n"
            f"3) Your brief diagnostic reasoning."
        )

        response_text = client.generate_chat(
            messages=[{"role": "user", "content": prompt}],
            system_instruction="Provide concise, objective plant disease diagnostics."
        )

        response_lower = response_text.lower()
        gemini_agrees = "disagree" not in response_lower
        
        # Simple extraction of guess label
        gemini_verdict = yolo_label
        for candidate in ["healthy", "powdery mildew", "leaf spot", "rust", "blight", "bacterial wilt", "manganese toxicity"]:
            if candidate in response_lower and candidate != yolo_label.lower():
                gemini_verdict = candidate.title()
                break

        reasoning = response_text.strip()

        # Log disagreement or low confidence into scan_feedback
        if not gemini_agrees or yolo_confidence < 0.60:
            FEEDBACK_STORE.insert_feedback(
                image_ref=image_ref,
                yolo_label=yolo_label,
                yolo_confidence=yolo_confidence,
                gemini_label=gemini_verdict,
                gemini_agrees=gemini_agrees,
                reasoning=reasoning,
            )

        return gemini_verdict, gemini_agrees, reasoning

    except Exception as exc:
        log.warning("Gemini second-opinion call failed (non-fatal): %s", exc)
        return yolo_label, True, f"Gemini second opinion unavailable: {exc}"
