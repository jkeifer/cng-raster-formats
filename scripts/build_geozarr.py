#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "async-geotiff>=0.5.1",
#     "geozarr-toolkit>=0.1.2",
#     "obstore>=0.11.0",
#     "zarr>=3.1.3",
# ]
# ///
"""Convert the nb01/nb03 Sentinel-2 COG into the workshop's Zarr v3 GeoZarr store.

A pure whole-scene COG -> GeoZarr converter: everything about the store is
driven by the source COG's own metadata and structure. Reads the full
Sentinel-2 L2A B04 scene used by exercises 01 and 03 (T10TFR, EPSG:32610) via
HTTP range requests (async-geotiff + obstore) and writes a Zarr v3 store
designed for exercise 02's by-hand reads:

- the FULL scene, on the COG's own grid: nb02's locate-the-POI-pixel math
  lines up exactly with nb01's work on the COG (same grid, same pixel
  coordinates -- locating the POI is notebook work, not build-script work)
- the multiscale pyramid IS the COG's: level ``0`` is the base image and
  levels ``1``..``n`` are the COG's own overview IFDs, read as-is (no local
  resampling); each level's shape and geotransform come from its IFD
- chunks match the COG's full-resolution internal tile size (read from its
  metadata at runtime; square tiles are asserted), uniformly across levels
- codec pipeline ``fixedscaleoffset`` -> ``delta`` -> ``bytes`` -> ``zstd``
  (no sharding): the SAME decode recipe exercise 01 performs by hand on a COG
  tile (undo the deflate, undo TIFF predictor 2, apply the DN -> reflectance
  scale/offset from the TIFF tags) -- but here each step is declared as
  explicit codec metadata in ``zarr.json``, so the store *tells you* the
  recipe instead of hiding it in format lore. The logical dtype is float32
  reflectance; the scaling codec (scale/offset from the COG's TIFF tags)
  encodes to the COG's uint16 DNs (bit-exact, asserted at build time), delta
  differences them, zstd compresses.
- ``dimension_names`` on every array
- geo metadata via the proj: + spatial: + multiscales zarr conventions
  (attribute-based, attached with geozarr-toolkit; NOT CF grid_mapping)

This script is deliberately standalone (PEP 723 inline metadata) so its deps
stay out of the workshop environment:

    uv run scripts/build_geozarr.py --out ./data/<store>.zarr
"""

from __future__ import annotations

import argparse
import asyncio
import shutil
import sys

from pathlib import Path

import numpy as np
import zarr

from async_geotiff import GeoTIFF
from geozarr_toolkit import (
    MultiscalesConventionMetadata,
    ProjConventionMetadata,
    SpatialConventionMetadata,
    create_geozarr_attrs,
    create_multiscales_layout,
    create_zarr_conventions,
    validate_group,
)
from obstore.store import HTTPStore

# Delta and FixedScaleOffset are zarr-python's wrappers around the numcodecs
# codecs of the same names (also at zarr.codecs.numcodecs / numcodecs.zarr3),
# serialized into zarr.json as "numcodecs.delta" / "numcodecs.fixedscaleoffset".
# numcodecs is already a zarr dependency, so no extra inline dep is needed.
# NOT used: zarr's native "scale_offset" codec (zarr>=3.2) -- it is
# dtype-preserving by spec (no astype), so it cannot encode float reflectance
# down to uint16 DNs on its own; that would take a second "cast_value" codec,
# whose optional cast-value-rs backend every reader would then need installed.
# FixedScaleOffset does the whole scale/offset/round/cast step in one codec.
from zarr.codecs import Delta, FixedScaleOffset, ZstdCodec

# The same scene/asset nb01 resolves via STAC search and nb03 hardcodes.
COG_URL = (
    'https://e84-earth-search-sentinel-data.s3.us-west-2.amazonaws.com'
    '/sentinel-2-c1-l2a/10/T/FR/2023/12/S2B_T10TFR_20231223T190950_L2A/B04.tif'
)

DIMS = ['y', 'x']
# Plain zstd rather than blosc(zstd): exercise 02 teaches by-hand chunk reads,
# and a plain-zstd chunk file is a standard zstd frame that any zstd library
# can decode, whereas blosc wraps compressed data in its own framing that only
# blosc understands. Write-once/read-many store, so favor ratio over speed
# (level picked by benchmarking sizes on the delta-encoded data: 13 beat both
# 19 and 22 by a hair, and compresses faster).
ZSTD_LEVEL = 13


def level_attrs(transform: object, shape: tuple[int, int], epsg: int) -> dict:
    """spatial: + proj: convention attrs for one resolution level."""
    a = transform  # affine.Affine: (a, b, c, d, e, f) row-major 2x3
    xmin, ymax = a.c, a.f  # type: ignore[attr-defined]
    xmax = xmin + a.a * shape[1]  # type: ignore[attr-defined]
    ymin = ymax + a.e * shape[0]  # type: ignore[attr-defined]
    return create_geozarr_attrs(
        dimensions=DIMS,
        crs=f'EPSG:{epsg}',
        transform=[a.a, a.b, a.c, a.d, a.e, a.f],  # type: ignore[attr-defined]
        bbox=[xmin, ymin, xmax, ymax],
        shape=list(shape),
    )


async def build(out: Path) -> None:
    base_url, _, cog_path = COG_URL.rpartition('/')
    gt = await GeoTIFF.open(cog_path, store=HTTPStore.from_url(base_url))

    epsg = gt.crs.to_epsg()
    if epsg != 32610:
        raise SystemExit(f'error: expected EPSG:32610, got EPSG:{epsg}')

    # The store geometry is derived from the COG: zarr chunks are sized to the
    # COG's full-res internal tiles, so the design assumes square tiles. The
    # overview IFDs use their own (smaller) tile size, but the store chunks
    # every level at the full-res tile size anyway -- one uniform chunk-size
    # story for nb02 and fewer chunk files, and each level's chunk grid is
    # declared in its own zarr.json regardless.
    if gt.tile_width != gt.tile_height:
        raise SystemExit(
            f'error: COG tiles are {gt.tile_width}x{gt.tile_height}; '
            'the store design assumes square tiles'
        )
    chunk = gt.tile_width

    # The pyramid IS the COG's: base image plus its overview IFDs, finest to
    # coarsest, copied pixel-for-pixel (no local resampling).
    sources = [gt, *gt.overviews]
    print(
        f'converting {COG_URL}\n'
        f'  base {gt.shape} @ {gt.transform.a:g} m, {chunk}px tiles -> '
        f'{chunk}px chunks; {len(gt.overviews)} COG overviews'
    )

    # The codec chain mirrors nb01's by-hand COG decode, declared as metadata.
    # DN -> reflectance is the COG's own scaling (reflectance = DN * scale +
    # offset), expressed as a FixedScaleOffset codec: the array's logical
    # dtype is float32 reflectance, the encoded dtype is the COG's uint16 DN
    # (DN = round((reflectance - add_offset) / scale_factor), bit-exact --
    # asserted per level below). Because the scaling lives in the codec
    # pipeline, the arrays must NOT also carry CF scale_factor/add_offset
    # attrs, or xarray would apply the scaling twice.
    scale_factor, add_offset = gt.scales[0], gt.offsets[0]
    scaling = FixedScaleOffset(
        offset=add_offset, scale=1 / scale_factor, dtype='<f4', astype='<u2'
    )
    # Delta on the uint16 DNs plays the role of TIFF predictor 2, with one
    # difference worth teaching: numcodecs Delta differences the *flattened*
    # chunk (it does not reset at each row like the TIFF predictor), so a
    # single wrapping cumsum over the whole chunk reverses it.
    delta = Delta(dtype='<u2')
    # Missing chunks decode to the same reflectance as the COG's nodata DN
    # (DN 0 -> -0.1), so "no chunk" and "nodata pixel" read identically.
    fill_value = np.float32((gt.nodata or 0) * scale_factor + add_offset)

    root = zarr.create_group(out, zarr_format=3)
    levels = []
    for i, src in enumerate(sources):
        raster = await src.read()
        data = raster.data[0]  # single band -> (y, x)
        print(f'level {i}: read {data.shape} {data.dtype}, {raster.transform!r}')
        # The scene edge is ragged (e.g. 10980 is not a multiple of 1024), so
        # the chunk grid has partial edge chunks. Zarr v3 still stores those
        # as FULL-size chunk buffers, padded with fill_value beyond the array
        # bounds -- nb02's by-hand decode always reshapes to the full chunk
        # shape from zarr.json, and the padding reads as fill (-0.1). The
        # coarsest level is smaller than one chunk; clamp so its single chunk
        # is exactly the array.
        array = root.create_array(
            str(i),
            shape=data.shape,
            chunks=(min(chunk, data.shape[0]), min(chunk, data.shape[1])),
            dtype='float32',
            fill_value=fill_value,
            filters=[scaling, delta],
            compressors=ZstdCodec(level=ZSTD_LEVEL),
            dimension_names=DIMS,
        )
        array.attrs.update(level_attrs(raster.transform, data.shape, epsg))
        array[:] = (data * scale_factor + add_offset).astype(np.float32)
        # Bit-exact DN recovery is a hard requirement: fail loudly if the
        # scaling codec's float round-trip ever quantizes the source DNs.
        recovered = np.rint((array[:] - add_offset) / scale_factor).astype(np.uint16)
        if not np.array_equal(recovered, data):
            raise SystemExit(
                f'error: level {i} DNs did not round-trip bit-exactly '
                'through the scaling codec'
            )
        levels.append((data.shape, raster.transform))

    group_attrs = level_attrs(levels[0][1], levels[0][0], epsg)
    # resampling_method is the producer's, not ours: Element 84's standard
    # Sentinel-2 COG pipeline builds overviews with average resampling, and we
    # copy those overview pixels verbatim. scale [2, 2] is nominal -- GDAL
    # halves with ceil, so the coarsest levels are 2x only to within a pixel.
    group_attrs |= create_multiscales_layout(
        [{'asset': '0'}]
        + [
            {
                'asset': str(i),
                'derived_from': str(i - 1),
                'transform': {'scale': [2.0, 2.0]},
            }
            for i in range(1, len(levels))
        ],
        resampling_method='average',
    )
    group_attrs['zarr_conventions'] = create_zarr_conventions(
        SpatialConventionMetadata(),
        ProjConventionMetadata(),
        MultiscalesConventionMetadata(),
    )
    root.attrs.update(group_attrs)

    errors = {k: v for k, v in validate_group(root).items() if v}
    if errors:
        raise SystemExit(f'error: store failed convention validation: {errors}')

    chunk_files = [p for p in out.rglob('c/*/*') if p.is_file()]
    total = sum(p.stat().st_size for p in out.rglob('*') if p.is_file())
    largest = max(p.stat().st_size for p in chunk_files)
    print(
        f'wrote {out}: {len(levels)} levels, {len(chunk_files)} chunk files, '
        f'{total / 1e6:.1f} MB total, largest chunk {largest / 1e6:.2f} MB'
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--out',
        type=Path,
        default=Path('./S2B_T10TFR_20231223_B04.zarr'),
        help='output path for the zarr store (default: %(default)s)',
    )
    parser.add_argument(
        '--overwrite',
        action='store_true',
        help='replace the store if it already exists',
    )
    args = parser.parse_args()

    if args.out.exists():
        if not args.overwrite:
            raise SystemExit(f'error: {args.out} exists (use --overwrite)')
        shutil.rmtree(args.out)

    asyncio.run(build(args.out))
    return 0


if __name__ == '__main__':
    sys.exit(main())
