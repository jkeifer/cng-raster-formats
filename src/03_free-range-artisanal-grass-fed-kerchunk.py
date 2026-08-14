# %% [markdown]
# # Free-Range Artisanal Grass-Fed Kerchunk
#
# Exercise 2 ended on a cliffhanger: Zarr's layout and access story is excellent, but its discovery story is "bring your own manifest". Nothing in a Zarr store can tell you which chunks exist or where their bytes live; the metadata describes what data should look like, and absence silently reads as fill.
#
# But think back to exercise 1. The COG had a manifest: the `tile_offsets` (324) and `tile_byte_counts` (325) tags were a complete inventory of every tile in the file, exactly which image segments exist, exactly where their bytes live. Perhaps a bit clunky to parse, but a real inventory. Notably though, this inventory is _internal_: locked inside the TIFF's binary structure, in the file itself.
#
# That it is internal makes sense, because as a single-file format it would be useless without it. Consider, however, if we wrote that inventory down _externally_, along with the rest of the metadata? We have metadata documents saying "here is an array, here is its shape and decode recipe", plus a mapping from each chunk key to a `(url, byte offset, byte length)` triple pointing into the original COG. What could we do with that? What would that enable?
#
# Consider further if we chose to write that metadata in Zarr format. Conceivably, a Zarr reader could then read the COG's bytes directly, not as a COG but a Zarr, without copying even a single pixel.
#
# Such is a kerchunk reference file, and in this exercise we're going to build one by hand for the very same B04 COG from exercise 1.
#
# Then, because hand-writing JSON is clearly not production tooling, we'll finish with a quick look at the modern descendants of this idea: opening our references as *virtual arrays* with VirtualiZarr, and committing them to *Icechunk*, where the manifest becomes versioned, transactional data in its own right.
#
# The usual imports first.

# %%
import json
import math

from pathlib import Path

import numpy as np

# %% [markdown]
# ## Getting our TIFF attributes
#
# We already did this in the first exercise! We could do it again if we felt it was necessary, but to save some time we'll start with those attributes already copied out of the first exercise's outputs, rather than re-parse the file.
#
# Pay attention to what attributes we have defined here. The `offsets` and `lengths` tuples are the inventory this whole exercise is about. Everything else is the context we need to find which offset/length pairs we want and decode what they point at.

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
    'crs': 'EPSG:32610',
    'transform': [10.0, 0.0, 600000.0, 0.0, -10.0, 5100000.0],
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
# The COG stores `uint16` digital numbers (DNs), but as we learned in exercise 1 they represent float reflectance via a scale and offset a reader may or may not notice. In exercise 2, we saw the Zarr answer to that ambiguity: make scaling part of the declared codec chain. As a result, in the Zarr the array's canonical data type is `float32`. We're writing the metadata this time, which means we choose the contract, so let's choose the more explicit exercise 2 contract. Thus, our array will declare the dtype to be `float32` (alternatively written in numpy format as `<f4`, which we'll need to use in once place), with the DN-to-reflectance scaling/offseting handled inside the codec pipeline.
#
# ## Building our Kerchunk
#
# We're describing a Zarr v3 store, so every node gets a `zarr.json` file, and chunks are addressed via `c/{row}/{col}` keys. As such, we'll need to define the following:
#
# * `zarr.json`: the root group document
# * `red/zarr.json`: the array document for our band (we'll use the name `red`, matching both the STAC asset's common name and the band group in exercise 2's store)
# * `red/c/{row}/{col}`: one entry per chunk
#
# In a real Zarr store those chunk keys name objects full of bytes. In kerchunk they instead map to a `[url, offset, length]` triple: "the bytes for this chunk are over there". The metadata documents ride along inline, so opening the store touches nothing but the reference file until actual chunk data is requested.
#
# A few more notes on kerchunk:
#
# * Kerchunk comes in two json versions: 0 and 1. Refer to [the documentation for a longer explanation with examples](https://fsspec.github.io/kerchunk/spec.html#).
# * Version 0 defines everything as a reference inside a single JSON document. Version 1 builds upon version 0 with some additional features, primarily templating support to facilitate reducing similar, highly repetitive definitions into iterative patterns, both to make the file easier to write and to reduce its length. (It turns out that the size of json file can be a bottleneck/problem with large kerchunk datasets; there's also a parquet storage option we're going to ignore).
# * We're going to use version 1 here, but we'll skip templating to keep things simple; plain refs generated from a loop are easier to write and read.
# * The kerchunk format dates from the Zarr v2 era, and many references in the wild still carry v2 metadata documents. But the format itself is agnostic (it's just a mapping from key names to inline data or byte ranges) so nothing stops us from putting v3 documents in it. That's what we'll do, keeping our vocabulary consistent with exercise 2.
#
# ### Codec considerations
#
# The key feature of an array's metadata is the `codecs` pipeline. In exercise 2 we read the decode recipe declared by `codecs` and marveled that we didn't have to go spelunking for it. This time we don't have `codecs` yet: the bytes in the COG are already encoded and our declaration must describe how that encoding happend.
#
# | What GDAL did (encode direction) | Where the COG said so | What we must declare |
# | -------------------------------- | --------------------- | ------------------------- |
# | float reflectance → uint16 DNs via scale/offset | `GDAL_METADATA` tag (42112) | `numcodecs.fixedscaleoffset`      |
# | difference each value from its left neighbor | `predictor` tag (317) = 2 | ??? |
# | serialize values little-endian | the `II` byte-order mark | `bytes` with `endian: little` |
# | compress each tile with DEFLATE | `compression` tag (259) = 8 | `numcodecs.zlib` |
#
# Three of the four rows are easy. The scale/offset codec can be copied verbatim from exercise 2's array metadata. The byte order and compression have simple, stock codecs. But that second row, the predictor, that's more complicated...
#
# ### The predictor problem
#
# Remember the footnote from exercise 2, when we decoded the quicklook chunk? TIFF's predictor 2 restarts its differencing at every row, while the `numcodecs` delta codec differences the *flattened* chunk in one long run, not resetting for each row. At the time, that footnote was merely an explanation as to why the exercise 2 cumulative sum had no `axis` argument, in contrast to the need to specify the axis exercise 1.
#
# Now, however, that difference becomes much more meaningful: exercise 2's store could use `numcodecs.delta` (our our equivalent cumulative sum) because the Zarr had re-encoded the original COGs data with that flattened transform. Here though, we are pointing Zarr at bytes GDAL wrote following the TIFF predictor 2 convention with the per-row differencing. And the consequences here are severe: if the declared codec doesn't match the actual encoding, we don't get an error: we silently get wrong numbers.
#
# We can demonstrate the difference with a toy example:

# %%
from numcodecs import Delta

toy = np.array([[10, 11, 12], [1000, 1001, 1002]], dtype='<u2')
toy_tiff_encoded = toy.copy()
toy_tiff_encoded[:, 1:] = np.diff(toy, axis=1)

print('original:')
print(toy)
print('as stored by TIFF predictor 2:')
print(toy_tiff_encoded)
print('as stored by numcodecs delta:')
print(Delta(dtype='<u2').encode(toy))
print('numcodecs delta decode of those bytes:')
print(Delta(dtype='<u2').decode(toy_tiff_encoded.tobytes()).reshape(2, 3))

# %% [markdown]
# **Question**: What happened to the second row, and why? Would this kind of error be easy to spot in real imagery?

# %% [markdown]
# <!-- scrub-omit: -->
# **Answer**: The flattened cumulative sum never resets, so row 1's absolute first value (1000) gets added on top of row 0's final value (12), and the entire second row comes out shifted by 12. In a full 1024 x 1024 tile every row after the first inherits the accumulated garbage of all the rows above it (wrapping modulo 65536, for extra spice), so only row 0 decodes correctly. And no, it would not necessarily be easy to spot: the values can easily be plausible-looking numbers and not obvious noise, exactly the kind of silent wrongness that makes "declare the recipe correctly" matter.
#
# Fun fact: the previous edition of this workshop declared `delta` in its hand-built references and never noticed the error!

# %% [markdown]
# ### Writing our own codec
#
# Turns out we have no stock Zarr-compatible codec for TIFF's per-row predictor. Are we stuck? Not at all: Zarr v3's codec pipeline is extensible by design. A codec is a small class with an encode transform, a decode transform, and a name to register it under. For an operation as simple as this we don't need to write much code: decoding is just a cumulative sum along the last axis (like we did in exercise 1), and encoding is its inverse, a per-row difference (like we did above).

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
# **Beware of custom codecs**: our references now decode correctly, but only in an environment where a codec named `tiff.predictor2` with the same functionality is registered. Hand this reference file to someone else and their zarr will refuse it. This is the fundamental tradeoff of virtualizing bytes you didn't encode: formats whose transforms map onto standard codecs (netCDF4/HDF5's chunk compression, for instance, the case kerchunk was invented for) tend to virtualize cleanly, while formats with different encodings need custom codecs at every reader. It's also precisely why exercise 2's store _re-encoded_ the pixels into standard Zarr codecs instead of referencing the COG's bytes.
#
# ### Building the array document
#
# Now we're ready, finally, to assemble `red/zarr.json`. We can use the `red/0/zarr.json` in the exercise 2 Zarr store as a template (worth a side-by-side look afterwards, if you don't remember it), and from that we see the fields we need:
#
# * `zarr_format` / `node_type`: `3`, and this node is an `array`
# * `shape`: the image dimensions, `(row, col)` order
# * `data_type`: `float32`, the canonical type per our contract discussion
# * `chunk_grid`: regular, with the COG's tile size as the chunk shape
# * `chunk_key_encoding`: the default `c/`-style keys with `/` separators
# * `fill_value`: the *physical* value of the nodata DN: `0 * 0.0001 + -0.1 = -0.1`, matching exercise 2's store
# * `codecs`: the four-step recipe we just worked out, in encode order
# * `dimension_names`: `y` then `x`
# * `attributes`: and while we're writing metadata anyway, we can throw in the `proj:`/`spatial:` conventions from exercise 2
#
# The `spatial:` convention wants a `spatial:bbox`, which we don't have sitting in `tiff_attrs` but can derive: the transform's `c`/`f` terms are the top-left corner, and stepping by the pixel sizes `a`/`e` across the image dimensions gets us the other one. Note `e` is negative (rows run north to south), so adding it walks _down_ the rows to the minimum y.

# %%
a, b, c, d, e, f = tiff_attrs['transform']
xmin, ymax = c, f
xmax = xmin + a * tiff_attrs['size']['cols']
ymin = ymax + e * tiff_attrs['size']['rows']
bbox = [xmin, ymin, xmax, ymax]
bbox

# %%
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
    # What an absent chunk reads as. Typed by `data_type`, so it's a decoded
    # float32, the nodata DN pushed through the scale/offset, not the raw DN.
    # Round-tripping through float32 is what makes this agree bit-for-bit with
    # the store exercise 2 reads.
    'fill_value': float(
        np.float32(
            tiff_attrs['nodata'] * tiff_attrs['scale'] + tiff_attrs['offset'],
        ),
    ),
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
        'proj:code': tiff_attrs['crs'],
        'spatial:dimensions': ['y', 'x'],
        'spatial:shape': [tiff_attrs['size']['rows'], tiff_attrs['size']['cols']],
        'spatial:transform': tiff_attrs['transform'],
        'spatial:transform_type': 'affine',
        'spatial:bbox': bbox,
        'spatial:registration': 'pixel',
        'zarr_conventions': [
            {
                'uuid': '689b58e2-cf7b-45e0-9fff-9cfc0883d6b4',
                'schema_url': 'https://raw.githubusercontent.com/zarr-conventions/spatial/refs/tags/v0.1/schema.json',
                'spec_url': 'https://github.com/zarr-conventions/spatial/blob/v0.1/README.md',
                'name': 'spatial',
                'description': 'Spatial coordinate information',
            },
            {
                'uuid': 'f17cb550-5864-4468-aeb7-f3180cfb622f',
                'schema_url': 'https://raw.githubusercontent.com/zarr-conventions/proj/refs/tags/v0.1/schema.json',
                'spec_url': 'https://github.com/zarr-conventions/proj/blob/v0.1/README.md',
                'name': 'proj',
                'description': 'Coordinate reference system information for geospatial data',
            },
        ],
    },
}

# %% [markdown]
# One footnote on `numcodecs.zlib`: its `level` only matters when encoding, so any value is fine for read-only references.
#
# ### Building the manifest
#
# Now let's build the chunk references. We'll walk the 11 x 11 tile grid, and for each tile emit a `red/c/{row}/{col}` key mapping to `[href, offset, length]`. The two metadata documents go in as inline JSON strings, and the whole thing gets the kerchunk version-1 wrapper: `{'version': 1, 'refs': {...}}`.
#
# Note that we generate the chunk refs in row-major order, like we saw the TIFF use in exercise 1 for its tile ordering. Except here, unlike in the TIFF, the order doesn't actually matter: we're generating JSON, and the JSON spec says that map order is not guaranteed and thus should not carry any semantic meaning. Readers accessing these chunks look them up based on the key, not by any sort of index. Any order in the result is just an artifact of our generation process, not a requirement.

# %%
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
# **Question**: In exercises 1 and 2, our POI pixel lived in tile/chunk (7, 0). Do the offset and length in `red/c/7/0` match what exercise 1's tag parsing found for that tile?

# %% [markdown]
# <!-- scrub-omit: -->
# **Answer**: They must, as they're the same numbers. Tile (7, 0) is linear index 77 (7 x 11 + 0) in the row-major tile order, and entry 77 of the `tile_offsets`/`tile_byte_counts` tags is offset 161,151,032 with length 1,631,840. Our loop copied exactly those values into the `red/c/7/0` reference. The manifest isn't *derived from* the COG's inventory; it *is* the COG's inventory, just transcribed into a new format.

# %% [markdown]
# ## Watching the bytes: a logging HTTP client
#
# Before we open our creation, let's set up some instrumentation. The claim behind this whole exercise is that a Zarr reader will fetch the byte ranges our manifest dictates: no more, no less. To verify that we want to see every HTTP request as it happens, complete with the `Range` header.
#
# The reference filesystem we're about to use fetches remote data with `aiohttp`, and it accepts a `get_client` hook for supplying the client session. We can leverage `aiohttp`'s supported tracing hooks to instrument a `ClientSession` with logging, and return it from our `get_client` implementation.

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
# The reference file is opened through fsspec's `reference://` filesystem: a filesystem whose "files" are the keys of our refs mapping. Inline content is served directly, and byte-range triples are fetched from the target URL on demand. Zarr 3 drives fsspec asynchronously, so both the reference filesystem and the remote HTTPS filesystem under it need `asynchronous=True`, and we wrap the result in Zarr's `FsspecStore`.
#
# (A quality-of-life note: fsspec caches filesystem instances by their constructor arguments, which means if you need to update the reference file for some reason it'll take a kernel restart by default. But we can use the option `skip_instance_cache=True` to opt out of that cache to handle any updates without a restart.)

# %%
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
# ### The value of an explicit inventory
#
# In exercise 2, `zarr.open_group(...).keys()` against the store returned an empty list. As we saw, plain HTTP provides no way to list keys, and the metadata has no way to declare children. What happens if we ask the same question of our reference store here?

# %%
root_group = zarr.open_group(store, mode='r')
sorted(root_group.keys())

# %% [markdown]
# What a difference. Now we see a listing of the group's children! Same Zarr library, same question, but a different answer: this store has what the plain-HTTP store lacked, a way to specify an inventory. The reference filesystem knows every key that exists (because they're right there in the refs mapping), so enumeration works.
#
# And notice what our logging client printed while we did all this metadata work: nothing. The `zarr.json` documents were served inline from the reference file; we haven't had to make a single HTTP request yet.
#
# Let's grab the array and look it over.

# %%
red_array = root_group['red']
red_array.info

# %% [markdown]
# A 10980 x 10980 float32 array with 1024 x 1024 chunks and our four-codec pipeline...Zarr obviously read the metadata we wrote. 😀 At this layer, as far as any client can tell, we have an ordinary Zarr v3 array; the fact that its chunk bytes live inside a GeoTIFF in some random corner of the internet is invisible plumbing.
#
# xarray works too:

# %%
import xarray

dataset = xarray.open_zarr(store, consolidated=False)
dataset

# %% [markdown]
# One data variable, `red`, with dimensions `y` and `x` straight from our `dimension_names`, as expected. Note that we're still operating on only metadata, and no HTTP requests have fired yet: like good cloud-native access patterns, everything so far is lazy.
#
# ## Reading our pixel
#
# Time to close the loop. In exercise 1 we found our POI at pixel (7471, 211) by chasing geo keys and affine math through TIFF tags; in exercise 2 the convention attributes handed us the same answer. It's the same grid here, so let's read that exact pixel and watch what happens on the wire.

# %%
poi_reflectance = float(dataset.red[7471, 211].values)
print(f'POI red reflectance: {poi_reflectance:.4f}')

# %% [markdown]
# <!-- scrub-omit: -->
# **Question**: Compare the logged byte range against the `red/c/7/0` reference (and exercise 1's tag values). Are these as expected? Is this the expected reflectance value?

# %% [markdown]
# <!-- scrub-omit: -->
# **Answer**: The request was `bytes=161151032-162782871`, so the start is equal to the manifest's offset, and the end is equal to offset + length - 1. That is byte-for-byte the range exercise 1 computed from tags 324/325 for tile (7, 0). And the reflectance value: it clearly flowed through four declared codecs, including our hand-rolled predictor codec, to give us the same answer we saw in exercise 1 and 2. The codec pipeline worked!

# %% [markdown]
# ## Reading across chunks
#
# What about a window spanning two neighboring tiles? Tiles (7, 0) and (7, 1) are adjacent in the image and adjacent in the file (or rather, nearly, (7, 0)'s bytes end at 162,782,871 and (7, 1)'s begin at 162,782,880, a gap of 8 bytes; [see GDAL's docs on the data leader and trailer](https://gdal.org/en/stable/drivers/raster/cog.html#tile-data-leader-and-trailer) to understand the gap). Let's read a window covering both and see how the requests come out.

# %%
two_tiles = dataset.red[7168:8192, 0:2048].values
two_tiles.shape

# %% [markdown]
# Two requests, one per chunk, each with exactly its own manifest range. If you used GDAL, or an earlier edition of this notebook, to read these chunks in this way, you might have expected the two nearly-touching ranges to be coalesced into a single request. That is, in fact, a real optimization some clients perform. Zarr's store interface fetches each chunk key independently (because in a non-virtual store they are different objects that cannot be coalesced), however, and leans on concurrency instead. The manifest's job is the same either way: it supplies the exact ranges; request-shaping is client strategy on top.
#
# And when the chunks _aren't_ neighbors in the byte layout of file? Tiles (7, 0) and (8, 0) are vertically adjacent in the image, but row-major layout puts roughly 14 MB of other tiles between them in the COG.

# %%
two_tiles_apart = dataset.red[7168:9216, 0:1024].values
two_tiles_apart.shape

# %% [markdown]
# Again two exact ranges, efficiently excluding the intermediate data we don't want.
#
# ## From artisanal to industrial: VirtualiZarr
#
# Nobody builds reference files by hand outside a workshop. The `kerchunk` package that pioneered this idea ships extractors that scan netCDF/HDF5, GRIB, TIFF, and friends and emit reference JSON automatically. But JSON files of chunk references have real limits: they're all-or-nothing to read or update, and they get enormous (millions of chunks means millions of JSON entries, which is just as bad as it sounds).
#
# The modern toolchain splits the idea into two proper layers. **VirtualiZarr** gives manifests a first-class in-memory model: a `ManifestArray` is Zarr v3 array metadata plus a chunk manifest, and it lives inside ordinary xarray datasets as a virtual variable, providing all the structure with none of the bytes. **Icechunk** (as we'll see in the next section) gives them a durable home. VirtualiZarr ships parsers for the kerchunk JSON format, but they expect the v2-era metadata documents that format historically carried; our references are v3-shaped, so rather than translate backwards we'll do something more instructive: build the VirtualiZarr objects directly and see that they are _exactly the pieces we already made_. A chunk manifest first:

# %%
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
# Then the manifest plus our array document make a `ManifestArray`; a `ManifestGroup` holds it (that's our root group document); and a `ManifestStore` binds the group to an object-store registry that says which store handles URLs under the COG's prefix. VirtualiZarr does its I/O through `obstore` rather than `fsspec`, so we hand it an `HTTPStore` for the bucket's HTTPS endpoint.

# %%
from obspec_utils.registry import ObjectStoreRegistry
from obstore.store import HTTPStore
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
# (Note that `ArrayV3Metadata.from_dict` accepted our hand-built document as-is, complete with our custom codec, since we registered it. This is a nice confirmation that what we wrote really is well-formed v3 array metadata.)
#
# From the store we can get a virtual dataset: an xarray dataset whose variables wrap `ManifestArray`s instead of loaded (or lazily-loadable) numpy data.

# %%
virtual_dataset = manifest_store.to_virtual_dataset()
virtual_dataset

# %% [markdown]
# It looks like the dataset we opened through `fsspec`, except the `red` variable's data here is a `ManifestArray`. This dataset can't compute anything; it exists solely to describe. Its real superpower is size:

# %%
print(f'apparent dataset size: {virtual_dataset.nbytes / 1e6:.0f} MB')
print(f'actual size in memory: {virtual_dataset.vz.nbytes / 1e3:.0f} kB')

# %% [markdown]
# Here we have ~500MB of Sentinel 2 imagery, represented in a few kilobytes of metadata and offsets (sound familiar? TIFF would like a word...). Virtual datasets for _thousands_ of scenes fit comfortably in memory, get concatenated with ordinary `xarray.concat` calls, and can all be written to a reference store in one shot.
#
# ## A manifest with a memory: Icechunk
#
# So where should this manifest live?
#
# A JSON file was our v1 answer, with the limits noted above. **Icechunk** is a more modern answer, providing the means of creating a Zarr v3 store whose contents (metadata, chunk data, and virtual chunk references) are managed kinda like a git repository. That is, writes happen in transactions, every transaction commit produces an immutable snapshot, and readers can time-travel through the graph of the snapshots. The inventory zarr never had is not just bolted on here, it's versioned data with a history.
#
# An Icechunk repository effectively must be persisted to be valuable, living in object storage or on disk, but for the workshop purposes we'll just build one in memory. One wrinkle virtual references add: a repository must be explicitly configured to, and each session explicitly authorized to, fetch bytes from foreign locations, via a _virtual chunk container_ declaring the URL prefix and how to access it (anonymous HTTPS, for us). The reason: exfiltration of your credentials shouldn't happen if a manifest is made public or stolen.

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
# Writing our virtual dataset into this Icechunk store is a session, a write, and a commit:

# %%
session = repo.writable_session('main')
virtual_dataset.vz.to_icechunk(session.store)
snapshot_id = session.commit('add virtual references to the S2 B04 COG')
snapshot_id

# %% [markdown]
# That commit is a durable, atomic snapshot: the array metadata plus a binary chunk manifest recording, for every chunk, either its own stored bytes or a virtual reference into our COG. Reading it back is just zarr-and-xarray-as-usual against a (read-only) session's store:

# %%
readonly_session = repo.readonly_session(branch='main')
ic_dataset = xarray.open_zarr(readonly_session.store, consolidated=False)
print(f'POI red reflectance: {float(ic_dataset.red[7471, 211].values):.4f}')

# %% [markdown]
# That's the same reflectance value we saw above. It works! (Note that no request appeared in our logs because Icechunk fetches virtual chunks with its own internal HTTP client, not aiohttp. But it issued the same range read our manifest dictates. Note also that our custom codec caveat followed us here: this repository's array still declares `tiff.predictor2`, so its readers need that codec too.)
#
# And because the manifest is now *versioned data*, we can interrogate it like data, for example listing every foreign location this repository would touch, or walking its commit history:

# %%
print(set(readonly_session.all_virtual_chunk_locations()))
for snapshot in repo.ancestry(branch='main'):
    print(f'{snapshot.id}: {snapshot.message}')

# %% [markdown]
# One external dependency, two commits (ours, plus the repository-initialization commit), and a growing history from here: append tomorrow's scene as a new commit, and yesterday's analysis can still pin yesterday's snapshot. Transactional updates, safe for concurrent readers, with time travel, for what started in this notebook as some byte offsets and lengths copied from our TIFF parsing in exercise 1.
#
# One final caveat to keep in mind with virtual references of any flavor: they all share the same load-bearing assumption that _the source files don't change_. Our manifest describes byte ranges in somebody else's bucket. If that COG is ever rewritten, recompressed, or deleted, every reference into it silently rots (Icechunk can at least track a `last_updated_at` timestamp per reference and refuse ones that have gone stale).
#
# ## Full circle
#
# The thread we've pulled across three exercises, in one paragraph: the COG kept a manifest _inside_ the file. Zarr computed its addressing and kept _no_ manifest (elegant reads, but absence is silent and listing is entirely dependent on access to something _outside_ Zarr, the storage layer). Kerchunk's insight was that the manifest can be its own data: pull the inventory out, write it down, and a reader can consume anything with a byte layout you can describe. VirtualiZarr made that idea composable. Icechunk made it durable, versioned, and transactional. Discovery cannot solve itself: someone always has to write the inventory down. Now that you've done that "writing down" yourself, you can understand what all these fancy tools are doing too.

# %% [markdown]
# ## Additional exercises to consider later
#
# * Our manifest covers only the COG's full-resolution IFD. Add the overview IFDs as additional arrays (`red_2`, `red_4`, ...or better, as a multiscale group matching exercise 2's layout). What extra tag values do you need from exercise 1's parser?
# * Extend the manifest to every band of the scene, using the STAC item's asset hrefs. How does your structure compare to exercise 2's store? What would multiple *scenes* look like?
# * Make a second Icechunk commit (say, adding group attributes), then read the array back from the *first* snapshot's ID. Congratulations, you're time traveling.
# * Can you write a reader that consumes our kerchunk JSON directly---no fsspec, no zarr---using just `urllib` and the codecs, like exercise 2's `read_chunk`?
# * See [Kerchunk in Practice](https://guide.cloudnativegeo.org/kerchunk/kerchunk-in-practice.html) from the Cloud-Native Geo Guide for reference generation against NetCDF data, and the [VirtualiZarr](https://virtualizarr.readthedocs.io/) and [Icechunk](https://icechunk.io/) docs for more about where this ecosystem is headed.
#
# Any other cool ideas? Let me know and/or share with the group.
