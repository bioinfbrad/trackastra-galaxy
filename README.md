# Trackastra Galaxy Tool

## Overview

**Trackastra** is a deep learning-based tool for tracking cell instances in time-lapse microscopy images. It combines:
- **Cellpose**: For automatic cell segmentation. This is an optional step when no segmentation is yet available.
- **Trackastra**: For transformer-based cell tracking across time.
- **ome-zarr**: For reading the input OME-Zarr.
- **CellTrackingChallenge**: For storing the tracking result in
  [CTC format](http://public.celltrackingchallenge.net/documents/Naming%20and%20file%20content%20conventions.pdf),
  which is supported, e.g., in [napari](https://napari.org/stable/), [TrackMate](https://imagej.net/plugins/trackmate/)
  or [Mastodon (Fiji)](https://mastodon.readthedocs.io/en/latest/).

The tool is designed not to require a GPU. It may thus show prolonged running times. It may also show slightly sub-optimal results
as "only" Cellpose v3 (the pre-SAM variant) is used, and Trackastra is operated in the "greedy" (CPU-friendly) mode.

It is worthwhile to consider downscaling the input data. This can be achieved by choosing a lower resolution level of
the input data (as OME-Zarr datasets often provide downscaled copies next to the full resolution data), and/or requesting
downscale factor (per each spatial dimension), in which case this tool will accordingly downscale before (segmentation and) tracking.
The former is controlled with the `--scale-level` parameter, and the latter with the `--downscale-[xyz]` parameters; it is allowed
to combine all of them. The tracking result is stored at the resolution level defined with the `--scale-level`.

Even when the segmentation result is provided, Trackastra still requires the original raw images for tracking.
If the segmentation is not provided, this tool offers to use Cellpose v3 to carry out the segmentation prior to the tracking;
the segmentation result is not saved anywhere.

## Requirements

### Input Data

- **OME-Zarr dataset**: Time-series images in NGFF-compliant zarr format, often referred to as OME-Zarr.
  - Either, it must have dimensions 2D+t: `t` (time), `y` (rows), `x` (columns)
  - Or, it must have dimensions 3D+t: `t` (time), `z` (depth), `y` (rows), `x` (columns)
  - It must show whole nuclei or cells
  - It may have additional channel with segmentation of the nuclei or cells
  - It may have extra dimensions (e.g., multiple channels, which can be selected via coordinates)
  - Data type: optimally *uint16* (16-bit unsigned integer)

### Software Dependencies

The main Python dependencies are the following:
- `trackastra > 0.5`
- `cellpose < 4.0`
- `ome-zarr >= 0.14.0`

All of which, including their transitive dependencies, are available on the `conda-forge` channel.

## Usage Modes

### 1. Segment and Track (Recommended)

Automatically segments nuclei or cells using Cellpose v3, then performs tracking.

```bash
trackastra-galaxy segment-and-track \
    --zarr-path https://uk1s3.embassy.ebi.ac.uk/idr/zarr/v0.4/idr0101A/13457537.zarr/0 \
    --scale-level 0 \
    --raw-channel-coords 0 \
    --downscale-x 1.0 \
    --downscale-y 1.0 \
    --downscale-z 1.0 \
    --start-tp 0 \
    --end-tp -1 \
    --segmentation-model cyto3 \
    --objects-diameter-px \
    --tracking-model ctc \
    --result-path /local/path/to/folder/result_ctc
```

### 2. Track Only

Assumes pre-existing segmentation in a separate channel/dimension.

```bash
trackastra-galaxy track \
    --zarr-path https://uk1s3.embassy.ebi.ac.uk/idr/zarr/v0.4/idr0101A/13457537.zarr/0 \
    --scale-level 0 \
    --raw-channel-coords 0 \
    --seg-channel-coords 1 \
    --downscale-x 1.0 \
    --downscale-y 1.0 \
    --downscale-z 1.0 \
    --start-tp 0 \
    --end-tp -1 \
    --tracking-model ctc \
    --result-path /local/path/to/folder/result_ctc
```

## Parameters

### Common Parameters (Both Modes)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--zarr-path` | Required | URL (https://..., s3://...) or local path to OME-Zarr dataset |
| `--scale-level` | 0 | Pyramid level in OME-Zarr (0 = finest/best resolution) |
| `--downscale-x`, `downscale-y`, `downscale-z` | 1.0 | Spatial downscaling factors (>1 reduces resolution for speed) |
| `--start-tp` | 0 | First time frame to process (0-indexed) |
| `--end-tp` | -1 | Last time frame to process (0-indexed, -1 signals to use all frames) |
| `--tracking-model` | `ctc` | Trackastra tracking model identifier |
| `--result-path` | Required | Folder to be created and populated with .tif files according to the [CTC format](http://public.celltrackingchallenge.net/documents/Naming%20and%20file%20content%20conventions.pdf) |

### Segment and Track Mode Only

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--raw-channel-coords` | 0 | Non-tzyx coordinates (space or comma-separated) to select raw image channel in multi-dimensional OME-Zarr |
| `--segmentation-model` | `cyto3` | Cellpose v3 model: `cyto3`, `cyto2`, or `nuclei` |
| `--objects-diameter-px` | 25 | Expected object diameter in pixels for Cellpose v3 |

### Track Only Mode Only

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--raw-channel-coords` | 0 | Non-tzyx coordinates (space or comma-separated) to select raw image channel |
| `--seg-channel-coords` | 1 | Non-tzyx coordinates (space or comma-separated) to select segmentation channel |

### Multi-Dimensional OME-Zarr Navigation

For OME-Zarr datasets with extra dimensions beyond `tzyx` (or `tyx` for 2D time-lapse):
- Provide integer coordinates for each extra dimension
- Example: 6D data `(t, view, domain, z, y, x)` needs coordinates like `"0 1"` to select view=0, domain=1
- Use space or comma separation: `"0 1"` or `"0,1"`

### Input and Remote Data Access

The tool supports reading local and especially remote OME-Zarr datasets. That said, the `--zarr-path` input parameter
accepts both a local path and a URL. The remote datasets can be hosted via
- S3, e.g., `s3://janelia-cosem-datasets/jrc_mus-choroid-plexus-3/jrc_mus-choroid-plexus-3.zarr`
- HTTP or HTTPS, e.g., `https://public.czbiohub.org/royerlab/zebrahub/imaging/multi-view/ZMNS001.ome.zarr`

### Output

The tool creates an output folder at `--result-path`, and populates it with `man_trackTTTT.tif` (`T`s represent zero-padded,
4-digits time point) and `man_track.txt` files. This is the
[CTC format](http://public.celltrackingchallenge.net/documents/Naming%20and%20file%20content%20conventions.pdf)
for the results of tracking.

## Tool Execution

### Command Line example

```bash
# Activate environment
pixi shell

# Run segmentation followed by tracking
trackastra-galaxy segment-and-track \
    --zarr-path test-data/sample_timelapse.zarr \
    --end-tp 3 \
    --result-path ctc_result_folder

# View results
ls ctc_result_folder
```

All coordinates and numerical parameters are validated before execution.
Errors print to stderr with appropriate exit codes for Galaxy error detection.

### Python API example

**Segment and Track:**
```python
from trackastra_galaxy import cli
from trackastra_galaxy.trackastra_galaxy import default_tracking_options

tops = default_tracking_options.copy()
tops["segmentation_model"] = "cyto3"

cli.segment_and_track_entry(
  zarr_path = "test-data/sample_timelapse.zarr",
  scale_level = 0,
  list_of_coords_for_non_tzyx_dims_to_reach_raw_channel = [0],
  result_path = "ctc_result_folder",
  tracking_options = tops,
)
```

**Track Only:**
```python
from trackastra_galaxy import cli
from trackastra_galaxy.trackastra_galaxy import default_tracking_options

cli.track_entry(
  zarr_path = "test-data/sample_timelapse.zarr",
  scale_level = 0,
  list_of_coords_for_non_tzyx_dims_to_reach_raw_channel = [0],
  list_of_coords_for_non_tzyx_dims_to_reach_seg_channel = [1],
  result_path = "ctc_result_folder",
)
```

## Online OME-Zarr Datasets

Ready-to-use test datasets from [Cesnet CZ](https://www.cesnet.cz/en):

```
2D, raw and mask channels:  https://s3.cl2.du.cesnet.cz/35b9fef6_a5c7_4724_b7ad_0db97899a356:public/CTC_CHOas2D_01_2channels_v04.zarr
3D, raw and mask channels:  https://s3.cl2.du.cesnet.cz/35b9fef6_a5c7_4724_b7ad_0db97899a356:public/CTC_trif_01_cropped_2channels_v04.zarr
```

This dataset can be used directly as `--zarr-path` for testing without downloading.

## Advanced: Key Parameters Explained

**Downscaling**: 
- Useful for large images (500+ pixels per dimension)
- Example: `--downscale-x 2.0` processes at half resolution, faster but may reduce tracking precision
- Set to 1.0 for full resolution (default)
- Consider downscaling when processing large 3D datasets or memory-limited systems

**Time Point Range**:
- Helpful for testing parameters on a subset
- `--start-tp 0 --end-tp 5` processes frames 0-5 only, 6 frames in total
- Use `-1` for `--end-tp` to flag that all frames should be used
- Useful for validating parameters before processing the entire time series

**Pyramid Levels**:
- OME-Zarr datasets often have multi-resolution pyramids
- Level 0 = finest resolution (slowest, largest, most accurate)
- Higher levels = downsampled versions (faster, smaller)
- Default level 0 is recommended

**Channel/Dimension Coordinates**:
- If OME-Zarr has extra dimensions beyond tzyx (e.g., time,channel,z,y,x), use coordinate indices
- Example: for time,*channel*,z,y,x format use `--raw-channel-coords 0` to select the first *channel*
- Multiple coordinates use space or comma separation: `0 1` or `0,1`

## Troubleshooting

### Common Issues and Solutions

**"Scale index negative or larger than available resolutions"**
- The requested pyramid level doesn't exist in the OME-Zarr
- Solutions:
  - Use `--scale-level 0` (default, safest option)
  - If the data is still too large, consider the `--downscale-x/y/z` options

**Memory errors on large datasets**
- The downscaled data is still too large for available memory
- Solutions:
  - Increase `--downscale-x/y/z` factors further, try e.g. 4 or 8
  - Process fewer time points with `--start-tp` and `--end-tp`
  - Use a higher `--scale-level` (lower resolution)

**Segmentation quality issues**
- Segmentation is too aggressive or too lenient
- Try different `--segmentation-model` options:
  - `cyto3`: General cells (recommended, default)
  - `cyto2`: Alternative model for comparison
  - `nuclei`: Optimized for nuclear/DAPI staining
- Try different `--objects-diameter-px` values.
- Check image contrast and brightness

**Tracking breaks or incomplete tracks**
- Cells moving too fast between frames may be missed
- Solutions:
  - Reduce `--downscale-x/y/z` factors for finer tracking
  - Check image quality and contrast
  - Reduce frame intervals if possible (i.e., use more time points)

### Debugging

Enable verbose output:

```bash
python -u cli.py segment-and-track \
    --zarr-path data.zarr \
    --result-path ctc_folder 2>&1 | tee debug.log
```

## Citation

If you use Trackastra in published research, please cite:
- Trackastra: Gallusser, B. & Weigert, M. (2024) Trackastra: Transformer-based cell tracking for live-cell microscopy. In *European conference on computer vision*, 467-484.
- Cellpose: Stringer, C., Wang, T., Michaelos, M. & Pachitariu, M. (2021). Cellpose: a generalist algorithm for cellular segmentation. *Nature Methods*, 18(1), 100-106.

## References

- [NGFF Zarr Spec](https://ngff.openmicroscopy.org/)
- [Trackastra Documentation](https://github.com/QuantumAstronomy/trackastra)
- [Cellpose Documentation](https://cellpose.readthedocs.io/)
- [Cell Tracking Challenge](https://celltrackingchallenge.net/)
- [napari-ctc-io](https://github.com/bentaculum/napari-ctc-io)
- [Mastodon CTC plugin](https://github.com/mastodon-sc/mastodon-ctc)
- [ngff-zarr Documentation](https://ngff-zarr.readthedocs.io/en/latest/)
- [Galaxy Tool Development](https://docs.galaxyproject.org/en/master/dev/schema.html)
