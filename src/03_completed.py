# %% [markdown]
# # Free-Range Artisanal Grass-Fed Kerchunk
#
# Let's build a kerchunk reference file _by hand_ for the TIFF we read in the "Reading COGs the hard way" exercise. To test if we did it right we can open it up with xarray using it's kerchunk/zarr support.
#
# As always, let's get imports out of the way first.

# %%
import json
import math

from pathlib import Path

import xarray

# %% [markdown]
# ## Getting our TIFF attributes
#
# We already did this in the first exercise! We could do it again if we felt it was necessary, but to save some time we'll start with those attributes already copied out of the first exercise's outputs.
#
# Do pay attention to what attributes we have defined here. Everything here will be required as we build up our kerchunk file.
#
# ### A note on data type
#
# If you recall, the TIFF from exercise one had a data type of `uint16`. However, astute readers will note that the data type (`dtype`) defined here is `<f4`, or "little-endian floating point of four bytes (32-bit)". This discrepancy is because the TIFF is _intended_ to representing floating point data, but it does so using `uint16` with a scale factor to reduce the file size.
#
# We'll see in a bit that we'll need to specify a number of different data types, one of which will be out _target_ data type, which per this discussion we realize is `float32`, not `uint16`.

# %%
tiff_attrs = {
    'href': 'https://e84-earth-search-sentinel-data.s3.us-west-2.amazonaws.com/sentinel-2-c1-l2a/10/T/FR/2023/12/S2B_T10TFR_20231223T190950_L2A/B04.tif',
    'size': {
        'rows': 10980,
        'cols': 10980,
    },
    'dtype': '<f4',
    'compression': {
        'id': 'zlib',
    },
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
    }
}

# %% [markdown]
# ## Building our kerchunk config
#
# Kerchunk comes in two json versions: 0 and 1. Refer to [the documentation for a longer explanation with examples](https://fsspec.github.io/kerchunk/spec.html#).
#
# In short: version 0 is rather simple, effectively merging all zarr metadata files together into a single file. Each data array is then also defined in the file with a source path, offset, and length. Version 1 provides some additional features, primarily templating support to facilitate reducing similar, highly repetative definitions into iterative patterns, both to make the file easier to write and to reduce its length. (It turns out that the size of json file can be a bottleneck/problem with large kerchunk datasets).
#
# In our case, we could leverage templating within the file, but it is easier both to script the file generation and check that what we produced looks reasonable if we do so in python rather than as a templated kerchunk file.
#
# ### What "files" do we need to define?
#
# We're effectively building a zarr dataset, without converting our data to native zarr arrays. So we need to build an equivalent to all the zarr metadata we looked at in the second exercise "Reading Zarr the Hard Way". This includes defining:
#
# * `.zgroup`
# * `{array}/.zattrs`
# * `{array/.zarray`
#
# We'll also need to define a zarr array chunk file via kerchunk references for each tile in our raster. We could create an array per overview level in the tiff if we wanted, but to keep things simple we'll just have one array for the full resolution data.
#
# In this case the band of the original Sentinel 2 image that we are working with is the `red` band, so we'll use the name `red` for our array name.
#
# ### What array metadata do we need?
#
# We can look back to the second exercise to see the list of matadata fields that need to be defined per array in `.zarray`:
#
# * `chunks`
#   * Should be our tile dimensions in `(row, col)` order.
# * `compressor`
#   * We found the TIFF to be compressed using `DEFLATE` which we inflated using `zlib`; turns out that's really all we need to define here is that our compressor is `"id": "zlib"`. See [the `numcodecs` docs](https://numcodecs.readthedocs.io/en/stable/compression/index.html) for more information about that and other options. Additional codecs can also be registered.
# * `dtype`
#   * As discussed above, this is our _target_ datatype.
# * `fill_value`
#   * Also known as `nodata` in more typical GDAL parlance.
# * `filters`
#   * This one is a bit more involved. If you recall from exercise one we had to do two things to the tile array after decompression: undo the `PREDICTOR=2` cumulative difference calculation, and apply the scale and offset. Zarr's filters can be used to do both of these transformations.
#
#   A filter in Zarr is simply a transformation operation that is done prior to compression, and thus must be reversed after decompression. The order matters here: the are applied sequentially before compression and in reverse order after decompression. [`numcodecs` supports several different filters](https://numcodecs.readthedocs.io/en/stable/filter/index.html), and, like compression codecs, additional filters can be registered.
#
#   In our case, we know our data was first modified via the scale and offset. We apply this filter first; note that our scale value is actually inverse of what we need to define here. Also note that the data type changes with this filter from the native/target data type of `float32` to `uint16`.
#
#   Next, we can undo the cumulative difference with the `delta` filter. As this filter is between scaling/offsetting and compression/decompression, the data type both in and out is `unit16`.
# * `order`
#   * This is `C`. Several options are available for this but `C` is a good default. See [these numpy docs](https://numpy.org/devdocs/reference/generated/numpy.ravel.html) for more information.
# * `shape`
#   * The total size of the array, which is our TIFF image size in `(row, col)` order.
# * `zarr_format`
#   * We're gonna stick with `2` here to be consistent and not have to learn _another_ format for this workshop.
#  
# ### How do we define the array chunk references?

# %%
kerchunking = {
    '.zgroup': {'zarr_format': 2},
    'red/.zattrs': {'_ARRAY_DIMENSIONS': ['Y', 'X']},
    'red/.zarray': {
        'chunks': [
            tiff_attrs['tiles']['size']['rows'],
            tiff_attrs['tiles']['size']['cols'],
        ],
        'compressor': tiff_attrs['compression'],
        'dtype': tiff_attrs['dtype'],
        'fill_value': tiff_attrs['nodata'],
        'filters': [
            {
                'id': 'fixedscaleoffset',
                'offset': tiff_attrs['offset'],
                'scale': 1/tiff_attrs['scale'],
                'dtype': tiff_attrs['dtype'],
                'astype': '<u2',
            },
            {
                'id': 'delta',
                'dtype': '<u2',
                'astype': '<u2',
            },
        ],
        'order': 'C',
        'shape': [
            tiff_attrs['size']['rows'],
            tiff_attrs['size']['cols'],
        ],
        'zarr_format': 2,
    },
}

for tile_row in range(math.ceil(tiff_attrs['size']['rows'] / tiff_attrs['tiles']['size']['rows'])):
    for tile_col in range(math.ceil(tiff_attrs['size']['cols'] / tiff_attrs['tiles']['size']['cols'])):
        tile_index = (math.ceil(tiff_attrs['size']['cols'] / tiff_attrs['tiles']['size']['cols']) * tile_row) + tile_col
        kerchunking[f'red/{tile_row}.{tile_col}'] = [
            tiff_attrs['href'],
            tiff_attrs['tiles']['offsets'][tile_index],
            tiff_attrs['tiles']['lengths'][tile_index],
        ]

json_file = Path('./kerchunk.json')
json_file.write_text(json.dumps(kerchunking))

print(json.dumps(kerchunking, indent=4))

# %% [markdown]
# Find the array chunk for the tile we read in the COG exercise. Do the offset and length values here match what we previously found for that tile?

# %% [markdown]
# ## Opening the kerchunk dataset with xarray
#
# We're going to use xarray to open the dataset to check it out and see if this worked.
#
# One thing that will be interesting is to know both when xarray makes an HTTP request to read our file data, and to know what byte range it is reading so we can see if it is sticking to the tiles and their byte ranges as we've defined. To facilitate seeing this, we're going to override the HTTP client xarray uses with our own wrapped implementation that will print out the information we're interested in when a request is made.

# %%
import aiohttp
from aiohttp.typedefs import LooseHeaders, StrOrURL

class LoggingClientSession(aiohttp.ClientSession):
    def get(self, url: StrOrURL, *args, headers: LooseHeaders | None = None, **kwargs):
        range_ = ' with no byte range specified'
        if headers and headers.get('Range'):
            range_ = f" with byte range '{headers.get('Range')}'"
        print(f'HTTP Client getting {url}{range_}')
        return super().get(url, *args, headers=headers, **kwargs)


async def get_client(**kwargs):
    return LoggingClientSession(**kwargs)


# %% [markdown]
# Now that we got that client implementation out of the way, let's actually open our dataset with `xarray`. Note that we need to set the `remote_protocol` to tell the xarray backend what protocol to use to access the data (`https`), and that it should use our wrapped HTTP client.
#
# **NOTE**: It seems that xarray, fsspec, or some other library in the stack is storing some global state or otherwise caching our kerchunk config in some way. In testing it took restarting the kernel on every change of the kerchunk json file to force xarray's state to be reset and get the updates to take effect. Just something to be aware of.

# %%
dataset = xarray.open_dataset(
    str(json_file),
    engine='kerchunk',
    backend_kwargs={
        'storage_options': {
            'remote_protocol': 'https',
            'remote_options': {
                'get_client': get_client,
            }
        },
    },
)
dataset

# %% [markdown]
# The opened dataset should have the dimensions we expect, as well as the one `red` data variable that we defined.
#
# We can select that variable to get a data array object.

# %%
dataset.red

# %% [markdown]
# From the data array we can select the same tile we read in the COG exercise, though to do so we'll need to find the pixel coordinates of the tile within the array as a whole.

# %%
tile_of_interest_row = 7
tile_of_interest_col = 0
tile_of_interest = dataset.red[
    tiff_attrs['tiles']['size']['rows'] * tile_of_interest_row:tiff_attrs['tiles']['size']['rows'] * (tile_of_interest_row + 1),
    tiff_attrs['tiles']['size']['cols'] * tile_of_interest_col:tiff_attrs['tiles']['size']['cols'] * (tile_of_interest_col + 1)]
tile_of_interest

# %% [markdown]
# ### Actually reading data
#
# Note that `xarray` doesn't touch the data until it is specifically requested. We can continue to perform operations on the data array to further subset the data required for any analysis, which ensures we only have to download the chunks of the array we actually need for whatever we're doing.
#
# This is exactly the lazy data access and ability to do data subsetting that cloud-optimized formats allow!
#
# We are ready, though, to request our data. We should see the HTTP request logged by our `LoggingClientSession` class, complete with the byte range requested.

# %%
tile_of_interest.values

# %% [markdown]
# Does that byte range match what we'd expect to see for reading this tile?
#
# Do the array values appear to match the values we saw when we read this tile in the COG exercise?

# %% [markdown]
# What happens if we request _two_ tiles?

# %%
tile_of_interest_row = 7
tile_of_interest_col = 0
two_tiles = dataset.red[
    tiff_attrs['tiles']['size']['rows'] * tile_of_interest_row:tiff_attrs['tiles']['size']['rows'] * (tile_of_interest_row + 1),
    tiff_attrs['tiles']['size']['cols'] * tile_of_interest_col:tiff_attrs['tiles']['size']['cols'] * (tile_of_interest_col + 2)]
two_tiles

# %%
two_tiles.values

# %% [markdown]
# What happened to the byte range in the request? Does it match expectations?
#
# What happens if instead of requesting two tiles that are neighboring in the COG layout we instead request two tiles that have discontinuous byte ranges?

# %%
tile_of_interest_row = 7
tile_of_interest_col = 0
two_tiles_discontinuous = dataset.red[
    tiff_attrs['tiles']['size']['rows'] * tile_of_interest_row:tiff_attrs['tiles']['size']['rows'] * (tile_of_interest_row + 2),
    tiff_attrs['tiles']['size']['cols'] * tile_of_interest_col:tiff_attrs['tiles']['size']['cols'] * (tile_of_interest_col + 1)]
two_tiles_discontinuous.values

# %% [markdown]
# Again, what happened to the byte range in the request? Does it match expectations?

# %% [markdown]
# ## Additional exercises
#
# * What would this be like if _all_ of the Sentinel 2 scenes' bands' COGs we indexed into this kerchunk reference file?
# * How might this kerchunk look if multiple Sentinel 2 scenes were then indexed into the same reference file?
# * See [Kerchunk in Practice](https://guide.cloudnativegeo.org/kerchunk/kerchunk-in-practice.html) from the Cloud-Native Geo Guide for examples using kerchunk to index NetCDF format data.
# * Can you make a parser to load data for this kerchunk without having to rely on xarray and fsspec?
#
# Any other cool ideas? Let me know and/or share with the group.
