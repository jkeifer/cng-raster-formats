#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.14"
# dependencies = [
#     "async-geotiff>=0.5.1",
#     # Pinned past 0.1.2: the released version still emits the convention
#     # schema/spec URLs with a "v1" tag, which 404s (the conventions tagged
#     # v0.1), and points proj: at the absorbed zarr-experimental org. Commit
#     # fb49f63 "update for v0.1 releases of spatial, multiscales, proj" fixes
#     # both. Revert to a version range once a release past 0.1.2 ships.
#     "geozarr-toolkit @ git+https://github.com/zarr-developers/geozarr-toolkit@fb49f635d229d24ff4accbebbb0ca61098a606a4",
#     "obstore>=0.11.0",
#     "zarr>=3.1.3",
# ]
# ///
"""Convert the nb01/nb03 Sentinel-2 scene into the workshop's Zarr v3 GeoZarr store.

A sparse multi-band scene converter: the store models the ENTIRE source scene
-- every single-band raster asset in the scene's Earth Search STAC item (the
spectral bands plus SCL, AOT, WVP, and the cloud/snow masks; the multi-band
visual/preview composites, thumbnails, and metadata documents are skipped) --
but materializes chunk DATA only for the red band (the B04 COG that exercises
01 and 03 read). Every other band exists purely as metadata: full group +
array structure, correct shapes/transforms/dtypes/codecs, zero chunk files.

The sparseness is a deliberate teaching beat for exercise 02, not a shortcut:
zarr metadata cannot tell you which chunks exist. A missing chunk simply reads
as fill_value -- silently, no error, no manifest anywhere in the store. That
is the chunk-level version of "zarr doesn't solve discovery" (at the catalog
level there is likewise no index of what stores exist), and it sets up
exercise 03's kerchunk/Icechunk manifests, which ARE that missing inventory.
The multi-band structure also gives nb02 a fuller, more realistic GeoZarr
store to explore than a single lonely band.

Where everything comes from: the scene's STAC item URL is the script's single
root input. The item supplies all band metadata (`proj:shape`/`proj:transform`
per asset, `raster:bands` data_type/nodata/scale/offset, `eo:bands`
common_name) -- the other bands' COGs are never opened. The one materialized
band is selected by ASSET KEY in the item, and even its COG URL comes from the
item (the asset href); that band is read for real, in full: base image +
overview IFDs via HTTP range requests (async-geotiff + obstore).

Structure: root group -> one child group per band -> multiscale arrays
``0..N``. Band groups are named by `eo` common_name (B04 -> ``red``, B02 ->
``blue``); assets whose common_name is absent (SCL/AOT/WVP/cloud/snow) or
ambiguous (rededge1/2/3 all share ``rededge``) use their asset key. Bands
live on their native 10/20/60 m grids, shapes and transforms straight from
the item. The proj:/spatial:/multiscales convention attrs live on each BAND
group (validated per group with geozarr-toolkit); the root group carries no
attrs at all -- a v3 root ``zarr.json`` doesn't even list its children, which
is nb02's first taste of the discovery gap.

Pyramids: red's is the COG's own (level ``0`` is the base image, levels
``1..n`` are its overview IFDs, copied pixel-for-pixel). The other bands'
COGs are never read, so their level structure is SYNTHESIZED with the same
deterministic rule the real pyramid follows -- GDAL-style ceil-halving of the
dims until a level fits within one chunk, pixel size rescaled to preserve the
full extent -- and the build asserts that rule reproduces red's actual
pyramid (10980 -> 5490 -> 2745 -> 1373 -> 687) before trusting it for anyone
else. Those claimed pyramids are the store's own design, not read from the
other COGs.

Chunks are uniform 1024x1024 on every level of every band (the red COG's
full-resolution internal tile size, read at runtime; square tiles asserted).

Codecs, per band:

- reflectance bands (and AOT/WVP, which declare their own scale/offset in
  `raster:bands`): ``fixedscaleoffset`` -> ``delta`` -> ``bytes`` -> ``zstd``
  -- the SAME decode recipe exercise 01 performs by hand on a COG tile (undo
  the deflate, undo TIFF predictor 2, apply the DN -> physical scale/offset),
  but declared as explicit codec metadata in ``zarr.json`` so the store
  *tells you* the recipe. Logical dtype float32; the scaling codec encodes to
  the source uint16 DNs (bit-exact for red, asserted at build time), delta
  differences them, zstd compresses.
- unscaled uint8 bands (SCL classification, cloud/snow masks): no scaling
  codec -- class/mask codes have no physical transform to declare -- so the
  chain is just ``delta`` -> ``bytes`` -> ``zstd`` with logical dtype uint8
  and fill from the band's declared nodata.

``dimension_names`` on every array; no CF scale_factor/add_offset attrs
anywhere (scaling lives in the codec chain; CF attrs on top would make xarray
apply it twice).

This script is deliberately standalone (PEP 723 inline metadata) so its deps
stay out of the workshop environment:

    uv run scripts/build_geozarr.py --out ./data/<store>.zarr
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import shutil
import sys
import urllib.request

from collections import Counter
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

# The scene's STAC item is the script's single root input: all band metadata
# comes from it, and the one COG actually read is located by asset key within
# it (its href). Same item nb01 resolves via STAC search against this catalog;
# nb03 hardcodes the same asset's URL.
ITEM_URL = (
    'https://earth-search.aws.element84.com/v1'
    '/collections/sentinel-2-c1-l2a/items/S2B_T10TFR_20231223T190950_L2A'
)
# The one asset whose raster data is materialized; all others are metadata only.
DATA_ASSET = 'red'

DIMS = ['y', 'x']
# Plain zstd rather than blosc(zstd): exercise 02 teaches by-hand chunk reads,
# and a plain-zstd chunk file is a standard zstd frame that any zstd library
# can decode, whereas blosc wraps compressed data in its own framing that only
# blosc understands. Write-once/read-many store, so favor ratio over speed
# (level picked by benchmarking sizes on the delta-encoded data: 13 beat both
# 19 and 22 by a hair, and compresses faster).
ZSTD_LEVEL = 13

# (shape, geotransform) per pyramid level: ((rows, cols), (a, b, c, d, e, f))
Level = tuple[tuple[int, int], tuple[float, ...]]


def fetch_stac_item() -> dict:
    """Fetch the scene's STAC item -- the root input of the whole build."""
    print(f'fetching STAC item {ITEM_URL}')
    with urllib.request.urlopen(ITEM_URL, timeout=30) as resp:
        return json.loads(resp.read())


def band_specs(item: dict) -> dict[str, dict]:
    """Select every single-band raster asset and normalize its metadata.

    Selection rule: assets with exactly one `raster:bands` entry. That keeps
    the spectral bands plus SCL/AOT/WVP and the cloud/snow masks, and drops
    the multi-band visual/preview composites (no or multiple raster:bands),
    the thumbnail, and the metadata documents.

    Group naming: the `eo` common_name where one exists and is unambiguous
    (B04 -> red, B02 -> blue, ...); otherwise the asset key (SCL/AOT/WVP and
    friends have no common_name, and rededge1/2/3 all share `rededge`).
    """
    raw = {}
    for key, asset in item['assets'].items():
        rbands = asset.get('raster:bands')
        if not rbands or len(rbands) != 1:
            continue
        rb = rbands[0]
        # proj:shape / proj:transform may be asset- or item-level in STAC;
        # Earth Search carries them per asset (grids differ: 10/20/60 m).
        shape = asset.get('proj:shape') or item['properties'].get('proj:shape')
        transform = asset.get('proj:transform') or item['properties'].get(
            'proj:transform'
        )
        if shape is None or transform is None:
            raise SystemExit(
                f'error: asset {key!r} has no proj:shape/proj:transform '
                '(asset- or item-level)'
            )
        eo = asset.get('eo:bands') or [{}]
        raw[key] = {
            'asset_key': key,
            'common_name': eo[0].get('common_name'),
            'shape': tuple(shape),
            'transform': tuple(transform[:6]),  # proj: allows a 9-element form
            'data_type': rb['data_type'],
            'nodata': rb.get('nodata', 0),
            'scale': rb.get('scale'),
            'offset': rb.get('offset', 0),
            'href': asset['href'],
        }

    counts = Counter(s['common_name'] for s in raw.values() if s['common_name'])
    specs = {}
    for key, spec in raw.items():
        name = spec['common_name']
        if not name or counts[name] > 1:
            name = key.lower()
        specs[name] = spec
    if len(specs) != len(raw):
        raise SystemExit('error: band group names collide after fallback')
    return specs


def synthesize_pyramid(
    shape: tuple[int, int], transform: tuple[float, ...], chunk: int
) -> list[Level]:
    """Level structure for a band whose COG we never read.

    The same deterministic rule the real red pyramid follows: GDAL-style
    ceil-halving of the dims until a level fits within one chunk, with each
    level's pixel size rescaled so every level spans the exact full-scene
    extent (GDAL overviews preserve extent, so the coarsest levels are 2x
    only to within a pixel and their pixel sizes are non-integer). The build
    asserts this reproduces red's ACTUAL overview structure before using it
    for the metadata-only bands.
    """
    (h0, w0), (a, b, c, d, e, f) = shape, transform
    levels: list[Level] = [(shape, transform)]
    h, w = shape
    while h > chunk or w > chunk:
        h, w = -(-h // 2), -(-w // 2)
        levels.append(((h, w), (a * w0 / w, b, c, d, e * h0 / h, f)))
    return levels


def codec_stack(spec: dict) -> tuple[str, object, list]:
    """(logical dtype, fill_value, filters) for one band.

    Bands with a declared scale/offset (reflectance bands, AOT, WVP) mirror
    nb01's by-hand COG decode as metadata: DN -> physical is a FixedScaleOffset
    codec (logical float32, encoded to the source integer DNs), Delta plays
    the role of TIFF predictor 2 (numcodecs Delta differences the *flattened*
    chunk -- it does not reset per row like the TIFF predictor, so one
    wrapping cumsum reverses it). fill_value is the physical value of the
    band's nodata DN, so missing chunks and nodata pixels read identically.

    Unscaled uint8 bands (SCL classification, cloud/snow masks) have no
    physical transform to declare, so there is no scaling codec: logical
    dtype IS the storage dtype, delta -> zstd only, fill = the nodata code.

    On fill_value vs nodata, because the two are easy to conflate: zarr v3
    defines fill_value as nothing more than "an element value to use for
    uninitialised portions of the array" -- what an ABSENT chunk reads as. It
    is not a declaration that a pixel is invalid, and v3 has no such
    declaration; neither the spatial: nor the proj: convention carries a nodata
    field (that lives in zarr-conventions/missing_value, still at Proposal
    maturity and implemented by nothing). We deliberately set fill_value to the
    nodata DN's PHYSICAL value so absent chunks and nodata pixels read alike,
    which is as close as v3 lets us get.

    Note fill_value is in the DECODED domain -- it is typed by data_type, above
    the codec chain, not below it. Hence nodata * scale + offset rather than the
    raw DN: a raw 0 here would mean a perfectly valid 0.0 reflectance, not
    missing data. (Consumers disagree about all this: GDAL reads fill_value as
    band nodata, while xarray does not mask on it at all for v3 stores.)
    """
    encoded = np.dtype(spec['data_type']).newbyteorder('<').str
    delta = Delta(dtype=encoded)
    if spec['scale'] is not None:
        scaling = FixedScaleOffset(
            offset=spec['offset'],
            scale=1 / spec['scale'],
            dtype='<f4',
            astype=encoded,
        )
        fill = np.float32(spec['nodata'] * spec['scale'] + spec['offset'])
        return 'float32', fill, [scaling, delta]
    return spec['data_type'], spec['nodata'], [delta]


def level_attrs(
    transform: tuple[float, ...], shape: tuple[int, int], epsg: int
) -> dict:
    """spatial: + proj: convention attrs for one resolution level."""
    a, b, c, d, e, f = transform  # row-major 2x3 geotransform
    xmin, ymax = c, f
    xmax = xmin + a * shape[1]
    ymin = ymax + e * shape[0]
    return create_geozarr_attrs(
        dimensions=DIMS,
        crs=f'EPSG:{epsg}',
        transform=[a, b, c, d, e, f],
        bbox=[xmin, ymin, xmax, ymax],
        shape=list(shape),
    )


def create_band_group(
    root: zarr.Group,
    name: str,
    levels: list[Level],
    *,
    spec: dict,
    chunk: int,
    epsg: int,
) -> list[zarr.Array]:
    """One band group: multiscale arrays 0..N + convention attrs, validated."""
    dtype, fill_value, filters = codec_stack(spec)
    group = root.create_group(name)
    arrays = []
    for i, (shape, transform) in enumerate(levels):
        # Ragged edges (e.g. 10980 is not a multiple of 1024) mean partial
        # edge chunks; zarr v3 still stores those as FULL-size chunk buffers
        # padded with fill_value beyond the array bounds. A coarsest level
        # smaller than one chunk gets its chunk clamped to the array shape.
        array = group.create_array(
            str(i),
            shape=shape,
            chunks=(min(chunk, shape[0]), min(chunk, shape[1])),
            dtype=dtype,
            fill_value=fill_value,
            filters=filters,
            compressors=ZstdCodec(level=ZSTD_LEVEL),
            dimension_names=DIMS,
        )
        array.attrs.update(level_attrs(transform, shape, epsg))
        arrays.append(array)

    attrs = level_attrs(levels[0][1], levels[0][0], epsg)
    # For red, resampling_method is the producer's (Element 84's standard
    # Sentinel-2 COG pipeline builds overviews with average resampling, and
    # we copy those pixels verbatim). For the metadata-only bands the pyramid
    # is the store's own design, so the claim is ours: average for continuous
    # bands, nearest for the uint8 class/mask bands (averaging class codes
    # would be meaningless). scale [2, 2] is nominal -- dims halve with ceil,
    # so the coarsest levels are 2x only to within a pixel.
    attrs |= create_multiscales_layout(
        [{'asset': '0'}]
        + [
            {
                'asset': str(i),
                'derived_from': str(i - 1),
                'transform': {'scale': [2.0, 2.0]},
            }
            for i in range(1, len(levels))
        ],
        resampling_method='average' if spec['scale'] is not None else 'nearest',
    )
    attrs['zarr_conventions'] = create_zarr_conventions(
        SpatialConventionMetadata(),
        ProjConventionMetadata(),
        MultiscalesConventionMetadata(),
    )
    group.attrs.update(attrs)

    # validate_group only inspects the attrs of the group it is handed (no
    # recursion into children), so the gate runs here, per band group -- the
    # root group carries no convention attrs to validate.
    errors = {k: v for k, v in validate_group(group).items() if v}
    if errors:
        raise SystemExit(f'error: band {name!r} failed convention validation: {errors}')
    return arrays


async def build(out: Path) -> None:
    item = fetch_stac_item()
    specs = band_specs(item)
    epsg = item['properties']['proj:epsg']
    if epsg != 32610:
        raise SystemExit(f'error: expected EPSG:32610, got EPSG:{epsg}')
    data_band = next(
        (n for n, s in specs.items() if s['asset_key'] == DATA_ASSET), None
    )
    if data_band is None:
        raise SystemExit(
            f'error: the STAC item has no single-band raster asset {DATA_ASSET!r}'
        )
    cog_url = specs[data_band]['href']

    base_url, _, cog_path = cog_url.rpartition('/')
    gt = await GeoTIFF.open(cog_path, store=HTTPStore.from_url(base_url))
    if gt.crs.to_epsg() != epsg:
        raise SystemExit(
            f'error: COG is EPSG:{gt.crs.to_epsg()}, STAC item says EPSG:{epsg}'
        )
    # The store geometry is derived from the red COG: zarr chunks are sized to
    # its full-res internal tiles (square tiles asserted), uniformly across
    # every level of every band -- one chunk-size story for nb02 and fewer
    # chunk files; each level's chunk grid is declared in its own zarr.json
    # regardless.
    if gt.tile_width != gt.tile_height:
        raise SystemExit(
            f'error: COG tiles are {gt.tile_width}x{gt.tile_height}; '
            'the store design assumes square tiles'
        )
    chunk = gt.tile_width
    # The one band we CAN cross-check: the item's scale/offset must match the
    # COG's own TIFF tags, or the codec chains built from the item are wrong.
    spec = specs[data_band]
    if not (
        math.isclose(gt.scales[0], spec['scale'])
        and math.isclose(gt.offsets[0], spec['offset'])
        and (gt.nodata or 0) == spec['nodata']
    ):
        raise SystemExit(
            f'error: STAC raster:bands for {data_band!r} disagrees with the '
            f'COG tags (scale {gt.scales[0]} vs {spec["scale"]}, offset '
            f'{gt.offsets[0]} vs {spec["offset"]}, nodata {gt.nodata} vs '
            f'{spec["nodata"]})'
        )

    # Read red's REAL pyramid: base image + the COG's own overview IFDs,
    # finest to coarsest, copied pixel-for-pixel (no local resampling) -- and
    # assert the synthesis rule used for every other band reproduces it.
    synth = synthesize_pyramid(spec['shape'], spec['transform'], chunk)
    sources = [gt, *gt.overviews]
    if len(sources) != len(synth):
        raise SystemExit(
            f'error: pyramid rule predicts {len(synth)} levels, the COG has '
            f'{len(sources)}'
        )
    print(
        f'converting {len(specs)} bands from the STAC item; data from {cog_url}\n'
        f'  base {gt.shape} @ {gt.transform.a:g} m, {chunk}px tiles -> '
        f'{chunk}px chunks; {len(gt.overviews)} COG overviews'
    )
    red_levels: list[tuple[np.ndarray, Level]] = []
    for i, src in enumerate(sources):
        raster = await src.read()
        data = raster.data[0]  # single band -> (y, x)
        t = raster.transform
        transform = (t.a, t.b, t.c, t.d, t.e, t.f)
        s_shape, s_transform = synth[i]
        if data.shape != s_shape or not all(
            math.isclose(u, v, rel_tol=1e-9, abs_tol=1e-9)
            for u, v in zip(transform, s_transform, strict=True)
        ):
            raise SystemExit(
                f'error: level {i} pyramid rule mismatch: COG has '
                f'{data.shape} {transform}, rule gives {s_shape} {s_transform}'
            )
        print(f'level {i}: read {data.shape} {data.dtype}, {raster.transform!r}')
        red_levels.append((data, (data.shape, transform)))

    # Root group: NO attrs, deliberately. Conventions live per band group
    # (each band has its own grid), and a v3 root zarr.json doesn't even list
    # its children -- nb02's first look at the discovery gap.
    root = zarr.create_group(out, zarr_format=3)
    for name in sorted(specs):
        spec = specs[name]
        if name == data_band:
            levels = [lvl for _, lvl in red_levels]
        else:
            levels = synthesize_pyramid(spec['shape'], spec['transform'], chunk)
        arrays = create_band_group(
            root, name, levels, spec=spec, chunk=chunk, epsg=epsg
        )
        res = spec['transform'][0]
        tag = 'DATA' if name == data_band else 'metadata only'
        print(
            f'band {name}: {len(levels)} levels, {spec["shape"][0]}x'
            f'{spec["shape"][1]} @ {res:g} m, {spec["data_type"]} ({tag})'
        )
        if name != data_band:
            continue  # every other band: arrays exist, no chunks are written

        for i, (array, (data, _)) in enumerate(zip(arrays, red_levels, strict=True)):
            array[:] = (data * spec['scale'] + spec['offset']).astype(np.float32)
            # Bit-exact DN recovery is a hard requirement: fail loudly if the
            # scaling codec's float round-trip ever quantizes the source DNs.
            recovered = np.rint((array[:] - spec['offset']) / spec['scale'])
            if not np.array_equal(recovered.astype(data.dtype), data):
                raise SystemExit(
                    f'error: level {i} DNs did not round-trip bit-exactly '
                    'through the scaling codec'
                )

    chunk_files = [p for p in out.rglob('c/*/*') if p.is_file()]
    stray = [p for p in chunk_files if p.relative_to(out).parts[0] != data_band]
    if stray:
        raise SystemExit(f'error: chunk files exist outside {data_band!r}: {stray[:5]}')
    total = sum(p.stat().st_size for p in out.rglob('*') if p.is_file())
    largest = max(p.stat().st_size for p in chunk_files)
    print(
        f'wrote {out}: {len(specs)} bands, {len(chunk_files)} chunk files '
        f'(all under {data_band!r}), {total / 1e6:.1f} MB total, '
        f'largest chunk {largest / 1e6:.2f} MB'
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--out',
        type=Path,
        default=Path('./S2B_T10TFR_20231223.zarr'),
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
