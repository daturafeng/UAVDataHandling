from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import rasterio
from pyproj import Transformer

from .errors import GeometryError
from .geometry import enu_offset_to_geodetic
from .models import TerrainOptions


@dataclass(frozen=True, slots=True)
class TerrainIntersection:
    east_m: float
    north_m: float
    up_m: float
    ground_altitude_m: float


@dataclass(frozen=True, slots=True)
class _DemDataset:
    path: str
    width: int
    height: int
    transform: object
    inverse_transform: object
    bounds: tuple[float, float, float, float]
    band: object
    min_altitude_m: float
    crs_transformer: Transformer | None

    def sample_altitude_m(
        self,
        longitude_deg: float,
        latitude_deg: float,
    ) -> float | None:
        x, y = longitude_deg, latitude_deg
        if self.crs_transformer is not None:
            x, y = self.crs_transformer.transform(longitude_deg, latitude_deg)

        left, bottom, right, top = self.bounds
        if x < left or x > right or y < bottom or y > top:
            return None

        col, row = self.inverse_transform * (x, y)
        col -= 0.5
        row -= 0.5
        col = min(max(col, 0.0), self.width - 1.0)
        row = min(max(row, 0.0), self.height - 1.0)

        nearest_altitude = self._sample_nearest(row, col)
        row0 = int(math.floor(row))
        col0 = int(math.floor(col))
        row1 = min(row0 + 1, self.height - 1)
        col1 = min(col0 + 1, self.width - 1)

        q11 = self._sample_cell(row0, col0)
        q21 = self._sample_cell(row0, col1)
        q12 = self._sample_cell(row1, col0)
        q22 = self._sample_cell(row1, col1)
        if q11 is None or q21 is None or q12 is None or q22 is None:
            return nearest_altitude

        dx = col - col0
        dy = row - row0
        top_value = q11 * (1.0 - dx) + q21 * dx
        bottom_value = q12 * (1.0 - dx) + q22 * dx
        return top_value * (1.0 - dy) + bottom_value * dy

    def _sample_nearest(self, row: float, col: float) -> float | None:
        return self._sample_cell(int(round(row)), int(round(col)))

    def _sample_cell(self, row: int, col: int) -> float | None:
        value = self.band[row, col]
        if bool(getattr(value, "mask", False)):
            return None
        return float(value)


@lru_cache(maxsize=8)
def load_dem_dataset(dem_path: str) -> _DemDataset:
    resolved_path = str(Path(dem_path).resolve())
    with rasterio.open(resolved_path) as dataset:
        band = dataset.read(1, masked=True)
        valid_band = band.compressed()
        if valid_band.size == 0:
            raise GeometryError(f"DEM 文件不包含可用高程值: {resolved_path}")

        transformer: Transformer | None = None
        if dataset.crs is not None and dataset.crs.to_epsg() != 4326:
            transformer = Transformer.from_crs(
                "EPSG:4326",
                dataset.crs,
                always_xy=True,
            )

        return _DemDataset(
            path=resolved_path,
            width=dataset.width,
            height=dataset.height,
            transform=dataset.transform,
            inverse_transform=~dataset.transform,
            bounds=tuple(dataset.bounds),
            band=band,
            min_altitude_m=float(valid_band.min()),
            crs_transformer=transformer,
        )


def intersect_ray_with_dem(
    *,
    ray_enu: tuple[float, float, float],
    drone_latitude_deg: float,
    drone_longitude_deg: float,
    drone_absolute_altitude_m: float,
    terrain_options: TerrainOptions,
) -> TerrainIntersection:
    if not terrain_options.dem_path:
        raise GeometryError("DEM 地形求交缺少 dem_path。")

    if terrain_options.ray_step_m <= 0:
        raise GeometryError("DEM 地形求交的 ray_step_m 必须大于 0。")

    if terrain_options.binary_search_iterations <= 0:
        raise GeometryError("DEM 地形求交的 binary_search_iterations 必须大于 0。")

    dz = ray_enu[2]
    if dz >= -1e-9:
        raise GeometryError("相机射线未指向地面，无法与 DEM 地形相交。")

    dem_dataset = load_dem_dataset(terrain_options.dem_path)
    initial_ground_altitude_m = dem_dataset.sample_altitude_m(
        drone_longitude_deg,
        drone_latitude_deg,
    )
    if initial_ground_altitude_m is None:
        raise GeometryError("无人机位置超出 DEM 覆盖范围，无法进行地形求交。")

    initial_gap_m = drone_absolute_altitude_m - initial_ground_altitude_m
    if initial_gap_m <= 0:
        raise GeometryError("无人机绝对高度低于或等于 DEM 地表高程，无法进行地形求交。")

    max_distance_m = (
        (drone_absolute_altitude_m - dem_dataset.min_altitude_m) / abs(dz)
        + terrain_options.ray_step_m
    )

    previous_distance_m = 0.0
    previous_gap_m = initial_gap_m
    current_distance_m = terrain_options.ray_step_m
    while current_distance_m <= max_distance_m + 1e-9:
        current_gap_m, current_ground_altitude_m = _evaluate_ray_gap(
            distance_m=current_distance_m,
            ray_enu=ray_enu,
            drone_latitude_deg=drone_latitude_deg,
            drone_longitude_deg=drone_longitude_deg,
            drone_absolute_altitude_m=drone_absolute_altitude_m,
            dem_dataset=dem_dataset,
        )

        if current_gap_m <= 0:
            intersection_distance_m, intersection_altitude_m = _refine_intersection_distance(
                low_distance_m=previous_distance_m,
                high_distance_m=current_distance_m,
                low_gap_m=previous_gap_m,
                ray_enu=ray_enu,
                drone_latitude_deg=drone_latitude_deg,
                drone_longitude_deg=drone_longitude_deg,
                drone_absolute_altitude_m=drone_absolute_altitude_m,
                dem_dataset=dem_dataset,
                iterations=terrain_options.binary_search_iterations,
            )
            return TerrainIntersection(
                east_m=ray_enu[0] * intersection_distance_m,
                north_m=ray_enu[1] * intersection_distance_m,
                up_m=ray_enu[2] * intersection_distance_m,
                ground_altitude_m=intersection_altitude_m,
            )

        previous_distance_m = current_distance_m
        previous_gap_m = current_gap_m
        current_distance_m += terrain_options.ray_step_m

    raise GeometryError("在 DEM 覆盖范围内未找到射线与地形的交点。")


def _evaluate_ray_gap(
    *,
    distance_m: float,
    ray_enu: tuple[float, float, float],
    drone_latitude_deg: float,
    drone_longitude_deg: float,
    drone_absolute_altitude_m: float,
    dem_dataset: _DemDataset,
) -> tuple[float, float]:
    latitude_deg, longitude_deg, altitude_m = enu_offset_to_geodetic(
        origin_latitude_deg=drone_latitude_deg,
        origin_longitude_deg=drone_longitude_deg,
        origin_altitude_m=drone_absolute_altitude_m,
        east_m=ray_enu[0] * distance_m,
        north_m=ray_enu[1] * distance_m,
        up_m=ray_enu[2] * distance_m,
    )
    ground_altitude_m = dem_dataset.sample_altitude_m(longitude_deg, latitude_deg)
    if ground_altitude_m is None:
        raise GeometryError("射线离开 DEM 覆盖范围，无法继续进行地形求交。")
    return altitude_m - ground_altitude_m, ground_altitude_m


def _refine_intersection_distance(
    *,
    low_distance_m: float,
    high_distance_m: float,
    low_gap_m: float,
    ray_enu: tuple[float, float, float],
    drone_latitude_deg: float,
    drone_longitude_deg: float,
    drone_absolute_altitude_m: float,
    dem_dataset: _DemDataset,
    iterations: int,
) -> tuple[float, float]:
    low = low_distance_m
    high = high_distance_m
    gap_at_low = low_gap_m
    final_altitude_m = drone_absolute_altitude_m + ray_enu[2] * high_distance_m

    for _ in range(iterations):
        mid = (low + high) / 2.0
        gap_at_mid, ground_altitude_m = _evaluate_ray_gap(
            distance_m=mid,
            ray_enu=ray_enu,
            drone_latitude_deg=drone_latitude_deg,
            drone_longitude_deg=drone_longitude_deg,
            drone_absolute_altitude_m=drone_absolute_altitude_m,
            dem_dataset=dem_dataset,
        )
        final_altitude_m = ground_altitude_m
        if gap_at_mid > 0:
            low = mid
            gap_at_low = gap_at_mid
        else:
            high = mid

        if abs(gap_at_low) < 1e-4 and abs(gap_at_mid) < 1e-4:
            break

    return (low + high) / 2.0, final_altitude_m
