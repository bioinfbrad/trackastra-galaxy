from __future__ import annotations

import argparse

from .trackastra_galaxy import (
    default_tracking_options,
    segment_and_track_entry,
    track_entry,
)


def parse_coords(coord_string: str) -> list[int]:
    """
    Parse comma- or space-separated coordinates into a list of ints.
    """
    if isinstance(coord_string, str):
        coords = coord_string.replace(",", " ").split()
        return [int(c) for c in coords if c.strip()]
    return [int(coord_string)] if coord_string else []


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="trackastra-galaxy",
        description="Trackastra: track cell instances in time-lapse imaging",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Segment and track from a zarr dataset
  trackastra-galaxy segment_and_track \\
    --zarr-path /path/to/data.zarr \\
    --result-path /path/to/result_ctc

  # Track with pre-existing segmentation
  trackastra-galaxy track \\
    --zarr-path /path/to/data.zarr \\
    --result-path /path/to/result_ctc
""",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands", required=True)

    seg_track_parser = subparsers.add_parser(
        "segment_and_track",
        help="Segment cells and perform tracking",
    )
    seg_track_parser.add_argument(
        "--zarr-path",
        required=True,
        help="Path to the zarr dataset (URL, s3://, or local path)",
    )
    seg_track_parser.add_argument(
        "--scale-level",
        type=int,
        default=0,
        help="Pyramid scale level to use (default: 0 (highest resolution))",
    )
    seg_track_parser.add_argument(
        "--raw-channel-coords",
        type=str,
        default="0",
        help="Coordinates to select raw data, non-tzyx dimensions (comma/space-separated, default: 0)",
    )
    seg_track_parser.add_argument(
        "--result-path",
        required=True,
        help="Output directory for Trackastra/CTC results",
    )
    seg_track_parser.add_argument(
        "--downscale-x",
        type=float,
        default=1.0,
        help="Downscale factor for X axis (default: 1.0)",
    )
    seg_track_parser.add_argument(
        "--downscale-y",
        type=float,
        default=1.0,
        help="Downscale factor for Y axis (default: 1.0)",
    )
    seg_track_parser.add_argument(
        "--downscale-z",
        type=float,
        default=1.0,
        help="Downscale factor for Z axis (default: 1.0)",
    )
    seg_track_parser.add_argument(
        "--start-tp",
        type=int,
        default=0,
        help="Starting time point (default: 0)",
    )
    seg_track_parser.add_argument(
        "--end-tp",
        type=int,
        default=-1,
        help="Ending time point (default: -1 (the end of the time-lapse))",
    )
    seg_track_parser.add_argument(
        "--segmentation-model",
        type=str,
        default="cyto3",
        choices=["cyto3", "cyto2", "nuclei"],
        help="Cellpose v3 segmentation model to use (default: cyto3)",
    )
    seg_track_parser.add_argument(
        "--objects-diameter-px",
        type=int,
        default=25,
        help="Expected object diameter in pixels for Cellpose v3 (default: 25)",
    )
    seg_track_parser.add_argument(
        "--tracking-model",
        type=str,
        default="ctc",
        help="Trackastra tracking model to use (default: ctc)",
    )

    track_parser = subparsers.add_parser(
        "track",
        help="Perform tracking on pre-segmented data",
    )
    track_parser.add_argument(
        "--zarr-path",
        required=True,
        help="Path to the zarr dataset (URL, s3://, or local path)",
    )
    track_parser.add_argument(
        "--scale-level",
        type=int,
        default=0,
        help="Pyramid scale level to use (default: 0 (highest resolution))",
    )
    track_parser.add_argument(
        "--raw-channel-coords",
        type=str,
        default="0",
        help="Coordinates to select raw data, non-tzyx dimensions (comma/space-separated, default: 0)",
    )
    track_parser.add_argument(
        "--seg-channel-coords",
        type=str,
        default="1",
        help="Coordinates to select segmentation, non-tzyx dimensions (comma/space-separated, default: 1)",
    )
    track_parser.add_argument(
        "--result-path",
        required=True,
        help="Output directory for Trackastra/CTC results",
    )
    track_parser.add_argument(
        "--downscale-x",
        type=float,
        default=1.0,
        help="Downscale factor for X axis (default: 1.0)",
    )
    track_parser.add_argument(
        "--downscale-y",
        type=float,
        default=1.0,
        help="Downscale factor for Y axis (default: 1.0)",
    )
    track_parser.add_argument(
        "--downscale-z",
        type=float,
        default=1.0,
        help="Downscale factor for Z axis (default: 1.0)",
    )
    track_parser.add_argument(
        "--start-tp",
        type=int,
        default=0,
        help="Starting time point (default: 0)",
    )
    track_parser.add_argument(
        "--end-tp",
        type=int,
        default=-1,
        help="Ending time point (default: -1 (the end of the time-lapse))",
    )
    track_parser.add_argument(
        "--tracking-model",
        type=str,
        default="ctc",
        help="Trackastra tracking model to use (default: ctc)",
    )

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    tracking_options = default_tracking_options.copy()
    tracking_options["downscale_factor_x"] = args.downscale_x
    tracking_options["downscale_factor_y"] = args.downscale_y
    tracking_options["downscale_factor_z"] = args.downscale_z
    tracking_options["start_from_tp"] = args.start_tp
    tracking_options["end_at_tp"] = args.end_tp
    tracking_options["tracking_model"] = args.tracking_model

    if args.command == "segment_and_track":
        tracking_options["segmentation_model"] = args.segmentation_model
        tracking_options["objects_diameter_px"] = args.objects_diameter_px

        raw_channel_coords = parse_coords(args.raw_channel_coords)
        segment_and_track_entry(
            zarr_path=args.zarr_path,
            scale_level=args.scale_level,
            list_of_coords_for_non_tzyx_dims_to_reach_raw_channel=raw_channel_coords,
            result_path=args.result_path,
            tracking_options=tracking_options,
        )
        print("Segmentation and Tracking completed successfully")
        return 0

    if args.command == "track":
        raw_ch_coords = parse_coords(args.raw_channel_coords)
        seg_ch_coords = parse_coords(args.seg_channel_coords)
        track_entry(
            zarr_path=args.zarr_path,
            scale_level=args.scale_level,
            list_of_coords_for_non_tzyx_dims_to_reach_raw_channel=raw_ch_coords,
            list_of_coords_for_non_tzyx_dims_to_reach_seg_channel=seg_ch_coords,
            result_path=args.result_path,
            tracking_options=tracking_options,
        )
        print("Tracking completed successfully")
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
