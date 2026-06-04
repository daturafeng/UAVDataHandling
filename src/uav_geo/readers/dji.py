from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import math
import re
import xml.etree.ElementTree as ET

from PIL import ExifTags, Image

from ..camera_profiles import match_dji_camera_profile
from ..errors import MetadataError
from ..geometry import infer_sensor_size_mm
from ..models import (
    CameraIntrinsics,
    CaptureOverrides,
    DroneState,
    Orientation,
    ResolvedCapture,
)

DJI_NS = "http://www.dji.com/drone-dji/1.0/"
TIFF_NS = "http://ns.adobe.com/tiff/1.0/"
EXIF_NS = "http://ns.adobe.com/exif/1.0/"


class DjiImageReader:
    def read(
        self,
        image_path: str | Path,
        overrides: CaptureOverrides | None = None,
    ) -> ResolvedCapture:
        image_path = Path(image_path)
        if not image_path.exists():
            raise FileNotFoundError(image_path)

        metadata_sources: dict[str, str] = {}
        raw_metadata: dict[str, object] = {}

        with Image.open(image_path) as image:
            image_width_px, image_height_px = image.size
            exif = image.getexif()
            exif_fields = self._extract_exif_fields(exif)

        raw_metadata["exif"] = exif_fields

        xmp_fields = self._extract_xmp_fields_from_jpeg(image_path)
        raw_metadata["xmp"] = xmp_fields

        aux_fields = self._extract_aux_fields(image_path.with_suffix(image_path.suffix + ".aux.xml"))
        raw_metadata["aux"] = aux_fields

        intrinsics = self._build_intrinsics(
            image_width_px=image_width_px,
            image_height_px=image_height_px,
            xmp_fields=xmp_fields,
            exif_fields=exif_fields,
            aux_fields=aux_fields,
            overrides=overrides,
            metadata_sources=metadata_sources,
        )

        drone_state = self._build_drone_state(
            xmp_fields=xmp_fields,
            exif_fields=exif_fields,
            aux_fields=aux_fields,
            overrides=overrides,
            metadata_sources=metadata_sources,
        )

        return ResolvedCapture(
            image_path=str(image_path),
            intrinsics=intrinsics,
            drone_state=drone_state,
            metadata_sources=metadata_sources,
            raw_metadata=raw_metadata,
        )

    def _build_intrinsics(
        self,
        *,
        image_width_px: int,
        image_height_px: int,
        xmp_fields: dict[str, str],
        exif_fields: dict[str, object],
        aux_fields: dict[str, str],
        overrides: CaptureOverrides | None,
        metadata_sources: dict[str, str],
    ) -> CameraIntrinsics:
        digital_zoom_ratio = self._coalesce_float(
            metadata_sources,
            "digital_zoom_ratio",
            [
                ("exif", exif_fields.get("DigitalZoomRatio")),
                ("aux", self._parse_parenthesized_float(aux_fields.get("EXIF_DigitalZoomRatio"))),
            ],
        )
        if digital_zoom_ratio is None or digital_zoom_ratio <= 0:
            digital_zoom_ratio = 1.0

        focal_length_mm = self._coalesce_float(
            metadata_sources,
            "focal_length_mm",
            [
                ("override", getattr(overrides, "focal_length_mm", None)),
                ("exif", exif_fields.get("FocalLength")),
                ("aux", self._parse_parenthesized_float(aux_fields.get("EXIF_FocalLength"))),
            ],
        )
        focal_length_35mm_mm = self._coalesce_float(
            metadata_sources,
            "focal_length_35mm_mm",
            [
                ("override", getattr(overrides, "focal_length_35mm_mm", None)),
                ("exif", exif_fields.get("FocalLengthIn35mmFilm")),
                ("aux", self._parse_parenthesized_float(aux_fields.get("EXIF_FocalLengthIn35mmFilm"))),
            ],
        )

        if focal_length_mm is not None and digital_zoom_ratio > 1.0:
            focal_length_mm *= digital_zoom_ratio
            metadata_sources["focal_length_mm"] = (
                f"{metadata_sources.get('focal_length_mm', 'unknown')}+digital_zoom"
            )
        if focal_length_35mm_mm is not None and digital_zoom_ratio > 1.0:
            focal_length_35mm_mm *= digital_zoom_ratio
            metadata_sources["focal_length_35mm_mm"] = (
                f"{metadata_sources.get('focal_length_35mm_mm', 'unknown')}+digital_zoom"
            )

        model_name = self._coalesce_str(
            metadata_sources,
            "camera_model",
            [
                ("xmp", xmp_fields.get("tiff:Model")),
                ("exif", exif_fields.get("Model")),
                ("aux", aux_fields.get("EXIF_Model")),
                ("aux", aux_fields.get("DNG_UniqueCameraModel")),
            ],
        )
        image_source = self._coalesce_str(
            metadata_sources,
            "image_source",
            [("xmp", xmp_fields.get("drone-dji:ImageSource"))],
        )

        profile = match_dji_camera_profile(
            model_name=model_name,
            image_source=image_source,
        )

        sensor_width_mm = self._coalesce_float(
            metadata_sources,
            "sensor_width_mm",
            [("override", getattr(overrides, "sensor_width_mm", None))],
        )
        sensor_height_mm = self._coalesce_float(
            metadata_sources,
            "sensor_height_mm",
            [("override", getattr(overrides, "sensor_height_mm", None))],
        )

        if (sensor_width_mm is None or sensor_height_mm is None) and profile is not None:
            sensor_width_mm = profile.sensor_width_mm
            sensor_height_mm = profile.sensor_height_mm
            metadata_sources.setdefault("sensor_width_mm", "camera_profile")
            metadata_sources.setdefault("sensor_height_mm", "camera_profile")

        if sensor_width_mm is None or sensor_height_mm is None:
            inferred = infer_sensor_size_mm(
                image_width_px=image_width_px,
                image_height_px=image_height_px,
                focal_length_mm=focal_length_mm,
                focal_length_35mm_mm=focal_length_35mm_mm,
            )
            if inferred is not None:
                sensor_width_mm, sensor_height_mm = inferred
                metadata_sources.setdefault(
                    "sensor_width_mm",
                    "inferred_from_focal_length_35mm_mm",
                )
                metadata_sources.setdefault(
                    "sensor_height_mm",
                    "inferred_from_focal_length_35mm_mm",
                )

        principal_point_x_px = self._coalesce_float(
            metadata_sources,
            "principal_point_x_px",
            [("override", getattr(overrides, "principal_point_x_px", None))],
        )
        principal_point_y_px = self._coalesce_float(
            metadata_sources,
            "principal_point_y_px",
            [("override", getattr(overrides, "principal_point_y_px", None))],
        )

        return CameraIntrinsics(
            image_width_px=image_width_px,
            image_height_px=image_height_px,
            focal_length_mm=focal_length_mm,
            focal_length_35mm_mm=focal_length_35mm_mm,
            sensor_width_mm=sensor_width_mm,
            sensor_height_mm=sensor_height_mm,
            principal_point_x_px=principal_point_x_px,
            principal_point_y_px=principal_point_y_px,
        )

    def _build_drone_state(
        self,
        *,
        xmp_fields: dict[str, str],
        exif_fields: dict[str, object],
        aux_fields: dict[str, str],
        overrides: CaptureOverrides | None,
        metadata_sources: dict[str, str],
    ) -> DroneState:
        latitude_deg = self._coalesce_float(
            metadata_sources,
            "latitude_deg",
            [
                ("override", getattr(overrides, "latitude_deg", None)),
                ("xmp", xmp_fields.get("drone-dji:GpsLatitude")),
                ("exif", exif_fields.get("GPSLatitudeDecimal")),
                ("aux", self._parse_aux_gps_dms(aux_fields.get("EXIF_GPSLatitude"), aux_fields.get("EXIF_GPSLatitudeRef"))),
            ],
        )
        longitude_deg = self._coalesce_float(
            metadata_sources,
            "longitude_deg",
            [
                ("override", getattr(overrides, "longitude_deg", None)),
                ("xmp", xmp_fields.get("drone-dji:GpsLongitude")),
                ("exif", exif_fields.get("GPSLongitudeDecimal")),
                ("aux", self._parse_aux_gps_dms(aux_fields.get("EXIF_GPSLongitude"), aux_fields.get("EXIF_GPSLongitudeRef"))),
            ],
        )
        absolute_altitude_m = self._coalesce_float(
            metadata_sources,
            "absolute_altitude_m",
            [
                ("override", getattr(overrides, "absolute_altitude_m", None)),
                ("xmp", xmp_fields.get("drone-dji:AbsoluteAltitude")),
                ("exif", exif_fields.get("GPSAltitude")),
                ("aux", self._parse_parenthesized_float(aux_fields.get("EXIF_GPSAltitude"))),
            ],
        )

        if latitude_deg is None or longitude_deg is None or absolute_altitude_m is None:
            raise MetadataError("无法解析无人机经纬度或绝对高度。")

        relative_altitude_m = self._coalesce_float(
            metadata_sources,
            "relative_altitude_m",
            [
                ("override", getattr(overrides, "relative_altitude_m", None)),
                ("xmp", xmp_fields.get("drone-dji:RelativeAltitude")),
            ],
        )
        gps_status = self._coalesce_str(
            metadata_sources,
            "gps_status",
            [("xmp", xmp_fields.get("drone-dji:GpsStatus"))],
        )
        altitude_type = self._coalesce_str(
            metadata_sources,
            "altitude_type",
            [("xmp", xmp_fields.get("drone-dji:AltitudeType"))],
        )

        camera_orientation = self._build_orientation(
            metadata_sources=metadata_sources,
            prefix="camera",
            yaw_candidates=[
                ("override", getattr(overrides, "gimbal_yaw_deg", None)),
                ("xmp", xmp_fields.get("drone-dji:GimbalYawDegree")),
            ],
            pitch_candidates=[
                ("override", getattr(overrides, "gimbal_pitch_deg", None)),
                ("xmp", xmp_fields.get("drone-dji:GimbalPitchDegree")),
            ],
            roll_candidates=[
                ("override", getattr(overrides, "gimbal_roll_deg", None)),
                ("xmp", xmp_fields.get("drone-dji:GimbalRollDegree")),
            ],
        )

        flight_orientation = self._build_orientation(
            metadata_sources=metadata_sources,
            prefix="flight",
            yaw_candidates=[
                ("override", getattr(overrides, "flight_yaw_deg", None)),
                ("xmp", xmp_fields.get("drone-dji:FlightYawDegree")),
            ],
            pitch_candidates=[
                ("override", getattr(overrides, "flight_pitch_deg", None)),
                ("xmp", xmp_fields.get("drone-dji:FlightPitchDegree")),
            ],
            roll_candidates=[
                ("override", getattr(overrides, "flight_roll_deg", None)),
                ("xmp", xmp_fields.get("drone-dji:FlightRollDegree")),
            ],
        )

        if camera_orientation is None and flight_orientation is not None:
            camera_orientation = replace(flight_orientation)

        if camera_orientation is not None:
            camera_orientation = self._normalize_camera_orientation(camera_orientation)
            metadata_sources.setdefault("camera_orientation_mode", "normalized_display_orientation")

        if camera_orientation is None:
            raise MetadataError("无法解析相机姿态：缺少云台或飞行姿态角。")

        return DroneState(
            latitude_deg=latitude_deg,
            longitude_deg=longitude_deg,
            absolute_altitude_m=absolute_altitude_m,
            relative_altitude_m=relative_altitude_m,
            flight_orientation=flight_orientation,
            camera_orientation=camera_orientation,
            gps_status=gps_status,
            altitude_type=altitude_type,
            rtk_std_lat_m=self._coalesce_float(
                metadata_sources,
                "rtk_std_lat_m",
                [("xmp", xmp_fields.get("drone-dji:RtkStdLat"))],
            ),
            rtk_std_lon_m=self._coalesce_float(
                metadata_sources,
                "rtk_std_lon_m",
                [("xmp", xmp_fields.get("drone-dji:RtkStdLon"))],
            ),
            rtk_std_hgt_m=self._coalesce_float(
                metadata_sources,
                "rtk_std_hgt_m",
                [("xmp", xmp_fields.get("drone-dji:RtkStdHgt"))],
            ),
            lrf_target_latitude_deg=self._coalesce_float(
                metadata_sources,
                "lrf_target_latitude_deg",
                [("xmp", xmp_fields.get("drone-dji:LRFTargetLat"))],
            ),
            lrf_target_longitude_deg=self._coalesce_float(
                metadata_sources,
                "lrf_target_longitude_deg",
                [("xmp", xmp_fields.get("drone-dji:LRFTargetLon"))],
            ),
            lrf_target_altitude_m=self._coalesce_float(
                metadata_sources,
                "lrf_target_altitude_m",
                [("xmp", xmp_fields.get("drone-dji:LRFTargetAbsAlt"))],
            ),
            lrf_target_distance_m=self._coalesce_float(
                metadata_sources,
                "lrf_target_distance_m",
                [("xmp", xmp_fields.get("drone-dji:LRFTargetDistance"))],
            ),
        )

    def _build_orientation(
        self,
        *,
        metadata_sources: dict[str, str],
        prefix: str,
        yaw_candidates: list[tuple[str, object]],
        pitch_candidates: list[tuple[str, object]],
        roll_candidates: list[tuple[str, object]],
    ) -> Orientation | None:
        yaw = self._coalesce_float(metadata_sources, f"{prefix}_yaw_deg", yaw_candidates)
        pitch = self._coalesce_float(metadata_sources, f"{prefix}_pitch_deg", pitch_candidates)
        roll = self._coalesce_float(metadata_sources, f"{prefix}_roll_deg", roll_candidates)
        if yaw is None or pitch is None:
            return None
        return Orientation(yaw_deg=yaw, pitch_deg=pitch, roll_deg=roll or 0.0)

    def _normalize_camera_orientation(self, orientation: Orientation) -> Orientation:
        yaw_deg = orientation.yaw_deg
        pitch_deg = orientation.pitch_deg
        roll_deg = orientation.roll_deg

        # DJI 可见光图像经常已经是“正立图像”，但云台原始姿态会记录 roll=180。
        # 若直接把 roll=180 用到像素投影，会让非中心点出现镜像偏差。
        if abs(abs(roll_deg) - 180.0) <= 5.0:
            yaw_deg = self._normalize_angle_deg(yaw_deg + 180.0)
            roll_deg = 0.0

        return Orientation(
            yaw_deg=yaw_deg,
            pitch_deg=pitch_deg,
            roll_deg=roll_deg,
        )

    def _normalize_angle_deg(self, angle_deg: float) -> float:
        normalized = math.fmod(angle_deg, 360.0)
        if normalized > 180.0:
            normalized -= 360.0
        if normalized <= -180.0:
            normalized += 360.0
        return normalized

    def _extract_exif_fields(self, exif) -> dict[str, object]:
        fields: dict[str, object] = {}
        for tag_id, value in exif.items():
            fields[ExifTags.TAGS.get(tag_id, str(tag_id))] = value

        try:
            exif_ifd = exif.get_ifd(ExifTags.IFD.Exif)
        except Exception:
            exif_ifd = {}
        for tag_id, value in exif_ifd.items():
            tag_name = ExifTags.TAGS.get(tag_id, str(tag_id))
            fields[tag_name] = value

        gps_tag_id = next(
            (tag_id for tag_id, name in ExifTags.TAGS.items() if name == "GPSInfo"),
            34853,
        )
        gps_info = {}
        try:
            gps_info = exif.get_ifd(gps_tag_id)
        except Exception:
            gps_info = {}

        gps_fields = {}
        for key, value in gps_info.items():
            gps_fields[ExifTags.GPSTAGS.get(key, str(key))] = value

        if gps_fields:
            fields["GPSInfoResolved"] = gps_fields
            latitude = self._gps_to_decimal(
                gps_fields.get("GPSLatitude"),
                gps_fields.get("GPSLatitudeRef"),
            )
            longitude = self._gps_to_decimal(
                gps_fields.get("GPSLongitude"),
                gps_fields.get("GPSLongitudeRef"),
            )
            altitude = self._safe_float(gps_fields.get("GPSAltitude"))
            if latitude is not None:
                fields["GPSLatitudeDecimal"] = latitude
            if longitude is not None:
                fields["GPSLongitudeDecimal"] = longitude
            if altitude is not None:
                fields["GPSAltitude"] = altitude

        return fields

    def _extract_xmp_fields_from_jpeg(self, image_path: Path) -> dict[str, str]:
        data = image_path.read_bytes()
        start = data.find(b"<x:xmpmeta")
        end = data.find(b"</x:xmpmeta>")
        if start == -1 or end == -1:
            return {}
        packet = data[start : end + len(b"</x:xmpmeta>")].decode("utf-8", errors="ignore")
        return self._parse_xmp_packet(packet)

    def _extract_aux_fields(self, aux_path: Path) -> dict[str, str]:
        if not aux_path.exists():
            return {}
        try:
            tree = ET.parse(aux_path)
        except ET.ParseError:
            return {}

        fields: dict[str, str] = {}
        for mdi in tree.findall(".//MDI"):
            key = mdi.attrib.get("key")
            if key:
                fields[key] = (mdi.text or "").strip()
        return fields

    def _parse_xmp_packet(self, packet: str) -> dict[str, str]:
        try:
            root = ET.fromstring(packet)
        except ET.ParseError:
            return {}

        fields: dict[str, str] = {}
        for element in root.iter():
            for attr_name, attr_value in element.attrib.items():
                if not attr_value:
                    continue
                if attr_name.startswith("{"):
                    namespace, local_name = attr_name[1:].split("}", 1)
                    if namespace == DJI_NS:
                        fields[f"drone-dji:{local_name}"] = attr_value
                    elif namespace == TIFF_NS:
                        fields[f"tiff:{local_name}"] = attr_value
                    elif namespace == EXIF_NS:
                        fields[f"exif:{local_name}"] = attr_value
                else:
                    fields[attr_name] = attr_value
        return fields

    def _gps_to_decimal(self, dms, ref: object) -> float | None:
        if not dms or len(dms) != 3:
            return None
        degrees = self._safe_float(dms[0])
        minutes = self._safe_float(dms[1])
        seconds = self._safe_float(dms[2])
        if degrees is None or minutes is None or seconds is None:
            return None
        value = degrees + minutes / 60.0 + seconds / 3600.0
        if ref in ("S", "W"):
            value *= -1
        return value

    def _safe_float(self, value: object) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _parse_parenthesized_float(self, value: str | None) -> float | None:
        if not value:
            return None
        matches = re.findall(r"[-+]?\d+(?:\.\d+)?", value)
        if not matches:
            return None
        try:
            return float(matches[0])
        except ValueError:
            return None

    def _parse_aux_gps_dms(self, value: str | None, ref: str | None) -> float | None:
        if not value:
            return None
        matches = re.findall(r"[-+]?\d+(?:\.\d+)?", value)
        if len(matches) < 3:
            return None
        degrees, minutes, seconds = (float(matches[0]), float(matches[1]), float(matches[2]))
        decimal = degrees + minutes / 60.0 + seconds / 3600.0
        if ref in ("S", "W"):
            decimal *= -1
        return decimal

    def _coalesce_float(
        self,
        metadata_sources: dict[str, str],
        field_name: str,
        candidates: list[tuple[str, object]],
    ) -> float | None:
        for source_name, value in candidates:
            if value is None:
                continue
            try:
                resolved = float(value)
            except (TypeError, ValueError):
                continue
            metadata_sources.setdefault(field_name, source_name)
            return resolved
        return None

    def _coalesce_str(
        self,
        metadata_sources: dict[str, str],
        field_name: str,
        candidates: list[tuple[str, object]],
    ) -> str | None:
        for source_name, value in candidates:
            if value is None:
                continue
            resolved = str(value).strip()
            if not resolved:
                continue
            metadata_sources.setdefault(field_name, source_name)
            return resolved
        return None
