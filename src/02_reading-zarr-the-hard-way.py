# %% [markdown]
# # Reading Zarr the Hard Way
#
# In the first exercise we read a Cloud-Optimized GeoTIFF the hard way: we parsed the TIFF's binary headers by hand, chased byte offsets through the file, and decoded an image tile ourselves. In this exercise we're going to read the very same Sentinel 2 scene--same red band, same pixels--but this time from a Zarr v3 store, and again the hard way: plain HTTP requests, no Zarr library.
#
# Along the way we'll see what Zarr v3 actually looks like, how the new geospatial metadata conventions let the store describe its own CRS and geotransform in a standardized manner, how the chunk decode recipe is spelled out for us instead of implied, and where Zarr leaves us on our own when it comes to knowing what data actually exists.
#
# First, the usual imports and helpers.

# %%
import json
import urllib.error
import urllib.request

from typing import Any

import folium
import numpy as np

from griffine import Affine, Grid
from odc.geo.geom import point

# %%
EPSG_4326 = 'EPSG:4326'


def url_read(url: str) -> bytes:
    with urllib.request.urlopen(url) as response:
        return response.read()


# %% [markdown]
# Notice what's *not* here compared to exercise 1: no `struct`, no byte-range helper. A zarr store is not one big file with internal offsets: it's a tree of small objects, each fetched whole by name. We'll dig into what that difference means as we go.

# %% [markdown]
# ## Point of Interest (POI)
#
# We'll reuse our point of interest from the first exercise, so we can check our work against the values we got there.

# %%
# Point of Interest
POI = point(-121.695833, 45.373611, crs=EPSG_4326)

# Let's remind ourselves where the point is
point_map = POI.explore(name='point')
point_map

# %% [markdown]
# ## Where's the STAC search?
#
# In exercise 1 we started by querying the Earth Search STAC catalog to *find* our scene. This time there is no search: we start from a URL we were handed:

# %%
STORE_URL = 'https://raw.githubusercontent.com/jkeifer/cng-raster-formats/data/S2B_T10TFR_20231223.zarr'


# %% [markdown]
# We start with a URL here not because we already showed such a search in the last exercise, but rather because it's the honest way to start this one. That is, Zarr solves data *layout and access*, how arrays are chunked, encoded, and fetched efficiently. It does not solve data *discovery*.
#
# But neither does COG, right? We had to turn to STAC to discover what data existed for our POI and to ultimately identify a COG with data around that point. Zarr, similarly can be indexed with STAC to facilitate discovery (but it might look a bit different: COG generally contains only a single band, mapping well to a single STAC asset, where a Zarr store might map to an item as a whole, or even a collection).
#
# In this case, I had to make this Zarr store for us, as a one off, as I could not find a Zarr v3 version for this specific data. I have no STAC indexing this store, so we have no catalog to search.
#
# Yet, discovery: keep that in mind as we continue.
#
# This particular store was built from the same Sentinel 2 scene we used in exercise 1. It models the entire scene, complete with all the same bands as the STAC item, including but not limited to the red band with which we're already familiar. Except, well, for a bit of a wrinkle around that which we'll get into later...
#
# Since we'll be fetching a lot of little files from under this URL, let's make some convenience functions like we did before.


# %%
def store_read(path: str) -> bytes:
    return url_read(f'{STORE_URL}/{path}')


def store_read_json(path: str) -> dict[str, Any]:
    return json.loads(store_read(path))


def print_json(_json: dict[str, Any]) -> None:
    print(json.dumps(_json, indent=4))


# %% [markdown]
# ## The root `zarr.json`
#
# In Zarr v2, a store scattered its metadata across various `.zgroup`, `.zarray`, and `.zattrs` files (and potentially a consolidated `.zmetadata` file too). Zarr v3 consolidates each node's metadata into a single document: every group and every array has exactly one `zarr.json` describing it.
#
# The root of the store is a group, so let's fetch the root `zarr.json` and see what a v3 group document looks like.

# %%
root_meta = store_read_json('zarr.json')
print_json(root_meta)

# %% [markdown]
# That's...it. The whole thing. Sixty-six string bytes. JSON-encoded, not binary. The `node_type` property tells us this is a group, and the `zarr_format` what Zarr version we're looking at (3), plus an empty `attributes` object.
#
# Notice anything missing? Anything you expected that's not here?
#
# Consider: the root group does not list its children. It has no inventory, no manifest, nothing that says what groups or arrays live below this node. On a local filesystem you'd just list the directory; on object storage you'd list the prefix.
#
# But we're reading over plain HTTP, where there is no directory listing. We have no way to discover what is inside this group. Note the reason for this: Zarr repeatedly defers to the _storage layer_ to maintain its indices. In this case, with HTTP in the middle, we have no storage layer to interrogate.
#
# What do we do?
#
# (I'd be remiss not to point out here that [consolidated metadata](https://zarr.readthedocs.io/en/v3.0.10/user-guide/consolidated_metadata.html) would give us something of an inventory of what's inside this group. Except that [consolidated metadata is not (at time of writing) part of the spec](https://github.com/zarr-developers/zarr-specs/pull/309), any tooling support for it is considered experimental, and in some cases using it might even be a _bad_ idea. As a result, groups with consolidated metadata are not a guarantee, and we aren't going to rely on it here).

# %% [markdown]
# ## So what's in the store?
#
# Since the store won't tell us, we have to be told: the builder of this store (me) created one child group per band of the scene, named using each band's `eo:bands` common name from the STAC item where available (`B04` → `red`, `B02` → `blue`, ...) and the plain asset key where not (`scl`, `aot`, `wvp`, ...):

# %%
BANDS = (
    'aot',
    'blue',
    'cloud',
    'coastal',
    'green',
    'nir',
    'nir08',
    'nir09',
    'red',
    'rededge1',
    'rededge2',
    'rededge3',
    'scl',
    'snow',
    'swir16',
    'swir22',
    'wvp',
)

# %% [markdown]
# Just to illustrate this topic further, let's probe for a band group in two ways: by its original asset name `B04` and by its common name `red`. A group exists if its `zarr.json` does.

# %%
for name in ('B04', 'red'):
    try:
        store_read(f'{name}/zarr.json')
        print(f'{name}: exists')
    except urllib.error.HTTPError as e:
        print(f'{name}: {e.code} {e.reason}')

# %% [markdown]
# ## The `red` band group
#
# Let's fetch the `zarr.json` for the `red` group, which should describe the band we care about in this exercise.

# %%
red_group_meta = store_read_json('red/zarr.json')
print_json(red_group_meta)

# %% [markdown]
# Unlike the empty root, the band group's `attributes` are full of great metadata:
#
# * `proj:code`: the CRS as an EPSG code
# * `spatial:transform`: the six-element affine geotransform
# * `spatial:shape`: the grid's shape (cell dimensions)
# * `spatial:bbox`: the grid's extent in CRS coordinates
# * `spatial:dimensions`: the grid's dimension semantics
# * `spatial:registration`: the grid's cell registration
# * `zarr_conventions`: a list declaring which metadata conventions this group uses, each with a name, a UUID, and links to its spec and schema (the metadata itself is self-describing!)
# * `multiscales`: a description of the overview pyramid
#
# In earlier versions of this exercise, it was here where we encountered some bad news: Zarr had no geospatial extension, so data providers stashed the CRS wherever they saw fit. Part of reading "the hard way" meant hunting for this necessary information. No longer! The [Zarr Conventions framework](https://github.com/zarr-conventions) gives us standard, in-band attributes for exactly this, and this store uses them.
#
# Think back to what getting this same information out of the COG took us: unpacking the `geo_key_directory` tag (34735), cross-referencing geo keys against `geo_ascii_params`, and combining the `pixel_scale` (33550) and `tie_point` (33922) tags to assemble an affine transform. Here it's one HTTP GET and `json.loads`.
#
# Let's pull out the pieces we'll need later.

# %%
red_attrs = red_group_meta['attributes']
image_crs = red_attrs['proj:code']
transform = Affine(*red_attrs['spatial:transform'])
image_rows, image_cols = red_attrs['spatial:shape']
print(f'{image_crs=}')
print(f'{transform=}')
print(f'{image_rows=} {image_cols=}')

# %% [markdown]
# Compare those values against what we parsed out of the TIFF in exercise 1. Same CRS (UTM zone 10N), same 10 m pixel size, same origin, same 10980 × 10980 shape. It should feel familiar: the `red` group *is* the exercise 1 COG's data, on the same grid.

# %% [markdown]
# ## Multiscales: the overview pyramid
#
# The `multiscales` attribute describes the group's resolution levels: a base array `0`, plus derived levels `1` through `4`, each downsampled 2x from its parent (`resampling_method` tells us how, `average` here). If "a full-resolution image plus a stack of 2x-downsampled overviews" sounds familiar, that's because that's exactly how the COG specification defines overviews: it's exactly the overview structure of exercise 1's COG.
#
# In fact this store's `red` pyramid was copied pixel-for-pixel from that COG's overview IFDs. We didn't look at those overviews in the first exercise, simply to save time with all the requisite parsing. But it won't take too long to look at them here, so let's investigate a bit.
#
# Each level is its own array node, so each has its own `zarr.json`. We can walk the layout and survey the pyramid, fetching each level's array metadata and printing its shape along with its pixel size from the level's `spatial:transform` attribute and the bbox from the `spatial:bbox` attribute.

# %%
for layout_entry in red_attrs['multiscales']['layout']:
    level = layout_entry['asset']
    level_meta = store_read_json(f'red/{level}/zarr.json')
    level_rows, level_cols = level_meta['shape']
    level_gsd = level_meta['attributes']['spatial:transform'][0]
    level_bbox = level_meta['attributes']['spatial:bbox']
    print(
        f'level {level}: {level_rows} x {level_cols} @ {level_gsd:.2f} m, covering {level_bbox}'
    )

# %% [markdown]
# Note the pixel sizes: the levels cover the *same* full-scene extent per the bbox, at progressively coarser resolution. The sizes aren't all clean powers of two because each level's dimensions end up being the ceiling of half its parent's (10980 → 5490 → 2745 → 1373 → 687).

# %% [markdown]
# ## Array metadata
#
# Time to look at a full array document. Let's fetch the base level's `zarr.json`.

# %%
red_0_meta = store_read_json('red/0/zarr.json')
print_json(red_0_meta)

# %% [markdown]
# Here we see everything a reader needs to interpret the array's bytes, all in one place, in a human readable format no less:
#
# * `shape`: 10980 × 10980, our familiar grid
# * `data_type`: `float32`, but the COG stored `uint16`, right?
# * `chunk_grid`: regular 1024 × 1024 chunks, like the COG's full-resolution IFD (so at this level the Zarr chunks correspond 1:1 with the COG's tiles)
# * `chunk_key_encoding`: chunk keys are named `c/{row}/{col}` with `/` as the separator (v2 used keys like `7.0`; v3 nests them under `c/`)
# * `fill_value`: what an *uninitialized* part of the array reads as (`-0.10000000149011612` is `-0.1` rendered from float32 into JSON's double precision). Note it's in the array's own `data_type`, i.e. the decoded value, not a stored DN. We'll come back to what this does and doesn't mean.
# * `dimension_names`: `["y", "x"]` (in v2, dimension naming was `_ARRAY_DIMENSIONS`, an attribute convention invented by xarray; in v3 it's part of the core spec)
# * `codecs`: the pipeline that turns array values into stored chunk bytes (this is my favorite part!)

# %% [markdown]
# ### The `codecs` pipeline: a declared recipe
#
# Think back to everything we had to figure out to decode a tile of the COG, and where each piece of information was hiding:
#
# | This store's codec             | What it does (encode direction)                     | Where the COG hid the same fact                     |
# | ------------------------------ | --------------------------------------------------- | --------------------------------------------------- |
# | `numcodecs.fixedscaleoffset`   | float32 reflectance → uint16 DNs via scale/offset    | `GDAL_METADATA` tag (42112), values in ad hoc XML    |
# | `numcodecs.delta`              | difference each value from its predecessor           | `predictor` tag (317) = 2, horizontal differencing   |
# | `bytes`                        | serialize values little-endian                       | the `II` byte-order mark in the file header          |
# | `zstd`                         | compress the bytes                                   | `compression` tag (259) = 8, i.e. DEFLATE            |
#
# The COG _implied_ its decode recipe, scattered across TIFF tags and conventions we had to know to go looking for (quick, what's tag 317 again?). The Zarr array _declares_ its recipe as an ordered pipeline, in the same document as the shape and dtype. To read a chunk, you run the pipeline backwards: decompress, deserialize, un-difference, un-scale. No lookup tables, no spec spelunking. It's not perfect, admittedly, as one still needs to know how to compose the pipeline operations with a bit of the other metadata, but still, we can see the clear improvement in legibility over TIFF.
#
# And this explains the `data_type` difference. The COG's canonical array is `uint16` digital numbers (DNs), with scale and offset as side metadata a reader may or may not notice. Remember, _we_ had to read the GDAL XML and apply it ourselves. Here, scaling is _part of the codec chain_, so the canonical array is `float32` reflectance. A naive reader gets DNs from the COG but proper reflectance values from this store.
#
# ### Not every band declares the same recipe
#
# The recipe belongs to the array, so different arrays can declare different recipes. `scl` is the scene classification layer: unsigned 8-bit class codes (vegetation, cloud, snow, ...) on a 20 m grid. Class codes have no scale/offset---reflectance math on category labels would be nonsense---so its chain should look different. Let's check the `codecs` (and `data_type` and `fill_value`) in its base array's metadata.

# %%
print_json(store_read_json('scl/0/zarr.json'))

# %% [markdown]
# Plain `uint8`, no `fixedscaleoffset`, fill value of the nodata class code `0`.

# %% [markdown]
# ## A quick look: the whole scene in one request
#
# Before we zoom to our POI at full resolution, let's put the pyramid to work. Level 4 is 687 × 687 pixels, smaller even than one 1024 × 1024 chunk from our full-res array. Take a look at its metadata:

# %%
red_4_meta = store_read_json('red/4/zarr.json')
print_json(red_4_meta)

# %% [markdown]
# The chunk shape was clamped to the array shape, so the entire level is a single chunk: `red/4/c/0/0`. One GET retrieves the whole-scene overview. This is the same trick that makes slippy-map zoom levels fast, and exactly why multiscale layouts like this and COG's overviews exist.
#
# Let's fetch it and work through the decode recipe step by step, just like we did for the COG tile. First, the raw bytes.

# %%
quicklook_bytes = store_read('red/4/c/0/0')
print(f'{len(quicklook_bytes)} bytes')
print(f'first four bytes: {quicklook_bytes[:4].hex(" ")}')

# %% [markdown]
# Recognize the opening bytes? Yeah me neither. Turns out `28 b5 2f fd` is meaningful: it's the zstd magic number. The last codec applied when encoding is the first we undo when decoding, and the metadata said that codec is `zstd`, so this is a good sign.
#
# Decompressing it needs no third-party help at all: Python 3.14 added zstd to the standard library as `compression.zstd`. We'll do the same decompression step we did in exercise 1's with the stdlib `zlib`, just with a different algorithm.

# %%
from compression import zstd

quicklook_decompressed = zstd.decompress(quicklook_bytes)
print(f'{len(quicklook_decompressed)} decompressed bytes')

# %% [markdown]
# Does that byte count make sense? 687 × 687 pixels × 2 bytes per `uint16` DN = 943,938 bytes. Remember, we have `uint16` because we're in the middle of the pipeline: the `fixedscaleoffset` codec's `astype` is `<u2`, so everything downstream of it operates on uint16 values.
#
# Next we undo the `bytes` codec (interpret the buffer as little-endian uint16; `numpy` handles this directly, no `struct` gymnastics required) and the `delta` codec (a cumulative sum restores the original values from the differences).
#
# One subtlety compared to exercise 1: TIFF's predictor 2 restarts its differencing at every row, so back then we ran a cumulative sum per row (`axis=1`). The `numcodecs` delta codec differences the *flattened* chunk: one long run, no row resets. We do that with a single cumulative sum over the whole buffer, i.e., with no axis.

# %%
quicklook_dns = np.cumsum(
    np.frombuffer(quicklook_decompressed, dtype='<u2'),
    dtype='<u2',
)
quicklook_dns

# %% [markdown]
# Now we reshape to the chunk shape and undo the `fixedscaleoffset` codec. Per its configuration, decoding maps stored DNs back to physical values as `value = dn / scale + offset`. Here that's `dn / 10000 - 0.1`, just like what we applied to the COG tile, except this time the recipe told us so.

# %%
quicklook_array = (
    quicklook_dns.reshape(red_4_meta['chunk_grid']['configuration']['chunk_shape'])
    / red_4_meta['codecs'][0]['configuration']['scale']
    + red_4_meta['codecs'][0]['configuration']['offset']
)
quicklook_array

# %% [markdown]
# Reflectance values! Let's throw them on the map, using the group's `spatial:bbox` (converted to lat/lon) for the overlay bounds, the same way we placed the COG tile in exercise 1.

# %%
bbox_min_x, bbox_min_y, bbox_max_x, bbox_max_y = red_attrs['spatial:bbox']
sw_lon, sw_lat = (
    point(bbox_min_x, bbox_min_y, crs=image_crs).to_crs(EPSG_4326).coords[0]
)
ne_lon, ne_lat = (
    point(bbox_max_x, bbox_max_y, crs=image_crs).to_crs(EPSG_4326).coords[0]
)

# let's do a slight, conservative constrast stretch here;
# resampling averages out the natural constrast of the image
p_low, p_high = np.percentile(quicklook_array, (0, 99.9))
stretched = np.clip(quicklook_array, p_low, p_high)
stretched = (stretched - p_low) / (p_high - p_low)

scene_map = POI.explore(name='point')
folium.raster_layers.ImageOverlay(
    stretched,
    bounds=[[sw_lat, sw_lon], [ne_lat, ne_lon]],
    name='quicklook',
).add_to(scene_map)
folium.LayerControl().add_to(scene_map)
scene_map.fit_bounds([[sw_lat, sw_lon], [ne_lat, ne_lon]])
scene_map

# %% [markdown]
# ## Locating our POI
#
# To load the full-resolution tile containing our POI, we can use the same process as in exercise 1: project the POI into the image CRS, build a `griffine` grid from the shape and affine transform, and find the pixel containing the point. The difference is where we source those metadata inputs: last time we assembled them from binary TIFF tags, but this time they come from the Zarr Convention attributes we read a few cells ago.

# %%
POI_proj = POI.to_crs(image_crs)
grid = Grid(rows=image_rows, cols=image_cols).add_transform(transform)
cell = grid.point_to_cell(POI_proj)
print(f'row={cell.row}, col={cell.col}')

# %% [markdown]
# Does that result look right? The coordinates should be identical to those found in exercise 1.
#
# Now, we need to find which chunk contains that pixel. Again, we can tile the grid by the chunk shape and locate our point in chunk coordinates, just like we did with the COG's tile grid.

# %%
chunk_rows, chunk_cols = red_0_meta['chunk_grid']['configuration']['chunk_shape']
chunk_grid = grid.tile_via(Grid(rows=chunk_rows, cols=chunk_cols))
poi_chunk = chunk_grid.point_to_tile(POI_proj)
print(f'chunk_row={poi_chunk.row}, chunk_col={poi_chunk.col}')

# %% [markdown]
# ### Addressing: keys instead of offsets
#
# In exercise 1, knowing "tile (7, 0)" wasn't enough to read anything: we had to transform those 2-dimensional tile coordinates into a linear index, then look up the byte offset and byte length of that linear index in the `tile_offsets` and `tile_byte_counts` tags, both of which needed to be parsed correctly. Only then could we read the chunk, via a range request into the one big file.
#
# Here, the chunk coordinates _are_ the address. Chunk (7, 0) of array `red/0` lives at the key `red/0/c/7/0`, by construction. No offset table, no linear index, and no `Range` header either. The naming convention replaces the byte-offset index, and each chunk is fetched whole, by name.
#
# This seems much easier, more convenient, yeah? Recognize that this convenience cuts both ways, however. The COG's tile index may have been annoying to parse, but it was an inventory: it told us exactly which tiles existed and where. Zarr's computed addressing requires no inventory, but this also means we have no inventory with in the format. The metadata cannot tell us which chunks actually exist.
#
# Again, this is Zarr deferring indexing to the storage layer, relying on storage layer resolution of a chunk key to bytes. It's not that no index exists at all---we must have _something_ that can resolve a chunk lookup to a stream of bytes---but that index is not part of Zarr, and cannot be accessed without access to the storage layer, as we saw before with group member discovery.

# %%
poi_chunk_key = f'red/0/c/{poi_chunk.row}/{poi_chunk.col}'
poi_chunk_key

# %% [markdown]
# ## Reading the POI chunk
#
# We already walked the decode recipe step by step for the quicklook, so let's automate it this time by wrapping all that up into a function. The provided function below reads any specified chunk of a reflectance band, taking each required parameters (chunk shape, scale, offset, etc.) from the array's metadata.


# %%
def read_chunk(band: str, level: int, chunk_row: int, chunk_col: int) -> np.ndarray:
    meta = store_read_json(f'{band}/{level}/zarr.json')
    codecs = {c['name']: c.get('configuration', {}) for c in meta['codecs']}
    scale_offset = codecs['numcodecs.fixedscaleoffset']

    raw = store_read(f'{band}/{level}/c/{chunk_row}/{chunk_col}')
    dns = np.cumsum(
        np.frombuffer(zstd.decompress(raw), dtype=codecs['numcodecs.delta']['dtype']),
        dtype=codecs['numcodecs.delta']['dtype'],
    )
    chunk = dns.reshape(meta['chunk_grid']['configuration']['chunk_shape'])
    return chunk / scale_offset['scale'] + scale_offset['offset']


# %% [markdown]
# A quick note on that `reshape`: a decoded chunk buffer is always the full chunk shape from `zarr.json`, even at the ragged edges of the array. 10980 isn't a multiple of 1024, so the last row and column of chunks extend 284 pixels past the array bounds. Zarr stores those edge chunks as full-size 1024 × 1024 buffers padded with `fill_value` beyond the edge.
#
# Now let's read our POI's chunk and pull out the pixel. Again, we'll need to convert our cell coords from array-relative to chunk-relative.

# %%
poi_chunk_array = read_chunk('red', 0, poi_chunk.row, poi_chunk.col)

in_chunk_row = cell.row % chunk_rows
in_chunk_col = cell.col % chunk_cols
poi_reflectance = poi_chunk_array[in_chunk_row, in_chunk_col]
print(f'in-chunk coords: ({in_chunk_row}, {in_chunk_col})')
print(f'POI red reflectance: {poi_reflectance:.4f}')

# %% [markdown]
# Is this the value we expect? Did it work???

# %% [markdown]
# Now let's map this chunk and see what it looks like compared to execise 1.

# %%
# the overlay bounds are the _chunk's_ extent, not the scene's: same as
# exercise 1, we take the chunk's origin and antiorigin and project them
chunk_nw_lon, chunk_nw_lat = (
    point(*poi_chunk.origin.coords[0], crs=image_crs).to_crs(EPSG_4326).coords[0]
)
chunk_se_lon, chunk_se_lat = (
    point(*poi_chunk.antiorigin.coords[0], crs=image_crs).to_crs(EPSG_4326).coords[0]
)

scene_map = POI.explore(name='point')
folium.raster_layers.ImageOverlay(
    poi_chunk_array,
    bounds=[[chunk_se_lat, chunk_nw_lon], [chunk_nw_lat, chunk_se_lon]],
    name='tile',
).add_to(scene_map)
folium.LayerControl().add_to(scene_map)
scene_map.fit_bounds([[sw_lat, sw_lon], [ne_lat, ne_lon]])
scene_map

# %% [markdown]
# ## The bands that aren't there
#
# Way back at the beginning, we said this store models every band of the scene, but hinted at a wrinkle. Let's investigate by looking at the `green` band now. We'll fetch its base array's metadata and compare it to `red`'s.

# %%
green_0_meta = store_read_json('green/0/zarr.json')
for field in ('shape', 'data_type', 'fill_value', 'codecs'):
    print(f'{field}: match={green_0_meta[field] == red_0_meta[field]}')

# %% [markdown]
# Identical in every way that matters: same grid, same dtype, same fill value, same codec chain. By the metadata, `green` is exactly as real as `red`. So let's read the same chunk we just read for red:

# %%
try:
    store_read('green/0/c/7/0')
except urllib.error.HTTPError as e:
    print(f'{e.code} {e.reason}')

# %% [markdown]
# There is no chunk. And it's not just this one: `green` has _zero_ chunk objects. Only `red` was materialized when this store was built (because I didn't want to store all this data for no good reason); the other sixteen bands are metadata-only, their structure synthesized from the STAC item we saw in exercise 1, without ever opening their respective COGs.
#
# Is a missing chunk an error? Not to zarr! Sparse arrays are a _feature_: a chunk that was never written simply reads as `fill_value`, so you don't have to spend storage on regions with no data. Watch what a real Zarr reader does with this band:

# %%
import zarr

green_easy = zarr.open_array(f'{STORE_URL}/green/0', mode='r')
green_easy[7168:7172, 208:212]

# %% [markdown]
# No exception, no warning: the underlying 404 is silently translated into a window of `-0.1`, the fill value, indistinguishable from a region of the scene that was actually observed and actually empty. Is this desriable behaivor? Bad? What do you think?
#
# ### An aside: `fill_value` is not nodata
#
# It's tempting to read that last sentence as "so `-0.1` is the nodata value," but the spec is narrower than that. Zarr v3 says only that `fill_value` "provides an element value to use for uninitialised portions of the Zarr array." It answers _what do I get where there is no chunk_. It does _not_ say "these pixels are invalid," and it turns out Zarr v3 has no way to say that at all, at least in the core spec. Because of Zarr's Convention extensibility we see a possible solution to this gap: [`missing_value`](https://github.com/zarr-conventions/missing_value)), but this still a proposal.
#
# While building this store I leaned on that gap deliberately, setting `fill_value` to the physical value that the COG's nodata DN decodes to. Here that means that "never written" and "written, but nodata" look the same. nodata means "mask these pixels", and this is what GDAL does, for example, but we don't have that so the best we can do is make fill value match what the original nodata value decodes to. `xarray`, notably, for v3 stores ignores `fill_value` for masking entirely and looks for a CF `_FillValue`, which this store doesn't have. So the same bytes are masked by one tool and not the other. 😕
#
# Note also which side of the codec chain `fill_value` lives on. It's typed by `data_type`, so it's a _decoded_ float32 value, `-0.1`, not the `uint16` DN `0` that's actually absent from storage. CF's `_FillValue`, confusingly, is conventionally the opposite: the packed value. Two "the same" concepts, two different numbers.
#
# Exercise 1 had none of this ambiguity, but only because it had no concept at all: the COG's nodata was a null-terminated ASCII string in a GDAL-specific tag that we parsed and cast ourselves.
#
# ## The discovery gap, summarized
#
# We've hit the discovery gap again, at the chunk level, a deeper version of the problem we met at the root group. The metadata told us what the array would look like _if it had data_; it cannot tell us which chunks exist, because it doesn't know anything about the actual chunks. It has no manifest.
#
# So Zarr leaves us with the same gap at three levels:
#
# * **Catalog level**: nothing tells you what stores exist or what's in them, you start from a URL someone handed you (but **STAC can fix this, and COG has the same gap**)
# * **Group level**: nothing tells you what subgroups or arrays exist, unless you have access to the storage layer (with caveats: we could use consolidated metadata, maybe, and notice that multiscales _is_ an array manifest?)
# * **Chunk level**: nothing tells you which chunks exist, absence is silently read as fill ([COG can support something like this with a reader/writer that supports it](https://gdal.org/en/stable/drivers/raster/gtiff.html#sparse-files), and it could be useful in certain circumstances, but is not the default nor common, and this mode uses a specific sentinel values to explicitly indicate an empty segment)
#
# What's missing from Zarr, in all these cases, is an inventory, something that says "here is exactly what data exists, and where the bytes live." COG has one in the tile offset table: it's clunky, but it's an inventory. Zarr, by design, does not. In exercise 3 we'll build exactly that missing inventory by hand using kerchunk, and see how the modern tools (VirtualiZarr, Icechunk) turn "a manifest of where the bytes live" into a whole virtual-dataset ecosystem.

# %% [markdown]
# ## Additional exercises to consider later
#
# * Read the edge chunk `red/0/c/10/10` with `read_chunk` and confirm the out-of-bounds region beyond row/column 740 is all fill value (-0.1).
# * Generalize `read_chunk` to handle `scl`'s codec chain (no `fixedscaleoffset`), read its base array, and look up the class code at our POI in the [SCL class table](https://sentinels.copernicus.eu/web/sentinel/technical-guides/sentinel-2-msi/level-2a/algorithm-overview).
# * How many requests would it take to read all of `red` at full resolution from this store? How would you do the equivalent read from the COG, and how many requests could that take in theory?
# * Use each level's `spatial:transform` to locate the POI's pixel on every level of the pyramid, and confirm the reflectance values are consistent across levels.
# * Zarr v3 has a `sharding` codec that packs many chunks into one stored object with an internal index; sounds rather COG-like, no? Read up on it and consider: what would sharding change about the request patterns and the discovery story we saw here?
#
# Any other cool ideas? Let me know and/or share with the group.
