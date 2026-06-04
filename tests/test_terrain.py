from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from uav_geo.errors import GeometryError
from uav_geo.models import TerrainOptions
from uav_geo.server import _list_dem_files
from uav_geo.terrain import intersect_ray_with_dem, load_dem_dataset


def _write_dem(
    path: Path,
    values: np.ndarray,
    *,
    west: float,
    north: float,
    pixel_size_deg: float,
) -> None:
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=values.shape[1],
        height=values.shape[0],
        count=1,
        dtype=str(values.dtype),
        crs="EPSG:4326",
        transform=from_origin(west, north, pixel_size_deg, pixel_size_deg),
        nodata=-9999,
    ) as dataset:
        dataset.write(values, 1)


def test_dem_sampling_uses_bilinear_interpolation(tmp_path: Path) -> None:
    dem_path = tmp_path / "bilinear.tif"
    _write_dem(
        dem_path,
        np.array([[100, 200], [300, 400]], dtype=np.int16),
        west=106.0,
        north=29.002,
        pixel_size_deg=0.001,
    )

    dem = load_dem_dataset(str(dem_path))
    altitude_m = dem.sample_altitude_m(106.001, 29.001)

    assert altitude_m == pytest.approx(250.0, rel=0, abs=1e-6)


def test_dem_intersection_matches_flat_ground_for_nadir_camera(tmp_path: Path) -> None:
    dem_path = tmp_path / "flat.tif"
    _write_dem(
        dem_path,
        np.full((20, 20), 400, dtype=np.int16),
        west=106.59,
        north=29.60,
        pixel_size_deg=0.0001,
    )

    result = intersect_ray_with_dem(
        ray_enu=(0.0, 0.0, -1.0),
        drone_latitude_deg=29.599,
        drone_longitude_deg=106.591,
        drone_absolute_altitude_m=500.0,
        terrain_options=TerrainOptions(
            dem_path=str(dem_path),
            ray_step_m=5.0,
            binary_search_iterations=20,
        ),
    )

    assert math.isclose(result.east_m, 0.0, abs_tol=1e-6)
    assert math.isclose(result.north_m, 0.0, abs_tol=1e-6)
    assert result.up_m == pytest.approx(-100.0, rel=0, abs=1e-3)
    assert result.ground_altitude_m == pytest.approx(400.0, rel=0, abs=1e-6)


def test_dem_intersection_raises_when_drone_outside_dem(tmp_path: Path) -> None:
    dem_path = tmp_path / "small.tif"
    _write_dem(
        dem_path,
        np.full((10, 10), 400, dtype=np.int16),
        west=106.60,
        north=29.60,
        pixel_size_deg=0.0001,
    )

    with pytest.raises(GeometryError, match="无人机位置超出 DEM 覆盖范围"):
        intersect_ray_with_dem(
            ray_enu=(0.0, 0.0, -1.0),
            drone_latitude_deg=29.500,
            drone_longitude_deg=106.500,
            drone_absolute_altitude_m=500.0,
            terrain_options=TerrainOptions(
                dem_path=str(dem_path),
                ray_step_m=5.0,
                binary_search_iterations=20,
            ),
        )


def test_list_dem_files_only_returns_tif_files(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    _write_dem(
        tmp_path / "a" / "terrain.tif",
        np.full((4, 4), 100, dtype=np.int16),
        west=106.0,
        north=29.0,
        pixel_size_deg=0.001,
    )
    (tmp_path / "a" / "note.txt").write_text("ignore", encoding="utf-8")

    result = _list_dem_files(tmp_path)

    assert result == [str((tmp_path / "a" / "terrain.tif"))]
