# %% [markdown]
# # Free-Range Artisanal Grass-Fed Kerchunk
#
# Exercise 2 ended on a cliffhanger: zarr's layout and access story is excellent, but its discovery story is "bring your own manifest". Nothing in a zarr store can tell you which chunks exist or where their bytes live--the metadata describes what the data *would* look like, and absence silently reads as fill.
#
# But think back to exercise 1. The COG *had* a manifest: the `tile_offsets` (324) and `tile_byte_counts` (325) tags were a complete inventory of every tile in the file--exactly which image segments exist, exactly where their bytes live. Clunky to parse, but a real inventory. It was just *internal*: locked inside the TIFF's binary structure, in the file itself.
#
# So here's the idea this whole exercise turns on: what if we wrote that internal inventory down *externally*, in a document shaped like a zarr store? Metadata documents saying "here is an array, here is its shape and decode recipe", plus a mapping from each chunk key to a `(url, byte offset, byte length)` triple pointing into the original COG. A zarr reader could then read the COG's bytes--without the COG ever knowing, and without copying a single pixel. That document is a *kerchunk reference file*, and in this exercise we're going to build one by hand for the very same B04 COG from exercise 1.
#
# Then, because hand-writing JSON is nobody's idea of production tooling, we'll finish with the modern descendants of this idea: opening our references as *virtual arrays* with VirtualiZarr, and committing them to *Icechunk*, where the manifest becomes versioned, transactional data in its own right.
#
# The usual imports first.

# %%
import json
import math

from pathlib import Path

import numpy as np

# %% [markdown]
# ## Our COG's vital statistics
#
# Everything we need to describe the COG we already dug out of its IFD in exercise 1--we're just going to reuse those findings rather than re-parse the file. Here they are, copied out of exercise 1's outputs, with the TIFF tag each fact came from:
#
# * the image and tile dimensions (tags 256/257, 322/323)
# * the compression scheme: `8`, i.e. DEFLATE (tag 259)
# * the predictor: `2`, horizontal differencing (tag 317)
# * the stored data type: `uint16` digital numbers (tags 258/339)
# * the scale/offset hiding in the GDAL XML (tag 42112) and the nodata DN (tag 42113)
# * and the manifest itself: every tile's byte offset (tag 324) and byte length (tag 325)
#
# Take a moment with the `offsets` and `lengths` tuples--those 121 pairs *are* the inventory this whole exercise is about. Everything else here is just enough context to decode what they point at.

# %%
tiff_attrs = {
    'href': 'https://e84-earth-search-sentinel-data.s3.us-west-2.amazonaws.com/sentinel-2-c1-l2a/10/T/FR/2023/12/S2B_T10TFR_20231223T190950_L2A/B04.tif',
    'size': {
        'rows': 10980,
        'cols': 10980,
    },
    'compression': 'deflate',
    'predictor': 2,
    'dtype': '<u2',
    'nodata': 0,
    'scale': 0.0001,
    'offset': -0.1,
    'tiles': {
        'size': {
            'rows': 1024,
            'cols': 1024,
        },
        'offsets': (
            55962680,
            57411167,
            58810332,
            60222446,
            61651003,
            63054996,
            64463518,
            66025043,
            67523672,
            68987825,
            70439668,
            71480485,
            72831139,
            74191906,
            75556803,
            76922917,
            78346396,
            79767466,
            81177106,
            82626646,
            84045343,
            85436959,
            86443457,
            87744763,
            89128625,
            90516041,
            91896145,
            93323921,
            94699513,
            96054131,
            97398784,
            98768288,
            100117176,
            101099165,
            102475360,
            103914015,
            105337327,
            106767167,
            108155055,
            109496290,
            110853634,
            112244713,
            113588526,
            114895196,
            115881834,
            117297939,
            118737048,
            120185270,
            121620456,
            123031867,
            124402930,
            125797422,
            127166585,
            128512496,
            129847193,
            130813023,
            132267746,
            133721219,
            135168258,
            136590051,
            138004961,
            139387400,
            140792216,
            142173401,
            143531515,
            144883653,
            145909014,
            147512228,
            148965842,
            150393926,
            151820955,
            153228408,
            154629691,
            156014882,
            157380367,
            158731976,
            160114338,
            161151032,
            162782880,
            164279805,
            165702744,
            167136236,
            168547793,
            169940007,
            171321112,
            172637466,
            174003270,
            175392224,
            176416464,
            178052532,
            179640701,
            181092961,
            182534128,
            183924802,
            185311293,
            186651878,
            187954039,
            189327902,
            190698439,
            191714854,
            193331795,
            194939195,
            196415899,
            197819251,
            199217398,
            200625142,
            201991437,
            203345078,
            204717082,
            206137392,
            207171477,
            208347309,
            209482357,
            210584255,
            211625167,
            212683632,
            213739512,
            214787222,
            215844136,
            216879023,
            217929856,
        ),
        'lengths': (
            1448479,
            1399157,
            1412106,
            1428549,
            1403985,
            1408514,
            1561517,
            1498621,
            1464145,
            1451835,
            1040809,
            1350646,
            1360759,
            1364889,
            1366106,
            1423471,
            1421062,
            1409632,
            1449532,
            1418689,
            1391608,
            1006490,
            1301298,
            1383854,
            1387408,
            1380096,
            1427768,
            1375584,
            1354610,
            1344645,
            1369496,
            1348880,
            981981,
            1376187,
            1438647,
            1423304,
            1429832,
            1387880,
            1341227,
            1357336,
            1391071,
            1343805,
            1306662,
            986630,
            1416097,
            1439101,
            1448214,
            1435178,
            1411403,
            1371055,
            1394484,
            1369155,
            1345903,
            1334689,
            965822,
            1454715,
            1453465,
            1447031,
            1421785,
            1414902,
            1382431,
            1404808,
            1381177,
            1358106,
            1352130,
            1025353,
            1603206,
            1453606,
            1428076,
            1427021,
            1407445,
            1401275,
            1385183,
            1365477,
            1351601,
            1382354,
            1036686,
            1631840,
            1496917,
            1422931,
            1433484,
            1411549,
            1392206,
            1381097,
            1316346,
            1365796,
            1388946,
            1024232,
            1636060,
            1588161,
            1452252,
            1441159,
            1390666,
            1386483,
            1340577,
            1302153,
            1373855,
            1370529,
            1016407,
            1616933,
            1607392,
            1476696,
            1403344,
            1398139,
            1407736,
            1366287,
            1353633,
            1371996,
            1420302,
            1034077,
            1175824,
            1135040,
            1101890,
            1040904,
            1058457,
            1055872,
            1047702,
            1056906,
            1034879,
            1050825,
            763422,
        ),
    },
}

# %% [markdown]
# ### A note on data type
#
# The COG stores `uint16` digital numbers (DNs), but as we learned in exercise 1 they *represent* float reflectance via a scale and offset a reader may or may not notice. In exercise 2 we saw the zarr answer to that ambiguity: make scaling part of the declared codec chain, so the array's canonical data type is `float32` reflectance and every reader gets physical values. We're writing the metadata this time, which means *we* choose the contract--and we'll choose the exercise 2 contract. Our array will declare `float32`, with the DN business handled inside the codec pipeline.
#
# ## What documents do we need?
#
# We're describing a zarr v3 store, so the decoder ring from exercise 2 tells us exactly what to write. Every node gets one `zarr.json`--no `.zgroup`/`.zarray`/`.zattrs` scatter--and chunks live at `c/{row}/{col}` keys:
#
# * `zarr.json`: the root group document
# * `red/zarr.json`: the array document for our band (we'll keep the name `red`, matching both the STAC asset's common name and the band group in exercise 2's store)
# * `red/c/{row}/{col}`: one entry per chunk--and these are the special ones
#
# In a real zarr store those chunk keys name objects full of compressed bytes. In a kerchunk reference file they instead map to a `[url, offset, length]` triple: "the bytes for this chunk are *over there*". The metadata documents ride along inline (as JSON text), so opening the store touches nothing but the reference file until actual chunk data is requested.
#
# A historical note: the kerchunk JSON container format (a `refs` mapping, optionally with templates for repetitive URLs) dates from the zarr v2 era, and most references in the wild still carry v2 metadata documents. But the format itself is agnostic--it's just a mapping from key names to inline data or byte ranges--so nothing stops us from putting v3 documents in it. That's what we'll do, keeping our vocabulary consistent with exercise 2. We'll skip templating; plain refs generated from a loop are easier to write and to check.
#
# ## Writing the recipe ourselves
#
# The heart of the array document is the `codecs` pipeline. In exercise 2 we *read* a declared recipe and marveled that we didn't have to go spelunking for it. Now the shoe is on the other foot: the bytes in the COG are already encoded, GDAL isn't going to change them for us, and our declaration must describe--exactly--what GDAL did. Flip exercise 2's table around:
#
# | What GDAL did (encode direction)                  | Where the COG said so       | What we must declare              |
# | ------------------------------------------------- | --------------------------- | --------------------------------- |
# | float reflectance → uint16 DNs via scale/offset    | `GDAL_METADATA` tag (42112) | `numcodecs.fixedscaleoffset`      |
# | difference each value from its left neighbor       | `predictor` tag (317) = 2   | ...we need to talk               |
# | serialize values little-endian                     | the `II` byte-order mark    | `bytes` with `endian: little`     |
# | compress each tile with DEFLATE                    | `compression` tag (259) = 8 | `numcodecs.zlib`                  |
#
# Three of the four rows are easy. The scale/offset codec can be copied *verbatim* from exercise 2's store--same scene, same band, same DN-to-reflectance mapping. The byte order and compression have stock codecs. But that second row...
#
# ### The predictor problem
#
# Remember the footnote from exercise 2, when we decoded the quicklook chunk? TIFF's predictor 2 restarts its differencing at every row, while the `numcodecs` delta codec differences the *flattened* chunk--one long run, no row resets. Back then it was trivia explaining why our cumulative sum had no `axis` argument. Now it has teeth: exercise 2's store could use `numcodecs.delta` because it *re-encoded* the pixels with that exact (flattened) transform. We are pointing zarr at bytes GDAL wrote, per-row differencing and all. If the declared codec doesn't match the actual encoding, we don't get an error--we get wrong numbers.
#
# Don't take that on faith. Build a toy 2 x 3 array, difference it the way TIFF predictor 2 does (each row independently, first value absolute), and then decode those differences with the `numcodecs` delta codec. If the two schemes really were interchangeable, we'd get our toy back.

# %%
#| scrub-note: cell0
from numcodecs import Delta

toy = np.array([[10, 11, 12], [1000, 1001, 1002]], dtype='<u2')
toy_tiff_encoded = toy.copy()
toy_tiff_encoded[:, 1:] = np.diff(toy, axis=1)

print('original:')
print(toy)
print('as stored by TIFF predictor 2:')
print(toy_tiff_encoded)
print('numcodecs delta decode of those bytes:')
print(Delta(dtype='<u2').decode(toy_tiff_encoded.tobytes()).reshape(2, 3))

# %% [markdown]
# **Question**: What happened to the second row, and why? Would this kind of error be easy to spot in real imagery?

# %% [markdown]
# <!-- scrub-omit -->
# **Answer**: The flattened cumulative sum never resets, so row 1's absolute first value (1000) gets added on top of row 0's final value (12), and the entire second row comes out shifted by 12. In a full 1024 x 1024 tile every row after the first inherits the accumulated garbage of all the rows above it (wrapping modulo 65536, for extra spice), so *only row 0 decodes correctly*. And no, it would not necessarily be easy to spot: the values are plausible-looking numbers, not obvious noise--exactly the kind of silent wrongness that makes "declare the recipe correctly" matter. (Fun fact: the previous edition of this workshop declared `delta` in its hand-built references and never noticed.)

# %% [markdown]
# ### Writing our own codec
#
# So there is no stock codec for TIFF's per-row predictor. Are we stuck? Not at all--zarr v3's codec pipeline is extensible by design. A codec is a small class with an encode transform, a decode transform, and a name to register it under; ours needs about twenty-five lines. Decoding is a cumulative sum along the last axis (the per-row version of what we did by hand in exercises 1 and 2), and encoding is its inverse, a per-row difference.

# %%
from dataclasses import dataclass

from zarr.abc.codec import ArrayArrayCodec
from zarr.registry import register_codec


@dataclass(frozen=True)
class TiffPredictor2(ArrayArrayCodec):
    """Reverses TIFF predictor=2, horizontal differencing restarting each row."""

    is_fixed_size = True

    @classmethod
    def from_dict(cls, data):
        return cls()

    def to_dict(self):
        return {'name': 'tiff.predictor2'}

    async def _decode_single(self, chunk_array, chunk_spec):
        diffs = chunk_array.as_ndarray_like()
        return chunk_spec.prototype.nd_buffer.from_ndarray_like(
            np.cumsum(diffs, axis=-1, dtype=diffs.dtype),
        )

    async def _encode_single(self, chunk_array, chunk_spec):
        values = chunk_array.as_ndarray_like()
        diffs = values.copy()
        diffs[..., 1:] = np.diff(values, axis=-1)
        return chunk_spec.prototype.nd_buffer.from_ndarray_like(diffs)

    def compute_encoded_size(self, input_byte_length, chunk_spec):
        return input_byte_length


register_codec('tiff.predictor2', TiffPredictor2)

# %% [markdown]
# **An honest cost, stated loudly**: our references now decode correctly, but only in an environment where a codec named `tiff.predictor2` is registered. Hand this reference file to someone else and their zarr will refuse it. This is the fundamental tradeoff of virtualizing bytes you didn't encode: formats whose transforms map onto standard codecs (netCDF4/HDF5's chunk compression, for instance--the case kerchunk was invented for) virtualize cleanly, while formats with bespoke encodings need custom codecs at every reader. It's also precisely why exercise 2's store *re-encoded* the pixels into standard codecs instead of referencing the COG's bytes: a store you write yourself can promise portability that a store you merely point at cannot.
#
# ## Building the array document
#
# Now we can assemble `red/zarr.json`. We built one of these from a live example in exercise 2 (`red/0/zarr.json` in the store--worth a side-by-side look afterwards); the fields we need:
#
# * `zarr_format` / `node_type`: `3`, and this node is an `array`
# * `shape`: the image dimensions, `(row, col)` order
# * `data_type`: `float32`--the canonical type, per our contract discussion
# * `chunk_grid`: regular, with the COG's tile size as the chunk shape (at full resolution the tiles and chunks correspond 1:1, as we confirmed in exercise 2)
# * `chunk_key_encoding`: the default `c/`-style keys with `/` separators
# * `fill_value`: the *physical* value of the nodata DN: `0 * 0.0001 + -0.1 = -0.1`, matching exercise 2's store
# * `codecs`: the four-step recipe we just worked out, in encode order
# * `dimension_names`: `y` then `x`
# * `attributes`: and while we're writing metadata anyway, we can throw in the `proj:`/`spatial:` conventions from exercise 2--the COG's geo keys and tie point, reborn as three JSON attributes (we'll skip the formal `zarr_conventions` declarations for brevity)

# %%
#| scrub-note: cell1
red_zarr_json = {
    'zarr_format': 3,
    'node_type': 'array',
    'shape': [
        tiff_attrs['size']['rows'],
        tiff_attrs['size']['cols'],
    ],
    'data_type': 'float32',
    'chunk_grid': {
        'name': 'regular',
        'configuration': {
            'chunk_shape': [
                tiff_attrs['tiles']['size']['rows'],
                tiff_attrs['tiles']['size']['cols'],
            ],
        },
    },
    'chunk_key_encoding': {
        'name': 'default',
        'configuration': {'separator': '/'},
    },
    'fill_value': -0.1,
    'codecs': [
        {
            'name': 'numcodecs.fixedscaleoffset',
            'configuration': {
                'offset': tiff_attrs['offset'],
                'scale': 1 / tiff_attrs['scale'],
                'dtype': '<f4',
                'astype': tiff_attrs['dtype'],
            },
        },
        {
            'name': 'tiff.predictor2',
        },
        {
            'name': 'bytes',
            'configuration': {'endian': 'little'},
        },
        {
            'name': 'numcodecs.zlib',
            'configuration': {'level': 6},
        },
    ],
    'dimension_names': ['y', 'x'],
    'attributes': {
        'proj:code': 'EPSG:32610',
        'spatial:shape': [10980, 10980],
        'spatial:transform': [10.0, 0.0, 600000.0, 0.0, -10.0, 5100000.0],
    },
}

# %% [markdown]
# (One footnote on `numcodecs.zlib`: its `level` only matters when *encoding*--DEFLATE streams don't care what level made them when decoding--so any value is fine for read-only references. The scale in `fixedscaleoffset` is the inverse of the TIFF's 0.0001, exactly as exercise 2's store declared it.)
#
# ## Building the manifest
#
# Time for the main event: the chunk references. Walk the 11 x 11 tile grid in row-major order (the same linear indexing we used with `tile_offsets` in exercise 1), and for each tile emit a `red/c/{row}/{col}` key mapping to `[href, offset, length]`. The two metadata documents go in as inline JSON strings, and the whole thing gets the kerchunk version-1 wrapper: `{'version': 1, 'refs': {...}}`.

# %%
#| scrub-note: cell2
tile_rows = math.ceil(tiff_attrs['size']['rows'] / tiff_attrs['tiles']['size']['rows'])
tile_cols = math.ceil(tiff_attrs['size']['cols'] / tiff_attrs['tiles']['size']['cols'])

refs = {
    'zarr.json': json.dumps(
        {
            'zarr_format': 3,
            'node_type': 'group',
            'attributes': {},
        }
    ),
    'red/zarr.json': json.dumps(red_zarr_json),
}

for tile_row in range(tile_rows):
    for tile_col in range(tile_cols):
        tile_index = (tile_cols * tile_row) + tile_col
        refs[f'red/c/{tile_row}/{tile_col}'] = [
            tiff_attrs['href'],
            tiff_attrs['tiles']['offsets'][tile_index],
            tiff_attrs['tiles']['lengths'][tile_index],
        ]

json_file = Path('./kerchunk.json')
json_file.write_text(json.dumps({'version': 1, 'refs': refs}))

print(f'{len(refs)} keys ({tile_rows * tile_cols} chunk references)')
print(f'red/c/7/0 -> {refs["red/c/7/0"]}')

# %% [markdown]
# **Question**: In exercises 1 and 2 our POI pixel lived in tile/chunk (7, 0). Do the offset and length in `red/c/7/0` match what exercise 1's tag parsing found for that tile?

# %% [markdown]
# <!-- scrub-omit -->
# **Answer**: They must--they're the same numbers. Tile (7, 0) is linear index 77 (7 x 11 + 0) in the row-major tile order, and entry 77 of the `tile_offsets`/`tile_byte_counts` tags is offset 161,151,032 with length 1,631,840. Our loop copied exactly those values into the `red/c/7/0` reference. The manifest isn't *derived from* the COG's inventory; it *is* the COG's inventory, transcribed.

# %% [markdown]
# ## Watching the bytes: a logging HTTP client
#
# Before we open our creation, let's set up some instrumentation. The claim behind this whole exercise is that a zarr reader will fetch *exactly* the byte ranges our manifest dictates--no more, no less. To verify that we want to see every HTTP request as it happens, `Range` header and all.
#
# The reference filesystem we're about to use fetches remote data with `aiohttp`, and it accepts a `get_client` hook for supplying the client session. Earlier editions of this notebook subclassed `aiohttp.ClientSession` to intercept requests ("`LoggingClientSession`"); aiohttp now discourages subclassing, so we use its supported tracing hooks instead--same device, modern implementation.

# %%
import aiohttp


async def log_request(session, context, params):
    range_header = params.headers.get('Range', 'no byte range')
    print(f'{params.method} {params.url} ({range_header})')


async def get_client(**kwargs):
    trace_config = aiohttp.TraceConfig()
    trace_config.on_request_start.append(log_request)
    return aiohttp.ClientSession(trace_configs=[trace_config], **kwargs)


# %% [markdown]
# ## Opening the references
#
# The reference file is opened through fsspec's `reference://` filesystem: a filesystem whose "files" are the keys of our refs mapping--inline content served directly, byte-range triples fetched from the target URL on demand. Zarr 3 drives fsspec asynchronously, so both the reference filesystem and the remote HTTPS filesystem under it need `asynchronous=True`, and we wrap the result in zarr's `FsspecStore`.
#
# (A quality-of-life note: fsspec caches filesystem instances by their constructor arguments, which in an earlier edition of this exercise meant edits to the reference file were invisible until a kernel restart. `skip_instance_cache=True` opts out of that cache--tweak, rerun, no restart.)

# %%
#| scrub-note: cell3
import fsspec
import zarr

fs = fsspec.filesystem(
    'reference',
    fo=str(json_file),
    remote_protocol='https',
    remote_options={
        'get_client': get_client,
        'asynchronous': True,
    },
    skip_instance_cache=True,
    asynchronous=True,
)
store = zarr.storage.FsspecStore(fs)
store

# %% [markdown]
# ### The payoff exercise 2 couldn't give us
#
# In exercise 2, `zarr.open_group(...).keys()` against the store returned an empty list--over plain HTTP there was no way to list keys, and the metadata declared no children. Let's ask the exact same question of our reference store.

# %%
#| scrub-note: cell4
root_group = zarr.open_group(store, mode='r')
sorted(root_group.keys())

# %% [markdown]
# There it is: a *listing*. Same zarr library, same question, opposite answer--because this store has what the plain-HTTP store lacked: an inventory. The reference filesystem knows every key that exists (they're right there in the refs mapping), so enumeration finally works. And notice what our logging client printed while we did all this metadata work: nothing. The `zarr.json` documents were served inline from the reference file; the COG hasn't received a single request yet.
#
# Let's grab the array and look it over.

# %%
#| scrub-note: cell5
red_array = root_group['red']
red_array.info

# %% [markdown]
# A 10980 x 10980 float32 array with 1024 x 1024 chunks and our four-codec pipeline--which is to say, zarr believes every word we wrote. As far as any reader can tell this is an ordinary zarr v3 array; the fact that its chunk bytes live inside a GeoTIFF on another continent is invisible plumbing.
#
# xarray works too, and this time--unlike exercise 2's zero-data-variables disappointment--it can actually discover the array, because discovery is just listing, and listing now works:

# %%
#| scrub-note: cell6
import xarray

dataset = xarray.open_zarr(store, consolidated=False)
dataset

# %% [markdown]
# One data variable, `red`, with dimensions `y` and `x` straight from our `dimension_names`. Note that no pixel data has moved yet: like every good cloud-native access pattern, everything so far is lazy.
#
# ## Reading our pixel
#
# Time to close the loop. In exercise 1 we found our POI at pixel (7471, 211) by chasing geo keys and affine math through TIFF tags; in exercise 2 the convention attributes handed us the same answer. It's the same grid here, so let's read that exact pixel and watch what happens on the wire.

# %%
#| scrub-note: cell7
poi_reflectance = float(dataset.red[7471, 211].values)
print(f'POI red reflectance: {poi_reflectance:.4f}')

# %% [markdown]
# **Question**: Compare the logged byte range against the `red/c/7/0` reference (and exercise 1's tag values). And is that reflectance the number we've seen twice before?

# %% [markdown]
# <!-- scrub-omit -->
# **Answer**: The request was `bytes=161151032-162782871`--start equal to the manifest's offset, end equal to offset + length - 1. That is byte-for-byte the range exercise 1 computed from tags 324/325 for tile (7, 0). And the value is 0.2736, from DN 3736, identical to exercises 1 and 2 (and this time it flowed through *four* declared codecs, including our hand-rolled predictor reverser--had we lazily declared `numcodecs.delta` instead, row 303 of that chunk would have decoded to nonsense).

# %% [markdown]
# ## Reading across chunks
#
# What about a window spanning two neighboring tiles? Tiles (7, 0) and (7, 1) are adjacent in the image *and* nearly adjacent in the file--(7, 0)'s bytes end at 162,782,871 and (7, 1)'s begin at 162,782,880, a gap of 8 bytes. Let's read a window covering both and see how the requests come out.

# %%
#| scrub-note: cell8
two_tiles = dataset.red[7168:8192, 0:2048].values
two_tiles.shape

# %% [markdown]
# Two requests, one per chunk, each with exactly its own manifest range--issued concurrently. If you used this notebook's earlier edition (or GDAL), you might have expected the two nearly-touching ranges to be coalesced into a single request; that's a real optimization some clients perform, but zarr's store interface fetches each chunk key independently and leans on concurrency instead. The manifest's job is the same either way: it supplies the exact ranges; request-shaping is client strategy on top.
#
# And when the chunks *aren't* neighbors in the file? Tiles (7, 0) and (8, 0) are vertically adjacent in the image, but row-major layout puts roughly 14 MB of other tiles between them in the COG.

# %%
#| scrub-note: cell9
two_tiles_apart = dataset.red[7168:9216, 0:1024].values
two_tiles_apart.shape

# %% [markdown]
# Again two exact ranges, this time far apart--and not a byte fetched from the 14 MB between them. That's the manifest earning its keep: precise addressing into a file laid out for somebody else's access pattern.
#
# ## From artisanal to industrial: VirtualiZarr
#
# Nobody builds reference files by hand outside a workshop. The `kerchunk` package that pioneered this idea ships extractors that scan netCDF/HDF5, GRIB, TIFF, and friends and emit reference JSON automatically. But JSON files of chunk references have real limits--they get enormous (millions of chunks means millions of JSON entries), they're all-or-nothing to update, and a bare `{'version': 1, 'refs': ...}` mapping is a data model only a filesystem could love.
#
# The modern toolchain splits the idea into two proper layers. **VirtualiZarr** gives manifests a first-class in-memory model: a `ManifestArray` is zarr v3 array metadata plus a chunk manifest, and it lives inside ordinary xarray datasets as a *virtual* variable--all the structure, none of the bytes. **Icechunk** (next section) gives them a durable home. VirtualiZarr ships parsers for the kerchunk JSON format, but they expect the v2-era metadata documents that format historically carried; our references are v3-shaped, so rather than translate backwards we'll do something more instructive: build the VirtualiZarr objects directly and see that they are *exactly the pieces we already made*. A chunk manifest first--our reference triples, restructured:

# %%
#| scrub-note: cell10
from virtualizarr.manifests import ChunkManifest

chunk_entries = {}
for key, ref in refs.items():
    if not key.startswith('red/c/'):
        continue
    path, offset, length = ref
    chunk_entries[key.removeprefix('red/c/')] = {
        'path': path,
        'offset': offset,
        'length': length,
    }

chunk_manifest = ChunkManifest(
    chunk_entries,
    shape=(tile_rows, tile_cols),
    separator='/',
)
chunk_manifest

# %% [markdown]
# Then the manifest plus our array document make a `ManifestArray`; a `ManifestGroup` holds it (that's our root group document); and a `ManifestStore` binds the group to an object-store registry that says which store handles URLs under the COG's prefix--VirtualiZarr does its I/O through `obstore` rather than fsspec, so we hand it an `HTTPStore` for the bucket's HTTPS endpoint.

# %%
#| scrub-note: cell11
from obstore.store import HTTPStore
from obspec_utils.registry import ObjectStoreRegistry
from virtualizarr.manifests import ManifestArray, ManifestGroup, ManifestStore
from zarr.core.metadata.v3 import ArrayV3Metadata

url_prefix = 'https://e84-earth-search-sentinel-data.s3.us-west-2.amazonaws.com'

manifest_array = ManifestArray(
    metadata=ArrayV3Metadata.from_dict(red_zarr_json),
    chunkmanifest=chunk_manifest,
)
manifest_store = ManifestStore(
    group=ManifestGroup(arrays={'red': manifest_array}, attributes={}),
    registry=ObjectStoreRegistry({url_prefix: HTTPStore.from_url(url_prefix)}),
)
manifest_store

# %% [markdown]
# (Note that `ArrayV3Metadata.from_dict` accepted our hand-built document as-is--custom codec and all, since we registered it--which is a nice confirmation that what we wrote really is well-formed v3 array metadata.)
#
# From the store we can get a *virtual dataset*: an xarray dataset whose variables wrap `ManifestArray`s instead of loaded (or lazily-loadable) numpy data.

# %%
#| scrub-note: cell12
virtual_dataset = manifest_store.to_virtual_dataset()
virtual_dataset

# %% [markdown]
# It looks almost like the dataset we opened through fsspec--except the `red` variable's data is literally a `ManifestArray`. This dataset can't compute anything; it exists to *describe*. Its real superpower is size:

# %%
print(f'apparent dataset size: {virtual_dataset.nbytes / 1e6:.0f} MB')
print(f'actual size in memory: {virtual_dataset.vz.nbytes / 1e3:.0f} kB')

# %% [markdown]
# Half a gigabyte of Sentinel 2 imagery, represented in a few kilobytes of metadata and offsets. Virtual datasets for *thousands* of scenes fit comfortably in memory, get concatenated with ordinary `xarray.concat` calls, and--the payoff--get written to a reference store in one shot.
#
# ## A manifest with a memory: Icechunk
#
# So where should a manifest *live*? A JSON file was our v1 answer, with the limits noted above. **Icechunk** is the modern one: a zarr v3 store (Rust core, open spec) whose contents--metadata, chunk data, *and virtual chunk references*--are managed like a git repository. Writes happen in transactions; every commit produces an immutable snapshot; readers can time-travel. The inventory zarr never had is not just bolted on here--it's versioned data with a history.
#
# An Icechunk repository lives in object storage or on disk; for the workshop we'll keep it in memory. The one wrinkle virtual references add: a repository must be explicitly configured--and each session explicitly authorized--to fetch bytes from foreign locations, via a *virtual chunk container* declaring the URL prefix and how to access it (anonymous HTTPS, for us). A stolen manifest shouldn't get to exfiltrate your credentials to arbitrary URLs.

# %%
import icechunk

container_prefix = f'{url_prefix}/'

repo_config = icechunk.RepositoryConfig.default()
repo_config.set_virtual_chunk_container(
    icechunk.VirtualChunkContainer(container_prefix, icechunk.http_store()),
)

repo = icechunk.Repository.create(
    icechunk.in_memory_storage(),
    config=repo_config,
    authorize_virtual_chunk_access={
        container_prefix: icechunk.credentials.HttpAccess,
    },
)
repo

# %% [markdown]
# Writing our virtual dataset into it is a session, a write, and a commit:

# %%
#| scrub-note: cell13
session = repo.writable_session('main')
virtual_dataset.vz.to_icechunk(session.store)
snapshot_id = session.commit('add virtual references to the S2 B04 COG')
snapshot_id

# %% [markdown]
# That commit is a durable, atomic snapshot: the array metadata plus a binary chunk manifest recording, for every chunk, either its own stored bytes or a virtual reference into our COG. Reading it back is just zarr-and-xarray-as-usual against a (read-only) session's store:

# %%
#| scrub-note: cell14
readonly_session = repo.readonly_session(branch='main')
ic_dataset = xarray.open_zarr(readonly_session.store, consolidated=False)
print(f'POI red reflectance: {float(ic_dataset.red[7471, 211].values):.4f}')

# %% [markdown]
# The same reflectance, one more time. (No request appeared in our log because Icechunk fetches virtual chunks with its own internal HTTP client, not aiohttp--but it issued the same range read our manifest dictates. Note also that our custom codec caveat followed us here: this repository's array still declares `tiff.predictor2`, so its readers need that codec too.)
#
# And because the manifest is now *versioned data*, we can interrogate it like data--list every foreign location this repository would touch, or walk its commit history:

# %%
#| scrub-note: cell15
print(set(readonly_session.all_virtual_chunk_locations()))
for snapshot in repo.ancestry(branch='main'):
    print(f'{snapshot.id}: {snapshot.message}')

# %% [markdown]
# One external dependency, two commits (ours, plus the repository-initialization commit), and a growing history from here: append tomorrow's scene as a new commit, and yesterday's analysis can still pin yesterday's snapshot. Transactional updates, safe concurrent readers, time travel--for what started this notebook as a JSON file of byte offsets.
#
# One final honesty check, because virtual references of any flavor--JSON, VirtualiZarr, Icechunk--share a load-bearing assumption: *the source files don't change*. Our manifest describes byte ranges in somebody else's bucket; if that COG is ever rewritten, recompressed, or deleted, every reference into it silently rots (Icechunk can at least track a `last_updated_at` timestamp per reference and refuse ones that have gone stale). A manifest is an inventory, not a custody arrangement. When you need the latter, you re-encode and own the bytes--which is exactly the choice exercise 2's store made.
#
# ## Full circle
#
# The thread we've pulled across three exercises, in one paragraph: the COG kept a manifest *inside* the file (tile offset tags--an inventory, but locked in binary and invisible to zarr tooling). Zarr computed its addressing and kept *no* manifest (elegant reads, but absence is silent and listing is a prayer). Kerchunk's insight was that the manifest deserves to be *data*: pull the inventory out, write it down, and any zarr reader can consume anything with a byte layout you can describe. VirtualiZarr made that idea composable; Icechunk made it durable, versioned, and transactional. Discovery was never going to solve itself--somebody always has to write the inventory down. Now you've done it by hand, once, and you know exactly what the fancy tools are writing.

# %% [markdown]
# ## Additional exercises to consider later
#
# * Our manifest covers only the COG's full-resolution IFD. Add the overview IFDs as additional arrays (`red_2`, `red_4`, ...or better, as a multiscale group matching exercise 2's layout). What extra tag values do you need from exercise 1's parser?
# * Extend the manifest to every band of the scene, using the STAC item's asset hrefs. How does your structure compare to exercise 2's store? What would multiple *scenes* look like?
# * Make a second Icechunk commit (say, adding group attributes), then read the array back from the *first* snapshot's ID. Congratulations, you're time traveling.
# * We claimed the 8-byte gap between tiles (7, 0) and (7, 1) makes them "nearly adjacent". What *is* in those 8 bytes? (Exercise 1's IFD walk has everything you need to find out.)
# * Can you write a reader that consumes our kerchunk JSON directly--no fsspec, no zarr--using just `urllib` and the codecs, like exercise 2's `read_chunk`?
# * See [Kerchunk in Practice](https://guide.cloudnativegeo.org/kerchunk/kerchunk-in-practice.html) from the Cloud-Native Geo Guide for reference generation against NetCDF data, and the [VirtualiZarr](https://virtualizarr.readthedocs.io/) and [Icechunk](https://icechunk.io/) docs for where this ecosystem is headed.
#
# Any other cool ideas? Let me know and/or share with the group.
