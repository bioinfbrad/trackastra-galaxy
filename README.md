# Trackastra Galaxy Tool

## Overview

**Trackastra** is a deep learning-based tool for tracking cell instances in time-lapse microscopy images. It combines:
- **Cellpose**: For automatic cell segmentation. This is an optional step when no segmentation is yet available.
- **Trackastra**: For transformer-based cell tracking across time.
- **ome-zarr**: For reading the input OME-Zarr.
- **CellTrackingChallenge**: For storing the tracking result in
  [CTC format](http://public.celltrackingchallenge.net/documents/Naming%20and%20file%20content%20conventions.pdf),
  which is supported, e.g., in [napari](https://napari.org/stable/) or [Mastodon (Fiji)](https://mastodon.readthedocs.io/en/latest/).

This Galaxy wrapper enables easy access to cell tracking workflows without requiring command-line expertise.

The tool is designed to not require GPU. It may thus show prolonged running times. It may also show slightly sub-optimal results
as "only" Cellpose v3 (the pre-SAM variant) is used as well as Trackastra is operated in the "greedy" (CPU-friendly) mode.

It is worthwhile to consider downscaling the input data. This can be achieved by choosing a lower resolution level of
the input data (as OME-Zarr datasets often provide downscaled copies next to the full resolution data), and/or requesting
downscale factor (per each dimension), in which case this tool will accordingly downscale before (segmentation) and tracking.
The former is controlled with the `scale_level` parameter, and the latter with the `downscale_` parameters; it is allowed
to combine all of them. The tracking result is stored at the resolution level defined with the `scale_level`.

Even when segmentation result is provided, Trackastra in any case requires also the original raw images for the tracking.
If the segmentation is not provided, this tool offers to use Cellpose v3 to carry out the segmentation prior the tracking;
the segmentation result is not saved anywhere.

## Requirements

### Input Data

- **OME-Zarr dataset**: Time-series images in NGFF-compliant zarr format, often referred to as OME-Zarr.
  - Either, it must have dimensions 2D+t: `t` (time), `y` (rows), `x` (columns)
  - Or, it must have dimensions 3D+t: `t` (time), `z` (depth), `y` (rows), `x` (columns)
  - It must show whole nuclei or cells
  - It may have additional channel with segmentation of the cells
  - It may have extra dimensions (e.g., multiple channels, which can be selected via coordinates)
  - Data type: optimally uint16 (16-bit unsigned integer)

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
python trackastra_wrapper.py segment_and_track \
    --zarr_path https://uk1s3.embassy.ebi.ac.uk/idr/zarr/v0.4/idr0101A/13457537.zarr/0 \
    --scale_level 0 \
    --channel_coords 0 \
    --downscale_x 1.0 \
    --downscale_y 1.0 \
    --downscale_z 1.0 \
    --start_tp 0 \
    --end_tp -1 \
    --segmentation_model cyto3 \
    --tracking_model ctc
```

### 2. Track Only

Assumes pre-existing segmentation in a separate channel/dimension.

```bash
python trackastra_wrapper.py track \
    --zarr_path https://uk1s3.embassy.ebi.ac.uk/idr/zarr/v0.4/idr0101A/13457537.zarr/0 \
    --scale_level 0 \
    --raw_channel_coords 0 \
    --seg_channel_coords 1 \
    --downscale_x 1.0 \
    --downscale_y 1.0 \
    --downscale_z 1.0 \
    --start_tp 0 \
    --end_tp -1 \
    --tracking_model ctc
```

## Parameters

### Common Parameters (Both Modes)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `zarr_path` | Required | URL (https://..., s3://...) or local path to OME-Zarr dataset |
| `scale_level` | 0 | Pyramid level in OME-Zarr (0 = finest/best resolution) |
| `downscale_x`, `downscale_y`, `downscale_z` | 1.0 | Spatial downscaling factors (>1 reduces resolution for speed) |
| `start_tp` | 0 | First time frame to process (0-indexed) |
| `end_tp` | -1 | Last time frame to process (-1 = all frames) |
| `tracking_model` | `ctc` | Trackastra tracking model identifier |

### Segment and Track Mode Only

| Parameter | Default | Description |
|-----------|---------|-------------|
| `channel_coords` | 0 | Non-tzyx coordinates (space or comma-separated) to select raw image channel in multi-dimensional OME-Zarr |
| `segmentation_model` | `cyto3` | Cellpose v3 model: `cyto3`, `cyto2`, or `nuclei` |

### Track Only Mode Only

| Parameter | Default | Description |
|-----------|---------|-------------|
| `raw_channel_coords` | 0 | Non-tzyx coordinates (space or comma-separated) to select raw image channel |
| `seg_channel_coords` | 0 | Non-tzyx coordinates (space or comma-separated) to select segmentation channel |

### Multi-Dimensional OME-Zarr Navigation

For OME-Zarr datasets with extra dimensions beyond `tzyx` (or `tyx` for 2D time-lapse):
- Provide integer coordinates for each extra dimension
- Example: 6D data `(t, view, domain, z, y, x)` needs coordinates like `"0 1"` to select view=0, domain=1
- Use space or comma separation: `"0 1"` or `"0,1"`

## Output

The tool creates an output folder `trackastra_geff.zarr`, which is a zarr (not OME) with GEFF data.
GEFF is a modern flexible format for representing (not only) the nuclei or cells tracking.

The folder is created in the working directory and automatically copied to the Galaxy outputs.

## Remote Data Access

The tool supports various OME-Zarr data sources:

```bash
# Activate environment
pixi shell

# Run segment_and_track
python trackastra_wrapper.py segment_and_track \
    --zarr_path test-data/sample_timelapse.zarr \
    --end_tp 3 \
    --output_tracks test_output.csv

# View results
ls trackastra_geff.zarr
```

## Implementation Notes

### Tool Wrapper Structure

```
tools/trackastra/
├── trackastra.xml           # Galaxy tool definition (XML)
├── trackastra_wrapper.py    # Main Python CLI wrapper
├── pixi.toml                # Pixi environment dependencies
├── .shed.yml                # Tool Shed metadata
├── test-data/               # Test inputs directory (initially empty)
└── README.md                # This file
```

## Galaxy Integration

### Command Line Interface

The tool provides two subcommands for Galaxy:

**Segment and Track:**
```
python trackastra_wrapper.py segment_and_track --zarr_path ... --channel_coords ... --segmentation_model cyto3 ...
```

**Track Only:**
```
python trackastra_wrapper.py track --zarr_path ... --raw_channel_coords ... --seg_channel_coords ... ...
```

All coordinates and numerical parameters are validated before execution.
Errors print to stderr with appropriate exit codes for Galaxy error detection.

## Online OME-Zarr Datasets

Ready-to-use test datasets from IDR (Image Data Resource):

```
https://uk1s3.embassy.ebi.ac.uk/idr/zarr/v0.4/idr0101A/13457537.zarr/0
```

This dataset can be used directly as zarr_path for testing without downloading.

## Advanced: Key Parameters Explained

**Downscaling**: 
- Useful for large images (500+ pixels per dimension)
- Example: `--downscale_x 2.0` processes at half resolution, faster but may reduce tracking precision
- Set to 1.0 for full resolution (default)
- Consider downscaling when processing large 3D datasets or memory-limited systems

**Time Point Range**:
- Helpful for testing parameters on a subset
- `--start_tp 0 --end_tp 5` processes frames 0-5 only, 6 frames in total
- Use `-1` for `end_tp` to flag that all frames should be used
- Useful for validating parameters before processing entire time series

**Pyramid Levels**:
- OME-Zarr datasets often have multi-resolution pyramids
- Level 0 = finest resolution (slowest, largest, most accurate)
- Higher levels = downsampled versions (faster, smaller)
- Default level 0 is recommended

**Channel/Dimension Coordinates**:
- If OME-Zarr has extra dimensions beyond tzyx (e.g., time,channel,z,y,x), use coordinate indices
- Example: for time,*channel*,z,y,x format use `--channel_coords 0` to select the first *channel*
- Multiple coordinates use space or comma separation: `0 1` or `0,1`

## Troubleshooting

### Common Issues and Solutions

**"Scale index negative or larger than available resolutions"**
- The requested pyramid level doesn't exist in the OME-Zarr
- Solutions:
  - Use `--scale_level 0` (default, safest option)
  - If the data is still too large, consider the --downscale options

**Memory errors on large datasets**
- The downscaled data is still too large for available memory
- Solutions:
  - Increase `--downscale_x/y/z` factors further, try e.g. 4 or 8
  - Process fewer time points with `--start_tp` and `--end_tp`
  - Use a higher `--scale_level` (lower resolution)

**Segmentation quality issues**
- Segmentation is too aggressive or too lenient
- Try different `--segmentation_model` options:
  - `cyto3`: General cells (recommended, default)
  - `cyto2`: Alternative model for comparison
  - `nuclei`: Optimized for nuclear/DAPI staining
- Check image contrast and brightness

**Tracking breaks or incomplete tracks**
- Cells moving too fast between frames may be missed
- Solutions:
  - Reduce `--downscale_*` factors for finer tracking
  - Check image quality and contrast
  - Reduce frame intervals if possible (i.e., use more time points)

### Debugging

Enable verbose output:

```bash
python -u trackastra_wrapper.py segment_and_track \
    --zarr_path data.zarr \
    --output_tracks tracks.csv 2>&1 | tee debug.log
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
