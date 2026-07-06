# %% [markdown]
# # Understanding Zarr

# %%
import datetime
import json

from pathlib import Path
from typing import Any

import fsspec
import numpy as np
import planetary_computer
import pystac_client

from griffine import Affine, Grid
from odc.geo.geom import point

# %% [markdown]
# # Point of Interest (POI)
#
# I want to go to Puerto Rico, but I'm from a northern temporate latitude. I'd like to find the best week of the year for me to visit Puerto Rico without having oppressive weather. Can we use a zarr dataset from Planetary Computer to answer this question?
#
# To pick a more specific point of interest, let's use these coordinates of San Juan:

# %%
POI = point(-66.063889, 18.406389, crs='EPSG:4326')

# Let's find out where the point is
point_map = POI.explore(name='point')
point_map

# %% [markdown]
# ## Finding data
#
# Now that we know where to look, we need to find some data we can use to answer this question. Turns out Microsoft's Plantary Computer has zarr data, and [we can search for zarr to find possible datasets](https://planetarycomputer.microsoft.com/catalog?filter=zarr). A prime contender of the options is the [Daymet Daily Puerto Rico](https://planetarycomputer.microsoft.com/dataset/daymet-daily-pr) dataset. For the sake of keeping this exercise simple, let's just consider measurements from 2020 (the last year in the dataset), and we'll sum the daily maximum temperature (`tmax` variable).
#
# Zarr datasets can be represented by a STAC collection without items, with a collection asset pointing to the zarr root. To get more information about this dataset we can fetch the `daymet-daily-pr` STAC collection from Planetary Computer. Pay special attention to the `assets`, `cube:variables`, and `cube:dimensions` attributes of the fetched collection.
#
# Note that accessing Planetary Computer data from Azure Blob Storage requires a signed token; we can use the `planetary_computer` package as a "plugin" of sorts to `pystac_client` to ensure we get an access token attached as necessary to each asset.

# %%
catalog = pystac_client.Client.open(
    "https://planetarycomputer.microsoft.com/api/stac/v1",
    modifier=planetary_computer.sign_inplace,
)
collection = catalog.get_collection('daymet-daily-pr')
collection

# %% [markdown]
# ## Accessing the zarr files
#
# We're going to use `fsspec` with the `abfs` filesystem type (as provided by the `adlfs` package) to get access to the zarr directory tree and its files. The `abfs` filesystem requires both an access token signed to and the Azure account name of the bucket we are attempting to access. Because we used the `planetary_computer` package with `pystac_client` when querying the collection, these connection details are included in the `xarray:storage_options` property of the `zarr-abfs` asset, and we can use them to successfully initialize our filessytem object `fs` and use it to explore the contents of the bucket.
#
# All the paths we're interested in will be under the root of the zarr we are interested in. That path is provided within the `zarr-abfs` asset's href.

# %%
asset = collection.assets["zarr-abfs"]
asset

# %%
# we need the href without the `abfs://`
zarr_root = Path(asset.href.split('//', 1)[1])
zarr_root

# %%
# the xarray:storage_options gives us the access token and account name required to connect
fs = fsspec.filesystem('abfs', **asset.extra_fields['xarray:storage_options'])

# %% [markdown]
# An fsspec filesystem provides an API that includes normal filesystem-related functions, such as listing a path (`ls`), reading files (`open), or finding file information (`stat`).

# %%
# now we can list the zarr root
fs.ls(str(zarr_root))

# %% [markdown]
# Note that when we list the zarr root we see some `.z*` files with zarr-related metadata and othe such info, which can be used to understand how to access the data in the listed directories. Notice also that the listed directory names predominately map to the zarr variables listed out in the STAC collection. From this we can be reasonably certain that the data for each varaible is nested within the directory of the same name.

# %%
# and we can read a file
with fs.open(str(zarr_root / '.zattrs')) as f:
   content = f.read()

content


# %% [markdown]
# ## Making browsing even easier
#
# Even with fsspec, browsing and reading files has a bit more boiler plate than we might like. We can easily create some simple functions to make an easier API for the types of operations we need to do to explore our zarr.

# %%
# let's make some convenience functions to make browsing easier
def ls_zarr(path: str) -> list[str]:
    return fs.ls(str(zarr_root / path))

def read_zarr_file(path: str) -> bytes:
    with fs.open(str(zarr_root / path)) as f:
        return f.read()

def read_zarr_json(path: str) -> dict[str, Any]:
    return json.loads(read_zarr_file(path))

def print_json(_json: dict[str, Any]) -> None:
    print(json.dumps(_json, indent=4))


# %% [markdown]
# And we can use one of the convenience functions to show much simpler reading the zarr metadata can be.

# %%
zmeta = read_zarr_json('.zmetadata')
print_json(zmeta)

# %% [markdown]
# ### `.zmetadata`
#
# Notice that the `.zmetadata` file starts with the `.zattrs` key, the value of which contains the same content as the `.zattrs` file we read a moment ago? Spoiler alert: `.zmetadata` contains the contents of all the `.z*` files. It's a great way to get an overview of the entire contents of the zarr. From here we can see a full inventory of the `.z*` file types through the archive:
#
# * `.zmetadata`: this file only
# * `.zattrs`: top-level and one in each variable's directory
# * `.zgroup`: top-level, just specifies the zarr version (here version 2)
# * `.zarray`: one in each variable's directory
#
# Note that `.zmetadata` appears only to be present if the zarr has "consolidated metadata", as this one does (and apparently that is a zarr extension and not part of the core spec).
#
# ### `.zattrs`
#
# `.zattrs` appears to provide user-facing information, such as dataset version information, citations, and that which can help users appropriately interpret the meaning of the data including units, array dimensions, and the like. Note that the collection also contains much of this information. For our purposes these values can help us know which files we might want to look at and how to interpret their structure and values, but otherwise we will be programmatically skipping over them.
#
# ### `.zgroup`
#
# This is super relevant to zarr readers to know what format the zarr is. For us, we are just exploring whatever we've found here, so it's not relevant really at all. At least not until we get to trying to read the next zarr file and we start wondering why it looks different than this one...
#
# ### `.zarray`
#
# Finally, a good one. We're going to need to be very interested in the `.zarray` files because they tell us some key information we're going to need to properly read the data arrays. Specifically, the fields data type, compression type (note that all are compressed via the `blosc` algorithm with the same settings), and chunk size are ones we're absolutely going to need. Some other fields that could be very relevant for reading data in other files include `filters` and `fill_value`, but we won't need to be concerned with those here.

# %% [markdown]
# ## Reading an array
#
# We're going to need location information, and our POI is in WGS84 (lat/long), so maybe we start by reading the `lat` variable?
#
# First, let's see what all is in the `lat` directory:

# %%
ls_zarr('lat/')

# %% [markdown]
# Not a lot. Maybe if we look at the `.zarray` and `.zattrs` we can learn something?

# %%
lat_zarray = read_zarr_json('lat/.zarray')
print_json(lat_zarray)

# %%
lat_zattrs = read_zarr_json('lat/.zattrs')
print_json(lat_zattrs)

# %% [markdown]
# The contents of both of these are exactly what we saw in top-level `.zmetadata`. No suprise there. And the `.zattrs` contents aren't particularly helpful at the moment.
#
# But the `.zarray`, that explains some things. First, we see the chunk size (`chunks`) is equal to the overall array size (`shape`). This tells us that this particular variable has only one chunk covering the entire extent of the data set to which it is relevant. We can make an educated guess then that `lat/0.0` is the array data for the single chunk.
#
# Let's read it and see what it looks like.

# %%
lat_bytes = read_zarr_file('lat/0.0')
print(f'{lat_bytes[:100]}...')
print(len(lat_bytes))

# %% [markdown]
# Just a bunch of ugly binary data--as we might have suspected, espcially given that it is supposedly compressed.
#
# Looking into the `blosc` compression format appears to indicate that it is `lz4`, so it seems like an `lz4`-compatible codec would be required. It turns out that's not entirely true. To cut a long story short, digging into this and trying to unravel what something like xarray uses to decompress such an array leads to [the `numcodecs` package](https://github.com/zarr-developers/numcodecs). It has a `blosc` codec, which can use to decompress this byte string and get an array.
#
# We'll be doing that operation a bunch, so let's make another convenience function that we can use to quickly and easily read these compressed array files.

# %%
import numcodecs.blosc

def read_zarr_blosc(path: str) -> Any:
    #with lz4.frame.LZ4FrameDecompressor() as decompressor:
    return numcodecs.blosc.decompress(read_zarr_file(path))


# %%
lat_uncompressed = read_zarr_blosc('lat/0.0')
print(f'{lat_uncompressed[:100]}...')
print(len(lat_uncompressed))

# %% [markdown]
# Uncompressed it's still pretty ugly, but again not really unexpected because it's binary data. We need to unpack it into an array and see what that looks like.

# %% [markdown]
# #### A quick note on data types
#
# The format of the data type is not what we might suspect after all the work we did with the `struct` package and packing/unpacking the TIFF values. Apparently the data type specification here is one natively supported by `numpy`, meaning the `dtype` string can be interpreted directly as a data type by `numpy`:

# %%
np.dtype('<f4'), np.dtype('<f8'), np.dtype('>f2')

# %% [markdown]
# `numpy` supports unpacking binary data from a byte string natively via the `frombuffer` method. We merely need to provide the specified data type for it to unpack the bytes properly, and then we can reshape the resulting array into the `chunks` shape.

# %%
dt = np.dtype(lat_zarray['dtype'])
lat_array = np.frombuffer(lat_uncompressed, dtype=dt).reshape(lat_zarray['chunks'])
lat_array

# %% [markdown]
# Success! Those values should look like what we'd expect for latitude values in or around Puerto Rico.

# %% [markdown]
# We can read in the `lon` variable the exact same way:

# %%
lon_zarray = read_zarr_json('lon/.zarray')
dt = np.dtype(lon_zarray['dtype'])
lon_array = np.frombuffer(read_zarr_blosc('lon/0.0'), dtype=dt).reshape(lon_zarray['chunks'])
lon_array

# %% [markdown]
# ## Finding the cell coordinates of our POI
#
# Now that we have the `lat` and `lon` variable arrays, we should be able to locate the cell coordinates corresponding to our POI, right?
#
# Well, if we look closely at the arrays we realize something: they are two-dimensional! Neither latitude nor longitude are actually one of the base dimensions of our data cube. If we look more closely at the collection's metadata we realize that the data are in a projected coordinate system. We _could_ presumably use the `lat` and `long` variable arrays to find our cell coordinates, but doing so would require some sort of non-obvious multivariate optimization problem.
#
# Instead, what happens if we open our `x` variable?

# %%
x_zarray = read_zarr_json('x/.zarray')
dt = np.dtype(x_zarray['dtype'])
x_array = np.frombuffer(read_zarr_blosc('x/0'), dtype=dt).reshape(x_zarray['chunks'])
x_array

# %%
x_array.shape

# %% [markdown]
# Oh, look at that, it's a one-dimensional array of the cell x coordinates in the projected coordinate system.
#
# Let's look at `y` too.

# %%
y_zarray = read_zarr_json('y/.zarray')
dt = np.dtype(y_zarray['dtype'])
y_array = np.frombuffer(read_zarr_blosc('y/0'), dtype=dt).reshape(y_zarray['chunks'])
y_array

# %%
y_array.shape

# %% [markdown]
# `y` is one-dimensional as well. Not only that, but the shapes of each map to the opposing dimensions of our `lat` and `lon` array shapes. Seems like we're on the right track here, if we only could convert our POI into the projected coordinates...

# %% [markdown]
# ### Understanding our reference system
#
# One outstanding problem with zarr is that the geospatial extension still has yet to be formalized. This means we don't have a built-in way of grabbing the CRS information from the zarr itself. Planetary Computer gets around this issue by storing the CRS information in the STAC collection, specifically as part of the `cube:dimensions` metadata.
#
# Both the `x` and `y` dimensions have a reference system defined. Thankfully for us, the data provide has made a sane decision to ensure these CRSs are the same, so we only need to use one of them to get a transformer we can use to project our POI coordinates.

# %%
collection.extra_fields['cube:dimensions']['x']['reference_system']

# %%
POI_proj = POI.to_crs(collection.extra_fields['cube:dimensions']['x']['reference_system'])
print(f'x={POI_proj.geom.x}, y={POI_proj.geom.y}')

# %% [markdown]
# ### Calculating our cell coords with a "geotransform"
#
# At this point we're really just in regular raster land and find outselves needing the raster grid's affine transformation--or geotransform in GDAL speak--to convert our coordinates from model space to grid space. Other than having to continue to pull metadata out of the collection to get our inputs, we can calculate the values we need to create that data structure. Then we can use that with our grid dimensions to create a grid we'll be able to use to find the cell we want.

# %%
transform = Affine(
    collection.extra_fields['cube:dimensions']['x']['step'],
    0,
    collection.extra_fields['cube:dimensions']['x']['extent'][0],
    0,
    collection.extra_fields['cube:dimensions']['y']['step'],
    collection.extra_fields['cube:dimensions']['y']['extent'][1],
)
grid = Grid(rows=y_array.shape[0], cols=x_array.shape[0]).add_transform(transform)

# %% [markdown]
# With the grid we can now find the cell containing our POI!

# %%
cell = grid.point_to_cell(POI_proj)
print(f'row={cell.row}, col={cell.col}')

# %%
lon_array[cell.row, cell.col], lat_array[cell.row, cell.col]

# %% [markdown]
# Does that look right?

# %% [markdown]
# ### Another option to find the cell coords
#
# Remember that the `x` and `y` arrays are increasing/decreasing by a constant step? That told us we had a regular affine grid and could use the easy and efficient transformation calculations above to get our target cell. But CF Convention coordinate arrays allow for irregular grids far beyond the simplest affine grid case. As such, sometimes we can't take that easy way out, and have to find cells a different way. In this case, another option could have been to do something like a linear search:

# %%
col = 0
POI_row_ = None
while POI_proj.xy[1] < y_array[col]:
    POI_row_ = col
    col += 1
POI_row_

# %%
col = 0
POI_col_ = None
while POI_proj.xy[0] >= x_array[col]:
    POI_col_ = col
    col += 1
POI_col_

# %% [markdown]
# Note that this strategy worked in this case because we had all of our x and all our y coordinate values each in a single chunk. If we were working with a larger zarr dataset this might not have been the case. Also, this strategy is not particularly efficient. As a general rule it is probably best to stick to the coordinate calculation using the offsets from the grid origin rather than this more brute-force strategy, where possible, but it is important to realize that is not always possible. In such cases, properly finding cell coordinates can grow in complexity, beyond the options presented here.

# %% [markdown]
# ## Reading the `tmax` variable data
#
# If after all this you still remember what we are trying to do, great! If not, it's understandable, so here's a little refresher: we are interested in finding the week of 2020 with the lowest average (mean) `tmax` value. So it seems pertinent that we read in the `tmax` variable data.
#
# Let's take a look at what's in the `tmax` directory.

# %%
ls_zarr('tmax')

# %% [markdown]
# Uh oh. This is different than we've run into up till now. We see a bunch of different chunk files here. Maybe if we look at the `.zarray` and `.zattrs` we can figure out something to help us here.

# %%
tmax_zarray = read_zarr_json('tmax/.zarray')
print_json(tmax_zarray)

# %%
tmax_zattrs = read_zarr_json('tmax/.zattrs')
print_json(tmax_zattrs)

# %% [markdown]
# We see with `tmax` that the chunk size `(365, 231, 364)` is different than the shape `(14965, 231, 364)`. And from `.zattrs` we see the array dimensions listed as `(time, y, x)`. A deductive person could infer that, this being a daily dataset, the chunk having a size of `365` for the `time` dimension means that each chunk is a year's worth of values. We have 41 chunk files (`0.0.0` though `40.0.0`), and `365 * 41 = 14965`. It further stands to reason that the chunks are in chronological order, so we can reasonably assume we want the last chunk, `40.0.0`.
#
# But what good would it do just to be clever here? Instead, let's confirm our theory. To do so we can look at the `time` variable.

# %%
ls_zarr('time')

# %%
time_zarray = read_zarr_json('time/.zarray')
print_json(time_zarray)

# %%
suspected_year_chunk = 2020-1980
suspected_year_chunk

# %%
dt = np.dtype(time_zarray['dtype'])
time_array = np.frombuffer(read_zarr_blosc(f'time/{suspected_year_chunk}'), dtype=dt).reshape(time_zarray['chunks'])
time_array

# %% [markdown]
# Per the metadata for the `time` array, we can interpret these values as the date of that cell in the days since 1980-01-01. We can use the `datetime` module to calculate the date given by cell 0 in the array above:

# %%
# to confirm the dates match up
chunk_start_date = datetime.date.fromisoformat('19800101') + datetime.timedelta(days=int(time_array[0]))
print(chunk_start_date)

# %% [markdown]
# Ah, great, proof that chunk 40 is the chunk we want for 2020 values.

# %% [markdown]
# Now that we know which chunk we want, let's finally read it. Note that this array is significantly bigger--365 times bigger, to be exact--than our `lat` and `lon` arrays. As a result, it might take a bit longer to download, extract, and unpack into an array. Be patient. In testing this step took on the order of 30-60 seconds.

# %%
dt = np.dtype(tmax_zarray['dtype'])
tmax_array = np.frombuffer(read_zarr_blosc(f'tmax/{suspected_year_chunk}.0.0'), dtype=dt).reshape(tmax_zarray['chunks'])
tmax_array.shape

# %% [markdown]
# What were we trying to do with these values again? Oh yeah, find the average max temperature of each week in the year, so we can identify the minimum. We can do this pretty trivially with `numpy` by:
#
# * slicing out only the stack of temperature values we're interested in for our POI cell
# * reshaping the array into rows of seven values
# * finding the mean along the row axis (gives us the mean of each week)
# * find the min value within that weekly mean array

# %%
# We only take 364 temperature values because 365 isn't divisible by 7. 😕
# We obviously need to lobby to have weeks redefined to 5 days long,
# with 3 work days and 2 weekend days. Leap days, where required,
# should be added to the end of the year as a mandatory holiday.
# While we're at it, let's eliminate timezones and just use UTC.
# Please sign my petition. 😁
POI_tmax_array = tmax_array[:364, cell.row, cell.col].reshape(52, 7)
POI_tmax_array

# %%
POI_tmax_mean_array = np.mean(POI_tmax_array, axis=1)
POI_tmax_mean_array

# %%
POI_tmax_min = np.min(POI_tmax_mean_array)
POI_tmax_min_index = np.argmin(POI_tmax_mean_array)
print(f'The lowest tmax temp {POI_tmax_min} occurred in week {POI_tmax_min_index} of 2020.')

# %% [markdown]
# This is a great result! But it would be good if we could turn that into an actual date. Good thing we read in that `time` array: we can use slice it on weekly bounds to get the date of the first day of the week in question.

# %%
week__days_since_1980 = int(time_array[::7][POI_tmax_min_index])
week__days_since_1980

# %%
best_week_of_the_year_start = datetime.date.fromisoformat('19800101') + datetime.timedelta(days=week__days_since_1980)
print(f'The best day to arrive in Puerto Rico, from our data, was {best_week_of_the_year_start}. Now go book your time machine tickets. 😁')
