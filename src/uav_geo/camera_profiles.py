from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CameraProfile:
    model_name: str
    image_source: str | None
    sensor_width_mm: float
    sensor_height_mm: float


DJI_CAMERA_PROFILES: tuple[CameraProfile, ...] = (
    # Matrice 4T / M4TD wide camera
    CameraProfile(
        model_name="M4TD",
        image_source="WideCamera",
        sensor_width_mm=9.6,
        sensor_height_mm=7.2,
    ),
    CameraProfile(
        model_name="DJI M4TD",
        image_source="WideCamera",
        sensor_width_mm=9.6,
        sensor_height_mm=7.2,
    ),
)


def match_dji_camera_profile(
    *,
    model_name: str | None,
    image_source: str | None,
) -> CameraProfile | None:
    normalized_model = (model_name or "").strip()
    normalized_source = (image_source or "").strip()
    for profile in DJI_CAMERA_PROFILES:
        if normalized_model != profile.model_name:
            continue
        if profile.image_source is not None and normalized_source != profile.image_source:
            continue
        return profile
    return None
