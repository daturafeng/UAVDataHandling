from __future__ import annotations

import math

from uav_geo.geometry import camera_ray_to_enu, image_point_to_camera_ray, intersect_ray_with_ground_plane
from uav_geo.models import CameraIntrinsics, ImagePoint, Orientation


def test_center_pixel_maps_straight_down_for_nadir_camera() -> None:
    intrinsics = CameraIntrinsics(
        image_width_px=4032,
        image_height_px=3024,
        focal_length_mm=6.72,
        focal_length_35mm_mm=24.0,
    )
    point = ImagePoint(u=2016, v=1512)
    orientation = Orientation(yaw_deg=0.0, pitch_deg=-90.0, roll_deg=0.0)

    ray_camera = image_point_to_camera_ray(point, intrinsics)
    ray_enu = camera_ray_to_enu(ray_camera, orientation)
    intersection = intersect_ray_with_ground_plane(
        ray_enu=ray_enu,
        drone_absolute_altitude_m=500.0,
        ground_absolute_altitude_m=400.0,
    )

    assert math.isclose(intersection[0], 0.0, abs_tol=1e-6)
    assert math.isclose(intersection[1], 0.0, abs_tol=1e-6)
    assert math.isclose(intersection[2], -100.0, abs_tol=1e-6)


def test_right_side_pixel_moves_east_for_nadir_camera() -> None:
    intrinsics = CameraIntrinsics(
        image_width_px=4032,
        image_height_px=3024,
        focal_length_mm=6.72,
        focal_length_35mm_mm=24.0,
    )
    point = ImagePoint(u=4032, v=1512)
    orientation = Orientation(yaw_deg=0.0, pitch_deg=-90.0, roll_deg=0.0)

    ray_camera = image_point_to_camera_ray(point, intrinsics)
    ray_enu = camera_ray_to_enu(ray_camera, orientation)
    intersection = intersect_ray_with_ground_plane(
        ray_enu=ray_enu,
        drone_absolute_altitude_m=500.0,
        ground_absolute_altitude_m=400.0,
    )

    assert intersection[0] > 0.0
    assert math.isclose(intersection[1], 0.0, abs_tol=1e-6)


def test_bottom_pixel_moves_south_for_nadir_camera() -> None:
    intrinsics = CameraIntrinsics(
        image_width_px=4032,
        image_height_px=3024,
        focal_length_mm=6.72,
        focal_length_35mm_mm=24.0,
    )
    point = ImagePoint(u=2016, v=3024)
    orientation = Orientation(yaw_deg=0.0, pitch_deg=-90.0, roll_deg=0.0)

    ray_camera = image_point_to_camera_ray(point, intrinsics)
    ray_enu = camera_ray_to_enu(ray_camera, orientation)
    intersection = intersect_ray_with_ground_plane(
        ray_enu=ray_enu,
        drone_absolute_altitude_m=500.0,
        ground_absolute_altitude_m=400.0,
    )

    assert intersection[1] < 0.0
    assert math.isclose(intersection[0], 0.0, abs_tol=1e-6)
