"""
Abstract Base Class & Registry for Pluggable Annotation Agents (Phase 8).
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Any


class AnnotationAgent(ABC):
    """Common interface for vision-LLM and detection auto-annotation providers."""

    def __init__(self, name: str, env_var: str) -> None:
        self.name = name
        self.env_var = env_var

    @property
    def is_active(self) -> bool:
        return bool((os.getenv(self.env_var) or "").strip())

    @abstractmethod
    def annotate(self, image_bytes: bytes, context_label: str = "") -> dict[str, Any]:
        """Run annotation on an image.

        Returns {
            "provider": str,
            "class_label": str,
            "confidence": float,
            "bbox": [x_center, y_center, width, height] | None,
            "reasoning": str,
            "status": "success" | "error"
        }
        """
        ...
