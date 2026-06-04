from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

AnnotationKind = Literal["point", "polyline", "polygon"]


@dataclass(slots=True)
class ImagePoint:
    u: float
    v: float

    def to_dict(self) -> dict[str, float]:
        return {"u": self.u, "v": self.v}


@dataclass(slots=True)
class Orientation:
    yaw_deg: float
    pitch_deg: float
    roll_deg: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return {
            "yaw_deg": self.yaw_deg,
            "pitch_deg": self.pitch_deg,
            "roll_deg": self.roll_deg,
        }


@dataclass(slots=True)
class CameraIntrinsics:
    image_width_px: int
    image_height_px: int
    focal_length_mm: float | None = None
    focal_length_35mm_mm: float | None = None
    sensor_width_mm: float | None = None
    sensor_height_mm: float | None = None
    principal_point_x_px: float | None = None
    principal_point_y_px: float | None = None

    @property
    def principal_point(self) -> tuple[float, float]:
        cx = self.principal_point_x_px
        cy = self.principal_point_y_px
        if cx is None:
            cx = self.image_width_px / 2.0
        if cy is None:
            cy = self.image_height_px / 2.0
        return cx, cy

    def to_dict(self) -> dict[str, float | int | None]:
        return {
            "image_width_px": self.image_width_px,
            "image_height_px": self.image_height_px,
            "focal_length_mm": self.focal_length_mm,
            "focal_length_35mm_mm": self.focal_length_35mm_mm,
            "sensor_width_mm": self.sensor_width_mm,
            "sensor_height_mm": self.sensor_height_mm,
            "principal_point_x_px": self.principal_point_x_px,
            "principal_point_y_px": self.principal_point_y_px,
        }


@dataclass(slots=True)
class DroneState:
    latitude_deg: float
    longitude_deg: float
    absolute_altitude_m: float
    relative_altitude_m: float | None = None
    flight_orientation: Orientation | None = None
    camera_orientation: Orientation | None = None
    gps_status: str | None = None
    altitude_type: str | None = None
    rtk_std_lat_m: float | None = None
    rtk_std_lon_m: float | None = None
    rtk_std_hgt_m: float | None = None
    lrf_target_latitude_deg: float | None = None
    lrf_target_longitude_deg: float | None = None
    lrf_target_altitude_m: float | None = None
    lrf_target_distance_m: float | None = None

    @property
    def ground_absolute_altitude_m(self) -> float | None:
        if self.relative_altitude_m is None:
            return None
        return self.absolute_altitude_m - self.relative_altitude_m

    def to_dict(self) -> dict[str, Any]:
        return {
            "latitude_deg": self.latitude_deg,
            "longitude_deg": self.longitude_deg,
            "absolute_altitude_m": self.absolute_altitude_m,
            "relative_altitude_m": self.relative_altitude_m,
            "ground_absolute_altitude_m": self.ground_absolute_altitude_m,
            "flight_orientation": (
                None if self.flight_orientation is None else self.flight_orientation.to_dict()
            ),
            "camera_orientation": (
                None if self.camera_orientation is None else self.camera_orientation.to_dict()
            ),
            "gps_status": self.gps_status,
            "altitude_type": self.altitude_type,
            "rtk_std_lat_m": self.rtk_std_lat_m,
            "rtk_std_lon_m": self.rtk_std_lon_m,
            "rtk_std_hgt_m": self.rtk_std_hgt_m,
            "lrf_target_latitude_deg": self.lrf_target_latitude_deg,
            "lrf_target_longitude_deg": self.lrf_target_longitude_deg,
            "lrf_target_altitude_m": self.lrf_target_altitude_m,
            "lrf_target_distance_m": self.lrf_target_distance_m,
        }


@dataclass(slots=True)
class CaptureOverrides:
    latitude_deg: float | None = None
    longitude_deg: float | None = None
    absolute_altitude_m: float | None = None
    relative_altitude_m: float | None = None
    ground_absolute_altitude_m: float | None = None
    gimbal_yaw_deg: float | None = None
    gimbal_pitch_deg: float | None = None
    gimbal_roll_deg: float | None = None
    flight_yaw_deg: float | None = None
    flight_pitch_deg: float | None = None
    flight_roll_deg: float | None = None
    focal_length_mm: float | None = None
    focal_length_35mm_mm: float | None = None
    sensor_width_mm: float | None = None
    sensor_height_mm: float | None = None
    principal_point_x_px: float | None = None
    principal_point_y_px: float | None = None

    def has_any_value(self) -> bool:
        return any(
            getattr(self, field_name) is not None
            for field_name in self.__dataclass_fields__
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            field_name: getattr(self, field_name)
            for field_name in self.__dataclass_fields__
            if getattr(self, field_name) is not None
        }


@dataclass(slots=True)
class TerrainOptions:
    dem_path: str | None = None
    ray_step_m: float = 10.0
    binary_search_iterations: int = 24

    def uses_dem(self) -> bool:
        return bool(self.dem_path)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dem_path": self.dem_path,
            "ray_step_m": self.ray_step_m,
            "binary_search_iterations": self.binary_search_iterations,
        }


@dataclass(slots=True)
class ResolvedCapture:
    image_path: str
    intrinsics: CameraIntrinsics
    drone_state: DroneState
    metadata_sources: dict[str, str] = field(default_factory=dict)
    raw_metadata: dict[str, Any] = field(default_factory=dict)

    def to_summary_dict(self) -> dict[str, Any]:
        return {
            "image_path": self.image_path,
            "intrinsics": self.intrinsics.to_dict(),
            "drone_state": self.drone_state.to_dict(),
            "metadata_sources": dict(self.metadata_sources),
        }


@dataclass(slots=True)
class GeoResult:
    latitude_deg: float
    longitude_deg: float
    ground_altitude_m: float
    east_offset_m: float
    north_offset_m: float
    slant_range_m: float
    used_camera_orientation: Orientation
    metadata_sources: dict[str, str]
    terrain_model: str = "plane"
    terrain_source: str | None = None
    assumptions: list[str] = field(default_factory=list)

    def to_coordinate(self) -> list[float]:
        return [self.longitude_deg, self.latitude_deg, self.ground_altitude_m]

    def to_dict(self) -> dict[str, Any]:
        return {
            "latitude_deg": self.latitude_deg,
            "longitude_deg": self.longitude_deg,
            "ground_altitude_m": self.ground_altitude_m,
            "east_offset_m": self.east_offset_m,
            "north_offset_m": self.north_offset_m,
            "slant_range_m": self.slant_range_m,
            "used_camera_orientation": self.used_camera_orientation.to_dict(),
            "metadata_sources": dict(self.metadata_sources),
            "terrain_model": self.terrain_model,
            "terrain_source": self.terrain_source,
            "assumptions": list(self.assumptions),
        }


@dataclass(slots=True)
class ImageAnnotation:
    annotation_id: str
    kind: AnnotationKind
    vertices: list[ImagePoint]
    label: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "annotation_id": self.annotation_id,
            "kind": self.kind,
            "label": self.label,
            "vertices": [vertex.to_dict() for vertex in self.vertices],
        }


@dataclass(slots=True)
class SolvedAnnotation:
    annotation_id: str
    kind: AnnotationKind
    label: str | None
    vertices: list[ImagePoint]
    results: list[GeoResult]
    geojson: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "annotation_id": self.annotation_id,
            "kind": self.kind,
            "label": self.label,
            "vertices": [vertex.to_dict() for vertex in self.vertices],
            "results": [result.to_dict() for result in self.results],
            "geojson": self.geojson,
        }
