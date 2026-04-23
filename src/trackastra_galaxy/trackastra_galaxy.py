from __future__ import annotations

import sys
from math import ceil
from pathlib import Path
from typing import Any

import numpy as np


default_tracking_options = {
    "downscale_factor_x": 1.0,
    "downscale_factor_y": 1.0,
    "downscale_factor_z": 1.0,
    "start_from_tp": 0,
    "end_at_tp": -1,
    "segmentation_model": "cyto3",
    "objects_diameter_px": 25,
    "tracking_model": "ctc",
}


def flag_error_and_quit(error_msg: str) -> None:
    print(f"ERROR: {error_msg}", file=sys.stderr)
    sys.exit(1)


def obtain_lazy_view_from_the_zarr_path(
    input_path: str,
    scale_level: int,
    list_of_coords_for_non_tzyx_dims: list[int],
):
    """
    Return a lazy t,z,y,x view from an OME-Zarr dataset.

    scale_level=0 means the finest/highest spatial resolution.
    """
    from ome_zarr.io import parse_url
    from ome_zarr.reader import Reader

    # image_nodes may include images, labels etc
    image_nodes = list(Reader(parse_url(input_path))())
    if not image_nodes:
        flag_error_and_quit(f"No readable OME-Zarr image nodes found in: {input_path}")

    # first node is often the image pixel data
    image_index = 0
    image_node = image_nodes[image_index]

    if scale_level < 0 or scale_level >= len(image_node.data):
        flag_error_and_quit(
            "Scale index negative or larger than number(-1) of available resolutions "
            "that the OME-Zarr dataset offers"
        )

    zarr_image = image_node.data[scale_level]

    axes_known: list[int] = []
    labels_known: list[str] = []
    axes_unknown: list[int] = []

    for curr_axis_idx, axis in enumerate(image_node.metadata["axes"]):
        dim_name = axis["name"]
        if dim_name not in "tzyx":
            # dimension to be "moved" to the front
            axes_unknown.append(curr_axis_idx)
        else:
            axes_known.append(curr_axis_idx)
            labels_known.append(dim_name)

    if len(axes_unknown) != len(list_of_coords_for_non_tzyx_dims):
        flag_error_and_quit(
            f"Found {len(axes_unknown)} non_tzyx dimensions but different number "
            f"({len(list_of_coords_for_non_tzyx_dims)}) of values for them"
        )

    if "t" not in labels_known:
        flag_error_and_quit(
            f"Time axis is missing among the discovered known axes ({labels_known}), "
            "can't track single static image"
        )

    axes_permutation = [*axes_unknown, *axes_known]
    # NB: TODO, would be great to check the order in the 'axes_known' and possibly adjust it...
    view = zarr_image.transpose(axes_permutation)[*list_of_coords_for_non_tzyx_dims]

    if "z" not in labels_known:
        # assumed tyx, inject singleton z
        view = np.reshape(view, (view.shape[0], 1, view.shape[1], view.shape[2]))

    if len(view.shape) != 4:
        flag_error_and_quit(
            "After fixing non_tzyx dimensions, tzyx (4) dimensions were supposed to be "
            f"left; instead {len(view.shape)} dimensions are available"
        )

    return view


def resize(
    view_into_raw_data,  # a numpy-like array
    view_into_seg_data,  # a numpy-like array
    tracking_options: dict[str, Any] = default_tracking_options,
):
    from skimage.transform import resize

    print(
        f"provided input data: {view_into_raw_data.shape[0]} images of shape "
        f"{view_into_raw_data.shape[1:]} pixels"
    )

    # figure out the (possibly) downscaled spatial size (zyx axes)
    down_scale_factors = [
        tracking_options.get("downscale_factor_z", 1),
        tracking_options.get("downscale_factor_y", 1),
        tracking_options.get("downscale_factor_x", 1),
    ]
    new_spatial_size = [
        ceil(size / scale) for size, scale in zip(view_into_raw_data[0].shape, down_scale_factors)
    ]

    do_scaling = min(down_scale_factors) != 1 or max(down_scale_factors) != 1
    print(f"resizing, going to scale images: {do_scaling}")

    # trim (along the time axis) the input data
    t_from = tracking_options.get("start_from_tp", 0)
    t_to = tracking_options.get("end_at_tp", -1)
    if t_to == -1:
        t_to = view_into_raw_data.shape[0] - 1

    view_into_raw_data = view_into_raw_data[t_from : t_to + 1]
    view_into_seg_data = view_into_seg_data[t_from : t_to + 1]

    print(
        f"preparing new input data: {view_into_raw_data.shape[0]} images of shape "
        f"{new_spatial_size} pixels"
    )

    # 'all_masks' will be in the new downscaled size, and the trimmed length!
    print("memory allocation for segmentation results started...")
    all_masks = np.empty((view_into_raw_data.shape[0], *new_spatial_size), dtype=view_into_seg_data.dtype)

    print("memory allocation for raw images started...")
    all_raws = np.empty((view_into_raw_data.shape[0], *new_spatial_size), dtype=view_into_raw_data.dtype)

    print("resizing started...")
    for t in range(view_into_raw_data.shape[0]):
        all_raws[t] = (
            np.array(resize(view_into_raw_data[t], new_spatial_size, preserve_range=True))
            if do_scaling
            else np.array(view_into_raw_data[t], dtype=view_into_raw_data.dtype)
        )
        all_masks[t] = (
            np.array(
                resize(
                    view_into_seg_data[t],
                    new_spatial_size,
                    preserve_range=True,
                    order=0,
                )
            )
            if do_scaling
            else np.array(view_into_seg_data[t], dtype=view_into_seg_data.dtype)
        )
        print(
            f"done resizing frame {t}, target image size was {all_raws[t].shape} "
            f"(source size was {view_into_raw_data[t].shape})"
        )

    print("resizing done")
    return all_raws, all_masks


def tracking(
    view_into_raw_data,  # a numpy-like array
    seg_data,            # a numpy-like array
    tracking_options: dict[str, Any] = default_tracking_options
):
    """
    Inputs 'view_into_raw_data' and 'seg_data' must be t,z,y,x (even for 2D+t images) and same shape.

    Output is that of Trackastra with possibly downscaled spatial
    coordinates (depending on the 'tracking_options').

    Returns:
        Trackastra graph object
    """
    from trackastra.model import Trackastra

    model_name = tracking_options.get("tracking_model", "ctc")
    tra_model = Trackastra.from_pretrained(model_name)

    print("tracking started...")
    track_graph, _ = tra_model.track(view_into_raw_data, seg_data, mode="greedy")
    # NB: possible alternative tracking modes are "greedy_nodiv" and "ilp" (needs Gurobi)
    print("tracking done")

    return track_graph


def upscale_and_timeshift_trackastra_graph(
    track_graph,  # Trackastra's native graph object
    tracking_options: dict[str, Any] = default_tracking_options,
):
    down_scale_factors = [
        tracking_options.get("downscale_factor_z", 1),
        tracking_options.get("downscale_factor_y", 1),
        tracking_options.get("downscale_factor_x", 1),
    ]
    t_from = tracking_options.get("start_from_tp", 0)

    nodes = track_graph.nodes()
    nodes_data = nodes.data()

    for idx in nodes.keys():
        # upscale the coordinates in zyx axes, and shift in time axis
        node = nodes_data[int(idx)]
        orig_coords = node["coords"]
        new_coords = (
            orig_coords[0] * down_scale_factors[0],
            orig_coords[1] * down_scale_factors[1],
            orig_coords[2] * down_scale_factors[2],
        )
        node["coords"] = new_coords
        node["time"] += t_from

    return track_graph


def upscale_timeshift_save(
    track_graph,
    seg,
    result_path: str,
    tracking_options: dict[str, Any] = default_tracking_options,
) -> None:
    from trackastra.tracking import graph_to_ctc

    upscale_and_timeshift_trackastra_graph(track_graph, tracking_options)
    graph_to_ctc(track_graph, seg, True, outdir=result_path)


def track_entry(
    zarr_path: str,
    scale_level: int,
    list_of_coords_for_non_tzyx_dims_to_reach_raw_channel: list[int],
    list_of_coords_for_non_tzyx_dims_to_reach_seg_channel: list[int],
    result_path: str,
    tracking_options: dict[str, Any] = default_tracking_options,
):
    """
    Track from raw + pre-segmented OME-Zarr channels.

    It is worthwhile to choose 'scale_level' or downscale in x,y,z
    (in 'tracking_options') so that the input images are not more
    than 500+ pixels per spatial dimension.
    """
    raw_data_view = obtain_lazy_view_from_the_zarr_path(
        zarr_path,
        scale_level,
        list_of_coords_for_non_tzyx_dims_to_reach_raw_channel,
    )
    seg_data_view = obtain_lazy_view_from_the_zarr_path(
        zarr_path,
        scale_level,
        list_of_coords_for_non_tzyx_dims_to_reach_seg_channel,
    )
    # NB: now both *_data_view are guaranteed to be ordered as tzyx
    #     and it is truly an unmodified view (not scaled, not trimmed)

    raw, seg = resize(raw_data_view, seg_data_view, tracking_options)
    track_graph = tracking(raw, seg, tracking_options)
    upscale_timeshift_save(track_graph, seg, result_path, tracking_options)
    return track_graph


def resave_ctc_result_tiffs(folder_with_tiffs: str | Path) -> None:
    """
    Replace all .tif files in the given folder with themselves, but
    the saved copies are compressed with "more standard" compression.

    The .tif files as produced from the Trackastra itself are compressed
    with a fairly new compression scheme, and chances are that a downstream
    reader of such result may not be able to handle such .tif files.
    """
    import tifffile as tiff

    tif_files = sorted(list(Path(folder_with_tiffs).glob("*.tif")))
    for tif_file in tif_files:
        print(f"resaving tiff {tif_file}")
        tiff.imwrite(tif_file, tiff.imread(tif_file))


def example1():
    # tops = tracking options
    tops = default_tracking_options.copy()
    tops["downscale_factor_x"] = 3.0
    tops["downscale_factor_y"] = 3.0
    tops["downscale_factor_z"] = 3.0
    dataset_url = (
        "https://s3.cl2.du.cesnet.cz/35b9fef6_a5c7_4724_b7ad_0db97899a356:"
        "public/CTC_trif_01_cropped_2channels_v04.zarr"
    )
    dataset_scale = 0
    select_raw = [0]
    select_masks = [1]
    return track_entry(dataset_url, dataset_scale, select_raw, select_masks, "result1_as_ctc", tops)


def example2():
    # tops = tracking options
    tops = default_tracking_options.copy()
    dataset_url = (
        "https://s3.cl2.du.cesnet.cz/35b9fef6_a5c7_4724_b7ad_0db97899a356:"
        "public/CTC_trif_01_cropped_2channels_v04.zarr"
    )
    dataset_scale = 2
    select_raw = [0]
    select_masks = [1]
    return track_entry(dataset_url, dataset_scale, select_raw, select_masks, "result2_as_ctc", tops)
