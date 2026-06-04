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
)
from .readers import DjiImageReader


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


def _solve_point_with_capture(
    capture: ResolvedCapture,
    point: ImagePoint,
    *,
    ground_altitude_m: float,
    assumptions: list[str],
) -> GeoResult:
    drone_state = capture.drone_state
    camera_orientation = drone_state.camera_orientation
    if camera_orientation is None:
        raise ValueError("Camera orientation is missing.")

    ray_camera = image_point_to_camera_ray(point, capture.intrinsics)
    ray_enu = camera_ray_to_enu(ray_camera, camera_orientation)
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
        assumptions=list(assumptions),
    )


def solve_image_point(
    image_path: str | Path,
    point: ImagePoint,
    overrides: CaptureOverrides | None = None,
) -> GeoResult:
    capture = resolve_capture(image_path=image_path, overrides=overrides)
    ground_altitude_m, assumptions = _resolve_ground_altitude(capture, overrides)
    return _solve_point_with_capture(
        capture,
        point,
        ground_altitude_m=ground_altitude_m,
        assumptions=assumptions,
    )


def solve_image_points(
    image_path: str | Path,
    points: Iterable[ImagePoint],
    overrides: CaptureOverrides | None = None,
) -> list[GeoResult]:
    capture = resolve_capture(image_path=image_path, overrides=overrides)
    ground_altitude_m, assumptions = _resolve_ground_altitude(capture, overrides)
    return [
        _solve_point_with_capture(
            capture,
            point,
            ground_altitude_m=ground_altitude_m,
            assumptions=assumptions,
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
) -> list[SolvedAnnotation]:
    return [
        solve_annotation(
            image_path=image_path,
            annotation=annotation,
            overrides=overrides,
        )
        for annotation in annotations
    ]
