from __future__ import annotations

import math

from .errors import GeometryError, MetadataError
from .models import CameraIntrinsics, ImagePoint, Orientation

WGS84_A = 6378137.0
WGS84_F = 1 / 298.257223563
WGS84_E2 = WGS84_F * (2 - WGS84_F)


def infer_sensor_size_mm(
    image_width_px: int,
    image_height_px: int,
    focal_length_mm: float | None,
    focal_length_35mm_mm: float | None,
) -> tuple[float, float] | None:
    if focal_length_mm is None or focal_length_35mm_mm is None or focal_length_mm <= 0:
        return None

    crop_factor = focal_length_35mm_mm / focal_length_mm
    sensor_width_mm = 36.0 / crop_factor
    sensor_height_mm = sensor_width_mm * image_height_px / image_width_px
    return sensor_width_mm, sensor_height_mm


def focal_lengths_px(intrinsics: CameraIntrinsics) -> tuple[float, float]:
    sensor_width_mm = intrinsics.sensor_width_mm
    sensor_height_mm = intrinsics.sensor_height_mm

    if sensor_width_mm is None or sensor_height_mm is None:
        inferred = infer_sensor_size_mm(
            image_width_px=intrinsics.image_width_px,
            image_height_px=intrinsics.image_height_px,
            focal_length_mm=intrinsics.focal_length_mm,
            focal_length_35mm_mm=intrinsics.focal_length_35mm_mm,
        )
        if inferred is not None:
            sensor_width_mm, sensor_height_mm = inferred

    if (
        intrinsics.focal_length_mm is None
        or sensor_width_mm is None
        or sensor_height_mm is None
        or sensor_width_mm <= 0
        or sensor_height_mm <= 0
    ):
        raise MetadataError("无法解析相机内参：缺少焦距或可推导的传感器尺寸。")

    fx = intrinsics.image_width_px * intrinsics.focal_length_mm / sensor_width_mm
    fy = intrinsics.image_height_px * intrinsics.focal_length_mm / sensor_height_mm
    return fx, fy


def image_point_to_camera_ray(
    point: ImagePoint,
    intrinsics: CameraIntrinsics,
) -> tuple[float, float, float]:
    fx, fy = focal_lengths_px(intrinsics)
    cx, cy = intrinsics.principal_point

    # 相机坐标系约定：
    # x 向右，y 向下，z 沿光轴向前。
    x = (point.u - cx) / fx
    y = (point.v - cy) / fy
    z = 1.0
    length = math.sqrt(x * x + y * y + z * z)
    return (x / length, y / length, z / length)


def _dot(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(
    a: tuple[float, float, float],
    b: tuple[float, float, float],
) -> tuple[float, float, float]:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _normalize(v: tuple[float, float, float]) -> tuple[float, float, float]:
    length = math.sqrt(_dot(v, v))
    if length == 0:
        raise GeometryError("零向量无法归一化。")
    return (v[0] / length, v[1] / length, v[2] / length)


def _rotate_around_axis(
    v: tuple[float, float, float],
    axis: tuple[float, float, float],
    angle_deg: float,
) -> tuple[float, float, float]:
    angle_rad = math.radians(angle_deg)
    ux, uy, uz = _normalize(axis)
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)
    dot_uv = ux * v[0] + uy * v[1] + uz * v[2]

    return (
        v[0] * cos_a
        + (uy * v[2] - uz * v[1]) * sin_a
        + ux * dot_uv * (1 - cos_a),
        v[1] * cos_a
        + (uz * v[0] - ux * v[2]) * sin_a
        + uy * dot_uv * (1 - cos_a),
        v[2] * cos_a
        + (ux * v[1] - uy * v[0]) * sin_a
        + uz * dot_uv * (1 - cos_a),
    )


def camera_axes_in_enu(
    orientation: Orientation,
) -> tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]:
    yaw_rad = math.radians(orientation.yaw_deg)
    pitch_rad = math.radians(orientation.pitch_deg)

    # yaw 以正北为 0，顺时针为正。
    # pitch 向下为负，向上为正。
    forward = (
        math.sin(yaw_rad) * math.cos(pitch_rad),
        math.cos(yaw_rad) * math.cos(pitch_rad),
        math.sin(pitch_rad),
    )
    forward = _normalize(forward)

    # 先根据航向建立一个水平右向量，再由前向量推导图像的“下”方向。
    right = _normalize((math.cos(yaw_rad), -math.sin(yaw_rad), 0.0))
    down = _normalize(_cross(forward, right))

    if orientation.roll_deg:
        right = _rotate_around_axis(right, forward, orientation.roll_deg)
        down = _rotate_around_axis(down, forward, orientation.roll_deg)

    return _normalize(right), _normalize(down), forward


def camera_ray_to_enu(
    ray_camera: tuple[float, float, float],
    orientation: Orientation,
) -> tuple[float, float, float]:
    right, down, forward = camera_axes_in_enu(orientation)
    ray_world = (
        ray_camera[0] * right[0] + ray_camera[1] * down[0] + ray_camera[2] * forward[0],
        ray_camera[0] * right[1] + ray_camera[1] * down[1] + ray_camera[2] * forward[1],
        ray_camera[0] * right[2] + ray_camera[1] * down[2] + ray_camera[2] * forward[2],
    )
    return _normalize(ray_world)


def intersect_ray_with_ground_plane(
    ray_enu: tuple[float, float, float],
    drone_absolute_altitude_m: float,
    ground_absolute_altitude_m: float,
) -> tuple[float, float, float]:
    dz = ray_enu[2]
    if dz >= -1e-9:
        raise GeometryError("相机射线未指向地面，无法与地面平面相交。")

    ground_offset_up_m = ground_absolute_altitude_m - drone_absolute_altitude_m
    scale = ground_offset_up_m / dz
    if scale <= 0:
        raise GeometryError("地面交点位于相机后方，无法求交。")

    return (
        ray_enu[0] * scale,
        ray_enu[1] * scale,
        ray_enu[2] * scale,
    )


def geodetic_to_ecef(
    latitude_deg: float,
    longitude_deg: float,
    altitude_m: float,
) -> tuple[float, float, float]:
    lat = math.radians(latitude_deg)
    lon = math.radians(longitude_deg)
    sin_lat = math.sin(lat)
    cos_lat = math.cos(lat)
    sin_lon = math.sin(lon)
    cos_lon = math.cos(lon)

    n = WGS84_A / math.sqrt(1 - WGS84_E2 * sin_lat * sin_lat)
    x = (n + altitude_m) * cos_lat * cos_lon
    y = (n + altitude_m) * cos_lat * sin_lon
    z = (n * (1 - WGS84_E2) + altitude_m) * sin_lat
    return x, y, z


def ecef_to_geodetic(
    x: float,
    y: float,
    z: float,
) -> tuple[float, float, float]:
    b = WGS84_A * (1 - WGS84_F)
    ep = math.sqrt((WGS84_A**2 - b**2) / b**2)
    p = math.sqrt(x * x + y * y)
    th = math.atan2(WGS84_A * z, b * p)
    lon = math.atan2(y, x)
    lat = math.atan2(
        z + ep * ep * b * math.sin(th) ** 3,
        p - WGS84_E2 * WGS84_A * math.cos(th) ** 3,
    )
    n = WGS84_A / math.sqrt(1 - WGS84_E2 * math.sin(lat) ** 2)
    alt = p / math.cos(lat) - n
    return math.degrees(lat), math.degrees(lon), alt


def enu_offset_to_geodetic(
    origin_latitude_deg: float,
    origin_longitude_deg: float,
    origin_altitude_m: float,
    east_m: float,
    north_m: float,
    up_m: float,
) -> tuple[float, float, float]:
    ox, oy, oz = geodetic_to_ecef(
        origin_latitude_deg,
        origin_longitude_deg,
        origin_altitude_m,
    )

    lat = math.radians(origin_latitude_deg)
    lon = math.radians(origin_longitude_deg)
    sin_lat = math.sin(lat)
    cos_lat = math.cos(lat)
    sin_lon = math.sin(lon)
    cos_lon = math.cos(lon)

    dx = -sin_lon * east_m - sin_lat * cos_lon * north_m + cos_lat * cos_lon * up_m
    dy = cos_lon * east_m - sin_lat * sin_lon * north_m + cos_lat * sin_lon * up_m
    dz = cos_lat * north_m + sin_lat * up_m

    return ecef_to_geodetic(ox + dx, oy + dy, oz + dz)
