from __future__ import annotations

from pathlib import Path

import pytest

from uav_geo.models import ImageAnnotation, ImagePoint, TerrainOptions
from uav_geo.readers import DjiImageReader
from uav_geo.service import solve_annotation, solve_image_point, solve_image_points

SAMPLE_IMAGE = Path(
    r"G:\DJIImage\drone_images\177 2026-01-08 11_29_21 (UTC+08)\DJI_20260108113251_0001_V.jpeg"
)
SAMPLE_IMAGE_NO_AUX = Path(
    r"G:\DJIImage\drone_images\177 2026-01-08 11_29_21 (UTC+08)\DJI_20260108113301_0004_V.jpeg"
)
SAMPLE_DEM = Path(
    r"G:\GIS\Data\Dem\重庆市\不统计\南岸区\重庆市_不统计_南岸区.tif"
)


@pytest.mark.skipif(not SAMPLE_IMAGE.exists(), reason="DJI 样例图片不存在")
def test_dji_reader_extracts_expected_fields() -> None:
    capture = DjiImageReader().read(SAMPLE_IMAGE)

    assert capture.intrinsics.image_width_px == 4032
    assert capture.intrinsics.image_height_px == 3024
    assert capture.intrinsics.focal_length_mm == pytest.approx(6.72, rel=0, abs=1e-6)
    assert capture.drone_state.latitude_deg == pytest.approx(29.59165345, rel=0, abs=1e-8)
    assert capture.drone_state.longitude_deg == pytest.approx(106.597808841, rel=0, abs=1e-9)
    assert capture.drone_state.absolute_altitude_m == pytest.approx(504.802, rel=0, abs=1e-6)
    assert capture.drone_state.relative_altitude_m == pytest.approx(116.275, rel=0, abs=1e-6)
    assert capture.drone_state.camera_orientation is not None
    assert capture.drone_state.camera_orientation.pitch_deg == pytest.approx(-90.0, rel=0, abs=1e-6)


@pytest.mark.skipif(not SAMPLE_IMAGE.exists(), reason="DJI 样例图片不存在")
def test_solver_returns_finite_result_for_sample_image_center() -> None:
    result = solve_image_point(
        image_path=SAMPLE_IMAGE,
        point=ImagePoint(u=2016, v=1512),
    )

    assert result.latitude_deg == pytest.approx(29.59165345, rel=0, abs=5e-6)
    assert result.longitude_deg == pytest.approx(106.597808841, rel=0, abs=5e-6)
    assert result.slant_range_m > 100.0


@pytest.mark.skipif(not SAMPLE_IMAGE_NO_AUX.exists(), reason="无 aux 的 DJI 样例图片不存在")
def test_solver_works_without_aux_xml() -> None:
    result = solve_image_point(
        image_path=SAMPLE_IMAGE_NO_AUX,
        point=ImagePoint(u=2016, v=1512),
    )

    assert result.latitude_deg == pytest.approx(29.592689461, rel=0, abs=5e-6)
    assert result.longitude_deg == pytest.approx(106.597828757, rel=0, abs=5e-6)
    assert result.metadata_sources["focal_length_mm"] == "exif"


@pytest.mark.skipif(not SAMPLE_IMAGE.exists(), reason="DJI 样例图片不存在")
def test_batch_solver_returns_multiple_results() -> None:
    results = solve_image_points(
        image_path=SAMPLE_IMAGE,
        points=[
            ImagePoint(u=2016, v=1512),
            ImagePoint(u=2216, v=1512),
        ],
    )

    assert len(results) == 2
    assert results[1].east_offset_m > results[0].east_offset_m


@pytest.mark.skipif(not SAMPLE_IMAGE.exists(), reason="DJI 样例图片不存在")
def test_polygon_annotation_returns_geojson() -> None:
    annotation = ImageAnnotation(
        annotation_id="polygon-1",
        kind="polygon",
        label="A1",
        vertices=[
            ImagePoint(u=1800, v=1300),
            ImagePoint(u=2200, v=1300),
            ImagePoint(u=2200, v=1700),
            ImagePoint(u=1800, v=1700),
        ],
    )

    result = solve_annotation(
        image_path=SAMPLE_IMAGE,
        annotation=annotation,
    )

    assert result.geojson["type"] == "Polygon"
    assert len(result.results) == 4
    assert result.geojson["coordinates"][0][0] == result.geojson["coordinates"][0][-1]


@pytest.mark.skipif(
    not SAMPLE_IMAGE.exists() or not SAMPLE_DEM.exists(),
    reason="DEM 或 DJI 样例图片不存在",
)
def test_solver_supports_dem_intersection() -> None:
    result = solve_image_point(
        image_path=SAMPLE_IMAGE,
        point=ImagePoint(u=2016, v=1512),
        terrain_options=TerrainOptions(dem_path=str(SAMPLE_DEM)),
    )

    assert result.terrain_model == "dem"
    assert result.terrain_source == str(SAMPLE_DEM.resolve())
    assert 100.0 <= result.ground_altitude_m <= 1000.0
