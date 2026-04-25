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
            f"Found {len(axes_unknown)} non_tzyx dimensions (size of the first "
            f"is {zarr_image.shape[ axes_unknown[0] ]}) but different number "
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


def obtain_size_adjusted_imgs_from_tiff_path(
    input_path: str,
    skip_frames: int,
    target_shape: list[int],
    tracking_options: dict[str, Any] = None,
):
    """
    This method reads segmentation masks from either one multi-frame
    tiff file, which shall be 3(4)-dimensional for 2(3)D time-lapse
    input, or from series of single-frame tiff files, which shall be
    2(3)-dimensional for 2(3)D time-lapse input. The function resizes
    only along spatial axes to fit the 'target_shape' size in pixels,
    nearest neighbor (no interpolation) is used during the resizing.

    The first 'skip_frames' segmentation images are skipped over (ignored)
    before the loading starts. This is useful if the segmentation is prepared
    for a full original time-lapse but only 'tracking_options.start_from_tp'
    to 'tracking_options.end_at_tp' time points are tracked, in which case
    provide 'skip_frames = tracking_options.start_from_tp'. Otherwise, set
    it to 0 (zero) to have nothing skipped. Value of 0 (zero) is useful when,
    again, a shorter sub-sequence of the original time-lapse is tracked, but
    the segmentation is prepared only for this sub-sequence.

    The function returns a numpy array of the 'target_shape'.

    input_path :
        Path to a multi-frame (one) tiff file,
        or path to a folder with many single-frame tiff files.

    skip_frames :
        Number of time points to skip at the path. These time
        points (frames) are the first "slices" in a multi-frame
        tiff file, or it is the first number of single-frame tiff
        files in the folder.

    target_shape :
        Quadruple of (T,Z,Y,X) (using Z=1 for 2D images). The loaded
        images (whose number shall be T) may are resized (scaled,
        no interpolation) to match the spatial part of the quadruple.

    tracking_options :
        This is either None or a copy of the 'default_tracking_options',
        and it is provided only for checking the consistency of inputs.
        It checks that the time span in 'tracking_options' matches T from
        the 'target_shape' quadruple.
    """

    if len(target_shape) != 4:
        flag_error_and_quit(
            f"Reference geometry/shape of the input is {target_shape} "
            "but was expected to be of length 4 (T,Z,Y,X)"
        )

    # trim (along the time axis) the input data
    t_from = tracking_options.get("start_from_tp", 0)
    t_to = tracking_options.get("end_at_tp", -1)
    if t_to == -1:
        t_to = target_shape.shape[0] - 1

    # check consistency that required shape matches tracking_options
    time_points_number = target_shape[0]
    if (t_to - t_from +1) != time_points_number:
        flag_error_and_quit(
            f"Expected to extract {t_from} to {t_to} frames while "
            f"aiming to squeeze the data to target_shape {target_shape}, "
            f"which mandates {time_points_number} frames"
        )

    import os
    if not os.path.isdir(input_path):
        return obtain_size_adjusted_imgs_from_one_tiff(input_path, skip_frames, target_shape)
    else:
        from natsort import natsorted
        tiff_files_paths = natsorted([ f.path
            for f in os.scandir(input_path)
            if f.is_file() and f.name.endswith((".tif",".tiff")) ])

        discovered_files = len(tiff_files_paths)
        if discovered_files == 0:
            flag_error_and_quit(
                f"single-frame tiff: Found no .tif or .tiff in the folder {input_path}"
            )
        if discovered_files < (skip_frames+target_shape[0]):
            flag_error_and_quit(
                f"single-frame tiff: Found only {discovered_files}, which is not enough "
                f"to load {target_shape[0]} files while skipping {skip_frames} files"
            )

        tiff_files_paths = tiff_files_paths[ skip_frames : skip_frames+target_shape[0] ]
        return obtain_size_adjusted_imgs_from_tiffs(tiff_files_paths, target_shape)


def obtain_size_adjusted_imgs_from_one_tiff(
    input_path: str,
    skip_frames: int,
    target_shape: list[int],
):
    """
    An internal function to implement 'obtain_size_adjusted_imgs_from_tiff_path()'
    for multi-frame (one) tiff image given in the 'input_path'.
    """
    from tifffile import imread
    from skimage.transform import resize

    print(f"multi-frame tiff: reading {input_path}")
    img = imread(input_path)

    # check dimensions:
    if not (len(img.shape) == 3 or len(img.shape) == 4):
        flag_error_and_quit(
            f"multi-frame tiff: Input image {input_path} is of shape {img.shape} "
            "that is not 3- or 4-dimensional (2D+t or 3D+t)"
        )
    if len(img.shape) == 3 and not target_shape[1] == 1:
        flag_error_and_quit(
            f"multi-frame tiff: Input image {input_path} is of shape {img.shape} "
            f"for 2D+t but 3D+t was needed (target T,Z,Y,X = {target_shape})"
        )
    if img.shape[0] < (skip_frames+target_shape[0]):
        flag_error_and_quit(
            f"multi-frame tiff: Found only {img.shape[0]}, which is not enough "
            f"to load {target_shape[0]} files while skipping {skip_frames} files"
        )

    is_x_resize_needed = img.shape[-1] != target_shape[-1]
    is_y_resize_needed = img.shape[-2] != target_shape[-2]
    if is_x_resize_needed != is_y_resize_needed:
        flag_error_and_quit(
            f"multi-frame tiff: Reference tiff image of shape {img.shape}, but "
            f"target_shape {target_shape} requires to resize only x or y, "
            "both should be required (or not) at the same time!"
        )

    # NB: the is_[xy]_resize* are now for sure of the same value, check z_resize if 3D+t images
    is_z_resize_needed = img.shape[1] != target_shape[1] if len(img.shape) == 4 else is_x_resize_needed
    if is_x_resize_needed != is_z_resize_needed:
        flag_error_and_quit(
            f"multi-frame tiff: Reference tiff image of shape {img.shape}, but "
            f"target_shape {target_shape} requires to resize only x or z, "
            "both should be required (or not) at the same time!"
        )

    # to be allocated later
    all_masks = None
    time_points_number = target_shape[0]

    if is_x_resize_needed:
        print("multi-frame tiff: memory allocation for segmentation results started...")
        all_masks = np.empty(target_shape, dtype=img.dtype)

        if target_shape[1] == 1:
            # 2D
            new_size = target_shape[2:]
            for t in range(time_points_number):
                all_masks[t,0] = resize(
                    img[t + skip_frames],
                    new_size,
                    preserve_range=True,
                    order=0,
                )
                print(f"multi-frame tiff: done resizing frame {t}, target image size was {new_size}")
        else:
            # 3D
            new_size = target_shape[1:]
            for t in range(time_points_number):
                all_masks[t] = resize(
                    img[t + skip_frames],
                    new_size,
                    preserve_range=True,
                    order=0,
                )
                print(f"multi-frame tiff: done resizing frame {t}, target image size was {new_size}")
    else:
        print("multi-frame tiff: taking its memory as is...")
        all_masks = img[skip_frames : skip_frames+time_points_number]
        if target_shape[1] == 1:
            # assumed tyx, inject singleton z
            all_masks = np.reshape(all_masks, (all_masks.shape[0], 1, all_masks.shape[1], all_masks.shape[2]))

    return all_masks



def obtain_size_adjusted_imgs_from_tiffs(
    input_paths: list[str],
    target_shape: list[int],
):
    """
    An internal function to implement 'obtain_size_adjusted_imgs_from_tiff_path()'
    for several single-frame tiff images given in the 'input_paths' list.
    """
    from tifffile import imread
    from skimage.transform import resize

    print(f"single-frame tiff: reading the first image {input_paths[0]}")
    img = imread(input_paths[0])

    # check dimensions:
    if not (len(img.shape) == 2 or len(img.shape) == 3):
        flag_error_and_quit(
            f"single-frame tiff: Input image {input_paths[0]} is of shape {img.shape} "
            "that is not 2- or 3-dimensional (2D or 3D)"
        )
    if len(img.shape) == 2 and not target_shape[1] == 1:
        flag_error_and_quit(
            f"single-frame tiff: Input image {input_paths[0]} is of shape {img.shape} "
            f"for 2D+t but 3D+t was needed (target T,Z,Y,X = {target_shape})"
        )
    if len(input_paths) < (target_shape[0]):
        flag_error_and_quit(
            f"single-frame tiff: List of input images is not long enough "
            f"to load {target_shape[0]} required files"
        )

    is_x_resize_needed = img.shape[-1] != target_shape[-1]
    is_y_resize_needed = img.shape[-2] != target_shape[-2]
    if is_x_resize_needed != is_y_resize_needed:
        flag_error_and_quit(
            f"single-frame tiff: Tiff images of shape {img.shape}, but "
            f"target_shape {target_shape} requires to resize only x or y, "
            "both should be required (or not) at the same time!"
        )

    # NB: the is_[xy]_resize* are now for sure of the same value, check z_resize if 3D+t images
    is_z_resize_needed = img.shape[0] != target_shape[1] if len(img.shape) == 3 else is_x_resize_needed
    if is_x_resize_needed != is_z_resize_needed:
        flag_error_and_quit(
            f"single-frame tiff: Tiff images of shape {img.shape}, but "
            f"target_shape {target_shape} requires to resize only x or z, "
            "both should be required (or not) at the same time!"
        )

    # 'all_masks' will be in the new downscaled size, and the trimmed length!
    print("single-frame tiff: memory allocation for segmentation results started...")
    all_masks = np.empty(target_shape, dtype=img.dtype)
    time_points_number = target_shape[0]

    if target_shape[1] == 1:
        # 2D
        new_size = target_shape[2:]
        for t in range(time_points_number):
            # don't read the first image again
            if t > 0:
                print(f"single-frame tiff: reading image {input_paths[t]}")
                img = imread(input_paths[t])

            if is_x_resize_needed:
                all_masks[t,0] = resize(
                    img,
                    new_size,
                    preserve_range=True,
                    order=0,
                )
                print(f"single-frame tiff: done resizing frame {t}, target image size was {new_size}")
            else:
                all_masks[t,0] = img
                print(f"single-frame tiff: done taking frame {t} as is (size is {img.shape})")
    else:
        # 3D
        new_size = target_shape[1:]
        for t in range(time_points_number):
            # don't read the first image again
            if t > 0:
                print(f"single-frame tiff: reading image {input_paths[t]}")
                img = imread(input_paths[t])

            if is_x_resize_needed:
                all_masks[t] = resize(
                    img,
                    new_size,
                    preserve_range=True,
                    order=0,
                )
                print(f"single-frame tiff: done resizing frame {t}, target image size was {new_size}")
            else:
                all_masks[t] = img
                print(f"single-frame tiff: done taking frame {t} as is (size is {img.shape})")

    return all_masks



def resize(
    view_into_data,  # a numpy-like array
    tracking_options: dict[str, Any] = default_tracking_options,
    is_resizing_masks: bool = False,
):
    from skimage.transform import resize

    print(
        f"provided input data: {view_into_data.shape[0]} images of shape "
        f"{view_into_data.shape[1:]} pixels"
    )

    # figure out the (possibly) downscaled spatial size (zyx axes)
    down_scale_factors = [
        tracking_options.get("downscale_factor_z", 1),
        tracking_options.get("downscale_factor_y", 1),
        tracking_options.get("downscale_factor_x", 1),
    ]
    new_spatial_size = [
        ceil(size / scale) for size, scale in zip(view_into_data[0].shape, down_scale_factors)
    ]

    do_scaling = min(down_scale_factors) != 1 or max(down_scale_factors) != 1
    print(f"resizing, going to scale images: {do_scaling}")

    # trim (along the time axis) the input data
    t_from = tracking_options.get("start_from_tp", 0)
    t_to = tracking_options.get("end_at_tp", -1)
    if t_to == -1:
        t_to = view_into_data.shape[0] - 1

    view_into_data = view_into_data[t_from : t_to + 1]

    print(
        f"preparing new input data: {view_into_data.shape[0]} images of shape "
        f"{new_spatial_size} pixels"
    )

    # 'all_imgs' will be in the new downscaled size, and the trimmed length!
    print("memory allocation for raw images started...")
    all_imgs = np.empty((view_into_data.shape[0], *new_spatial_size), dtype=view_into_data.dtype)

    print("resizing started...")
    for t in range(view_into_data.shape[0]):
        all_imgs[t] = (
            np.array(resize(view_into_data[t], new_spatial_size, preserve_range=True, order = 0 if is_resizing_masks else 1))
            if do_scaling
            else np.array(view_into_data[t], dtype=view_into_data.dtype)
        )
        print(
            f"done resizing frame {t}, target image size was {all_imgs[t].shape} "
            f"(source size was {view_into_data[t].shape})"
        )

    print("resizing done")
    return all_imgs


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


def track_entry__seg_zarr(
    zarr_path: str,
    scale_level: int,
    list_of_coords_for_non_tzyx_dims_to_reach_raw_channel: list[int],
    list_of_coords_for_non_tzyx_dims_to_reach_seg_channel: list[int],
    result_path: str,
    tracking_options: dict[str, Any] = default_tracking_options,
):
    """
    Track from raw + pre-segmented OME-Zarr channels (two channels required).

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

    raw = resize(raw_data_view, tracking_options, is_resizing_masks = False)
    seg = resize(seg_data_view, tracking_options, is_resizing_masks = True)
    return track_entry(raw, seg, tracking_options)


def track_entry__seg_tiff(
    zarr_path: str,
    scale_level: int,
    list_of_coords_for_non_tzyx_dims_to_reach_raw_channel: list[int],
    tiffs_path: str,
    skip_frames: int,
    result_path: str,
    tracking_options: dict[str, Any] = default_tracking_options,
):
    """
    Track from raw OME-Zarr channel + series of TIFFs with pre-segmented data.

    It is worthwhile to choose 'scale_level' or downscale in x,y,z
    (in 'tracking_options') so that the input images are not more
    than 500+ pixels per spatial dimension.

    The input TIFFs will be potentially resized to match the size of
    the prepared (selected scale, additionally and optionally down-scaled)
    raw images. When tracking in only a time points sub-interval (as
    compared to the original OME-Zarr raw channel), a series of TIFFs can
    be prepared only for that interval, in which case use 'skip_frames = 0'.
    If, however, TIFFs for all original time points are available, use
    'skip_frames = tracking_options.start_from_tp' to "rewind" to the
    corresponding TIFFs.
    """
    raw_data_view = obtain_lazy_view_from_the_zarr_path(
        zarr_path,
        scale_level,
        list_of_coords_for_non_tzyx_dims_to_reach_raw_channel,
    )
    raw = resize(raw_data_view, tracking_options, is_resizing_masks = False)

    seg = obtain_size_adjusted_imgs_from_tiff_path(
        tiffs_path,
        skip_frames,
        raw.shape,
        tracking_options,
    )
    # NB: now both 'raw' and 'seg' are guaranteed to be ordered as tzyx
    #     and it is truly an unmodified view (not scaled, not trimmed)

    return track_entry(raw, seg, tracking_options)


def track_entry(raw, seg, tracking_options):
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
