from __future__ import annotations

import argparse
import json
from pathlib import Path

from .models import CaptureOverrides, ImageAnnotation, ImagePoint, TerrainOptions
from .server import DEFAULT_DEM_PATH, DEFAULT_DEM_ROOT, DEFAULT_TDT_TOKEN, run_server
from .service import solve_annotation, solve_image_point


def build_common_override_kwargs(args: argparse.Namespace) -> dict[str, float | None]:
    return {
        "latitude_deg": args.latitude_deg,
        "longitude_deg": args.longitude_deg,
        "absolute_altitude_m": args.absolute_altitude_m,
        "relative_altitude_m": args.relative_altitude_m,
        "ground_absolute_altitude_m": args.ground_absolute_altitude_m,
        "gimbal_yaw_deg": args.gimbal_yaw_deg,
        "gimbal_pitch_deg": args.gimbal_pitch_deg,
        "gimbal_roll_deg": args.gimbal_roll_deg,
        "flight_yaw_deg": args.flight_yaw_deg,
        "flight_pitch_deg": args.flight_pitch_deg,
        "flight_roll_deg": args.flight_roll_deg,
        "focal_length_mm": args.focal_length_mm,
        "focal_length_35mm_mm": args.focal_length_35mm_mm,
        "sensor_width_mm": args.sensor_width_mm,
        "sensor_height_mm": args.sensor_height_mm,
        "principal_point_x_px": args.principal_point_x_px,
        "principal_point_y_px": args.principal_point_y_px,
    }


def add_override_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--latitude", dest="latitude_deg", type=float)
    parser.add_argument("--longitude", dest="longitude_deg", type=float)
    parser.add_argument("--absolute-altitude", dest="absolute_altitude_m", type=float)
    parser.add_argument("--relative-altitude", dest="relative_altitude_m", type=float)
    parser.add_argument("--ground-absolute-altitude", dest="ground_absolute_altitude_m", type=float)
    parser.add_argument("--gimbal-yaw", dest="gimbal_yaw_deg", type=float)
    parser.add_argument("--gimbal-pitch", dest="gimbal_pitch_deg", type=float)
    parser.add_argument("--gimbal-roll", dest="gimbal_roll_deg", type=float)
    parser.add_argument("--flight-yaw", dest="flight_yaw_deg", type=float)
    parser.add_argument("--flight-pitch", dest="flight_pitch_deg", type=float)
    parser.add_argument("--flight-roll", dest="flight_roll_deg", type=float)
    parser.add_argument("--focal-length-mm", dest="focal_length_mm", type=float)
    parser.add_argument("--focal-length-35mm", dest="focal_length_35mm_mm", type=float)
    parser.add_argument("--sensor-width-mm", dest="sensor_width_mm", type=float)
    parser.add_argument("--sensor-height-mm", dest="sensor_height_mm", type=float)
    parser.add_argument("--principal-point-x", dest="principal_point_x_px", type=float)
    parser.add_argument("--principal-point-y", dest="principal_point_y_px", type=float)


def add_terrain_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--dem-path", dest="dem_path")
    parser.add_argument("--dem-step", dest="ray_step_m", type=float, default=10.0)
    parser.add_argument(
        "--dem-binary-iterations",
        dest="binary_search_iterations",
        type=int,
        default=24,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="UAV image to WGS84 coordinate tools.",
    )
    subparsers = parser.add_subparsers(dest="command")

    point_parser = subparsers.add_parser(
        "point",
        help="Solve one image pixel to WGS84.",
    )
    point_parser.add_argument("image_path")
    point_parser.add_argument("u", type=float)
    point_parser.add_argument("v", type=float)
    add_override_arguments(point_parser)
    add_terrain_arguments(point_parser)

    batch_parser = subparsers.add_parser(
        "batch",
        help="Solve point/polyline/polygon annotations in one image.",
    )
    batch_parser.add_argument("image_path")
    batch_group = batch_parser.add_mutually_exclusive_group(required=True)
    batch_group.add_argument("--annotation-json", dest="annotation_json")
    batch_group.add_argument("--annotation-file", dest="annotation_file")
    add_override_arguments(batch_parser)
    add_terrain_arguments(batch_parser)

    serve_parser = subparsers.add_parser(
        "serve",
        help="Start the local annotation and Cesium visualization page.",
    )
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8765)
    serve_parser.add_argument(
        "--sample-root",
        default=r"G:\DJIImage\drone_images",
    )
    serve_parser.add_argument("--tdt-token", default=DEFAULT_TDT_TOKEN)
    serve_parser.add_argument("--dem-root", default=str(DEFAULT_DEM_ROOT))
    serve_parser.add_argument("--dem-path", default=str(DEFAULT_DEM_PATH))

    return parser


def parse_annotation_payload(raw_text: str) -> ImageAnnotation:
    payload = json.loads(raw_text)
    vertices = [
        ImagePoint(u=float(item["u"]), v=float(item["v"]))
        for item in payload["vertices"]
    ]
    return ImageAnnotation(
        annotation_id=str(payload.get("annotation_id", "annotation-1")),
        kind=payload["kind"],
        label=payload.get("label"),
        vertices=vertices,
    )


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        import sys

        argv = sys.argv[1:]

    # Backward compatibility:
    # `python UAVDataHandling.py image.jpg 100 200`
    if argv and argv[0] not in {"point", "batch", "serve", "-h", "--help"}:
        argv = ["point", *argv]

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "serve":
        run_server(
            host=args.host,
            port=args.port,
            sample_root=Path(args.sample_root),
            default_tdt_token=args.tdt_token,
            default_dem_root=Path(args.dem_root),
            default_dem_path=Path(args.dem_path) if args.dem_path else None,
        )
        return 0

    overrides = CaptureOverrides(**build_common_override_kwargs(args))
    terrain_options = TerrainOptions(
        dem_path=args.dem_path,
        ray_step_m=args.ray_step_m,
        binary_search_iterations=args.binary_search_iterations,
    )

    if args.command == "point":
        result = solve_image_point(
            image_path=args.image_path,
            point=ImagePoint(u=args.u, v=args.v),
            overrides=overrides,
            terrain_options=terrain_options,
        )
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return 0

    if args.command == "batch":
        raw_text = (
            args.annotation_json
            if args.annotation_json is not None
            else Path(args.annotation_file).read_text(encoding="utf-8")
        )
        annotation = parse_annotation_payload(raw_text)
        result = solve_annotation(
            image_path=args.image_path,
            annotation=annotation,
            overrides=overrides,
            terrain_options=terrain_options,
        )
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
