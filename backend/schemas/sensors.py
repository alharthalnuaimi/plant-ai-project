"""ESP32 / environment sensor schemas (POST /sensor, GET /sensor/latest)."""



from __future__ import annotations



from datetime import datetime, timezone

from typing import Literal



from pydantic import BaseModel, Field





class SensorInput(BaseModel):

    """Payload from ESP32 node (POST /sensor)."""



    device_id: str = Field(min_length=1, max_length=64)

    plant_id: str = Field(min_length=1, max_length=64)

    air_temperature: float = Field(ge=-40, le=60, description="Air temperature °C (DHT22)")

    air_humidity: float = Field(ge=0, le=100, description="Air relative humidity % (DHT22)")

    light_lux: float = Field(ge=0, description="Illuminance lux (BH1750)")

    soil_temperature: float = Field(ge=-10, le=50, description="Soil/environment temp °C (RS485)")

    soil_humidity: float = Field(ge=0, le=100, description="Soil moisture % (RS485)")

    soil_ph: float = Field(ge=0, le=14, description="Soil pH (RS485)")

    soil_ec: float = Field(ge=0, description="Soil EC mS/cm (RS485)")





class SensorStatus(BaseModel):

    """Rule-based environment stress labels from sensor_processing."""



    air_temperature_status: str

    air_humidity_status: str

    light_status: str

    soil_temperature_status: str

    soil_humidity_status: str

    ph_status: str

    ec_status: str

    overall_environment_status: str





class SensorReading(BaseModel):

    """Stored reading with metadata and derived status."""



    device_id: str

    plant_id: str

    air_temperature: float

    air_humidity: float

    light_lux: float

    soil_temperature: float

    soil_humidity: float

    soil_ph: float

    soil_ec: float

    timestamp: str

    status: SensorStatus





class SensorLatestResponse(BaseModel):

    ok: bool = True

    source: Literal["live", "none"] = "live"

    reading: SensorReading | None = None





def utc_now_iso() -> str:

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

