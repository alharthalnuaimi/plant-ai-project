from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class PlantHealthScore(BaseModel):
    plant_health: int = Field(ge=0, le=100, description="Overall plant health 0-100")
    disease_risk: Literal["Low", "Medium", "High", "Critical"] = "Low"
    environment_stress: Literal["Low", "Medium", "High"] = "Low"
    survival_chance: int = Field(ge=0, le=100, description="Estimated survival 0-100")
    recommendation: str = ""
    class_name: str = ""
    disease_type: str = "unknown"
    source: Literal["live", "demo", "baseline"] = "baseline"
