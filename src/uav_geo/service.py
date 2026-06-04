from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .geometry import (
    camera_ray_to_enu,
    enu_offset_to_geodetic,
    image_point_to_camera_ray,
    intersect_ray_with_ground_plane,
)
from .models import (
    AnnotationKind,
    CaptureOverrides,
    GeoResult,
    ImageAnnotation,
    ImagePoint,
    ResolvedCapture,
    SolvedAnnotation,
    TerrainOptions,
)
from .readers import DjiImageReader
from .terrain import intersect_ray_with_dem


def resolve_capture(
    image_path: str | Path,
    overrides: CaptureOverrides | None = None,
) -> ResolvedCapture:
    return DjiImageReader().read(image_path=image_path, overrides=overrides)


def _resolve_ground_altitude(
    capture: ResolvedCapture,
    overrides: CaptureOverrides | None,
) -> tuple[float, list[str]]:
    drone_state = capture.drone_state
    assumptions: list[str] = []
    if overrides and overrides.ground_absolute_altitude_m is not None:
        return overrides.ground_absolute_altitude_m, assumptions

    ground_altitude_m = drone_state.ground_absolute_altitude_m
    if ground_altitude_m is None:
        raise ValueError(
            "Unable to determine ground altitude. "
            "Provide relative_altitude_m or ground_absolute_altitude_m."
        )

    assumptions.append(
        "ground_absolute_altitude_m = absolute_altitude_m - relative_altitude_m"
    )
    return ground_altitude_m, assumptions


def _normalize_terrain_options(
    terrain_options: TerrainOptions | None,
) -> TerrainOptions:
    if terrain_options is None:
        return TerrainOptions()
    return terrain_options


def _solve_point_with_capture(
    capture: ResolvedCapture,
    point: ImagePoint,
    *,
    ground_altitude_m: float | None,
    assumptions: list[str],
    terrain_options: TerrainOptions,
) -> GeoResult:
    drone_state = capture.drone_state
    camera_orientation = drone_state.camera_orientation
    if camera_orientation is None:
        raise ValueError("Camera orientation is missing.")

    ray_camera = image_point_to_camera_ray(point, capture.intrinsics)
    ray_enu = camera_ray_to_enu(ray_camera, camera_orientation)
    terrain_model = "plane"
    terrain_source: str | None = None
    if terrain_options.uses_dem():
        terrain_intersection = intersect_ray_with_dem(
            ray_enu=ray_enu,
            drone_latitude_deg=drone_state.latitude_deg,
            drone_longitude_deg=drone_state.longitude_deg,
            drone_absolute_altitude_m=drone_state.absolute_altitude_m,
            terrain_options=terrain_options,
        )
        intersection = (
            terrain_intersection.east_m,
            terrain_intersection.north_m,
            terrain_intersection.up_m,
        )
        terrain_model = "dem"
        terrain_source = str(Path(terrain_options.dem_path).resolve())
    else:
        if ground_altitude_m is None:
            raise ValueError("Plane terrain model requires ground altitude.")
        intersection = intersect_ray_with_ground_plane(
            ray_enu=ray_enu,
            drone_absolute_altitude_m=drone_state.absolute_altitude_m,
            ground_absolute_altitude_m=ground_altitude_m,
        )

    latitude_deg, longitude_deg, altitude_m = enu_offset_to_geodetic(
        origin_latitude_deg=drone_state.latitude_deg,
        origin_longitude_deg=drone_state.longitude_deg,
        origin_altitude_m=drone_state.absolute_altitude_m,
        east_m=intersection[0],
        north_m=intersection[1],
        up_m=intersection[2],
    )

    slant_range_m = (
        intersection[0] ** 2 + intersection[1] ** 2 + intersection[2] ** 2
    ) ** 0.5

    return GeoResult(
        latitude_deg=latitude_deg,
        longitude_deg=longitude_deg,
        ground_altitude_m=altitude_m,
        east_offset_m=intersection[0],
        north_offset_m=intersection[1],
        slant_range_m=slant_range_m,
        used_camera_orientation=camera_orientation,
        metadata_sources=capture.metadata_sources,
        terrain_model=terrain_model,
        terrain_source=terrain_source,
        assumptions=list(assumptions),
    )


def solve_image_point(
    image_path: str | Path,
    point: ImagePoint,
    overrides: CaptureOverrides | None = None,
    terrain_options: TerrainOptions | None = None,
) -> GeoResult:
    capture = resolve_capture(image_path=image_path, overrides=overrides)
    terrain_options = _normalize_terrain_options(terrain_options)
    assumptions: list[str]
    ground_altitude_m: float | None
    if terrain_options.uses_dem():
        ground_altitude_m = None
        assumptions = [
            f"terrain_model = dem({Path(terrain_options.dem_path).resolve()})",
            "DEM 高程采样单位为米，且必须与无人机 absolute_altitude_m 使用同一高程基准。",
        ]
    else:
        ground_altitude_m, assumptions = _resolve_ground_altitude(capture, overrides)
        assumptions.insert(0, "terrain_model = plane")
    return _solve_point_with_capture(
        capture,
        point,
        ground_altitude_m=ground_altitude_m,
        assumptions=assumptions,
        terrain_options=terrain_options,
    )


def solve_image_points(
    image_path: str | Path,
    points: Iterable[ImagePoint],
    overrides: CaptureOverrides | None = None,
    terrain_options: TerrainOptions | None = None,
) -> list[GeoResult]:
    capture = resolve_capture(image_path=image_path, overrides=overrides)
    terrain_options = _normalize_terrain_options(terrain_options)
    assumptions: list[str]
    ground_altitude_m: float | None
    if terrain_options.uses_dem():
        ground_altitude_m = None
        assumptions = [
            f"terrain_model = dem({Path(terrain_options.dem_path).resolve()})",
            "DEM 高程采样单位为米，且必须与无人机 absolute_altitude_m 使用同一高程基准。",
        ]
    else:
        ground_altitude_m, assumptions = _resolve_ground_altitude(capture, overrides)
        assumptions.insert(0, "terrain_model = plane")
    return [
        _solve_point_with_capture(
            capture,
            point,
            ground_altitude_m=ground_altitude_m,
            assumptions=assumptions,
            terrain_options=terrain_options,
        )
        for point in points
    ]


def _build_geojson(
    kind: AnnotationKind,
    results: list[GeoResult],
) -> dict[str, object]:
    coordinates = [result.to_coordinate() for result in results]

    if kind == "point":
        return {
            "type": "Point",
            "coordinates": coordinates[0],
        }
    if kind == "polyline":
        return {
            "type": "LineString",
            "coordinates": coordinates,
        }
    if kind == "polygon":
        ring = list(coordinates)
        if ring[0] != ring[-1]:
            ring.append(ring[0])
        return {
            "type": "Polygon",
            "coordinates": [ring],
        }
    raise ValueError(f"Unsupported annotation kind: {kind}")


def solve_annotation(
    image_path: str | Path,
    annotation: ImageAnnotation,
    overrides: CaptureOverrides | None = None,
    terrain_options: TerrainOptions | None = None,
) -> SolvedAnnotation:
    if annotation.kind == "point" and len(annotation.vertices) != 1:
        raise ValueError("Point annotations must contain exactly one vertex.")
    if annotation.kind == "polyline" and len(annotation.vertices) < 2:
        raise ValueError("Polyline annotations must contain at least two vertices.")
    if annotation.kind == "polygon" and len(annotation.vertices) < 3:
        raise ValueError("Polygon annotations must contain at least three vertices.")

    results = solve_image_points(
        image_path=image_path,
        points=annotation.vertices,
        overrides=overrides,
        terrain_options=terrain_options,
    )
    return SolvedAnnotation(
        annotation_id=annotation.annotation_id,
        kind=annotation.kind,
        label=annotation.label,
        vertices=list(annotation.vertices),
        results=results,
        geojson=_build_geojson(annotation.kind, results),
    )


def solve_annotations(
    image_path: str | Path,
    annotations: Iterable[ImageAnnotation],
    overrides: CaptureOverrides | None = None,
    terrain_options: TerrainOptions | None = None,
) -> list[SolvedAnnotation]:
    return [
        solve_annotation(
            image_path=image_path,
            annotation=annotation,
            overrides=overrides,
            terrain_options=terrain_options,
        )
        for annotation in annotations
    ]
