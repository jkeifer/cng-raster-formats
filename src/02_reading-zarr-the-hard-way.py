# %% [markdown]
# # Reading Zarr the Hard Way
#
# In the first exercise we read a Cloud-Optimized GeoTIFF the hard way: we parsed the TIFF's binary headers by hand, chased byte offsets through the file, and decoded an image tile ourselves. In this exercise we're going to read the very same Sentinel 2 scene--same red band, same pixels--but this time from a Zarr v3 store, and again the hard way: plain HTTP requests, no zarr library (well, almost none; we'll allow ourselves a decompressor, same as we allowed `zlib` last time).
#
# Along the way we'll see what zarr v3 looks like on the wire, how the new geospatial metadata conventions let the store describe its own CRS and geotransform (this is new and exciting!), how the chunk decode recipe is spelled out for us instead of implied, and--because every silver lining has a cloud--where zarr leaves us on our own when it comes to knowing what data actually exists.
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
# Notice what's *not* here compared to exercise 1: no `struct`, no byte-range helper. A zarr store is not one big file with internal offsets--it's a tree of small objects, each fetched whole by name. We'll dig into what that difference means as we go.

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
# In exercise 1 we started by querying the Earth Search STAC catalog to *find* our scene. This time there is no search--we start from a URL we were handed:

# %%
STORE_URL = 'https://raw.githubusercontent.com/jkeifer/cng-raster-formats/data/S2B_T10TFR_20231223.zarr'


# %% [markdown]
# That's not laziness (okay, not *only* laziness); it's the honest way to start a zarr exercise. Zarr solves data *layout* and *access*: how arrays are chunked, encoded, and fetched efficiently. It does not solve data *discovery*. There is no public "zarr catalog" to search the way we searched Earth Search for COGs, so in practice zarr work starts exactly like this: somebody hands you a store URL. And as we'll see, the discovery gap runs deeper than the catalog level--even once we're *inside* the store, the metadata won't tell us everything we might expect. Keep that thought; it becomes the whole point of exercise 3.
#
# This particular store was built from the same Sentinel 2 scene we used in exercise 1. It models the entire scene--every single-band asset in the STAC item--though (spoiler alert) we'll discover an interesting wrinkle about that later.
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
# A zarr v2 store scattered its metadata across `.zgroup`, `.zarray`, and `.zattrs` files (plus a consolidated `.zmetadata` if you were lucky). Zarr v3 consolidates each node's metadata into a single document: every group and every array has exactly one `zarr.json` describing it.
#
# The root of the store is a group, so let's fetch the root `zarr.json` and see what a v3 group document looks like.

# %%
#| scrub-note: cell0
root_meta = store_read_json('zarr.json')
print_json(root_meta)

# %% [markdown]
# That's... the whole thing. Sixty-six bytes. A `node_type` telling us this is a group, the `zarr_format` version, and an empty `attributes` object.
#
# Notice anything missing? The root group does not list its children. There is no inventory, no manifest, nothing that says what groups or arrays live below this node. On a local filesystem you'd just list the directory; on object storage you'd list the prefix. But we're reading over plain HTTP, where there is no directory listing--and the metadata itself has nothing to offer. Our first taste of the discovery gap, one level down from the catalog: even standing inside the store, we can't ask it what it contains.
#
# For reference, here's the v2-to-v3 decoder ring we'll be filling in as we explore:
#
# | zarr v2                                  | zarr v3                                    |
# | ---------------------------------------- | ------------------------------------------ |
# | `.zgroup` + `.zarray` + `.zattrs` per node | one `zarr.json` per node                 |
# | chunk keys like `7.0`                    | chunk keys like `c/7/0`                    |
# | `compressor` + `filters`                 | a single ordered `codecs` pipeline         |
# | `_ARRAY_DIMENSIONS` attr (xarray's hack) | `dimension_names`, part of the core spec   |

# %% [markdown]
# ## So what's in the store?
#
# Since the store won't tell us, we have to be told: the builder of this store created one child group per band of the scene, named using each band's `eo:bands` common name from the STAC item where available (`B04` → `red`, `B02` → `blue`, ...) and the plain asset key where not (`scl`, `aot`, `wvp`, ...):

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
# Just to drive home that this knowledge came from outside the store: let's probe for a band group by its original asset name `B04`, and by its common name `red`. A group exists if its `zarr.json` does.

# %%
#| scrub-note: cell1
for name in ('B04', 'red'):
    try:
        store_read(f'{name}/zarr.json')
        print(f'{name}: exists')
    except urllib.error.HTTPError as e:
        print(f'{name}: {e.code} {e.reason}')

# %% [markdown]
# The store answers "yes" or "404"--but only if we already know what to ask for. Guessing keys is not a discovery mechanism (writes that down for later...).

# %% [markdown]
# ## The `red` band group: the conventions exist now!
#
# Let's fetch the `zarr.json` for the `red` group, which should describe the band we care about.

# %%
#| scrub-note: cell2
red_group_meta = store_read_json('red/zarr.json')
print_json(red_group_meta)

# %% [markdown]
# Now *that* is more like it. Unlike the empty root, the band group's `attributes` are full of geospatial goodness:
#
# * `proj:code`: the CRS, as an EPSG code, sitting right there in plain text
# * `spatial:transform`: the six-element affine geotransform
# * `spatial:shape`, `spatial:bbox`, `spatial:dimensions`, `spatial:registration`: the grid's shape, extent in CRS coordinates, dimension semantics, and cell registration
# * `zarr_conventions`: a list *declaring* which metadata conventions this group uses, each with a name, a UUID, and links to its spec and schema--the metadata is self-describing
# * `multiscales`: a description of the overview pyramid (more on this next)
#
# When this workshop was first written, this was the spot where we had to deliver the bad news: zarr had no geospatial extension, so data providers stashed the CRS wherever they saw fit--usually in a STAC record somewhere outside the store--and reading "the hard way" meant hunting for it. No longer! The [GeoZarr](https://github.com/zarr-developers/geozarr-spec) effort and the [zarr-conventions](https://github.com/zarr-conventions) work give us standard, in-band attributes for exactly this, and this store uses them.
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
# Compare those values against what we parsed out of the TIFF in exercise 1. Same CRS (UTM zone 10N), same 10 m pixel size, same origin, same 10980 × 10980 grid. It should feel familiar: the `red` group *is* the exercise 1 COG's data, on the COG's exact grid.

# %% [markdown]
# ## Multiscales: the overview pyramid
#
# The `multiscales` attribute describes the group's resolution levels: a base array `0`, plus derived levels `1` through `4`, each downsampled 2x from its parent (`resampling_method` tells us how--`average` here). If "a full-resolution image plus a stack of 2x-downsampled overviews" sounds familiar, it should: it's exactly the overview structure of exercise 1's COG. In fact this store's `red` pyramid was copied pixel-for-pixel from that COG's overview IFDs.
#
# Each level is its own array node, so each has its own `zarr.json`. Let's walk the layout and survey the pyramid: fetch each level's array metadata and print its shape along with its pixel size from the level's `spatial:transform` attribute.

# %%
#| scrub-note: cell3
for layout_entry in red_attrs['multiscales']['layout']:
    level = layout_entry['asset']
    level_meta = store_read_json(f'red/{level}/zarr.json')
    level_rows, level_cols = level_meta['shape']
    level_gsd = level_meta['attributes']['spatial:transform'][0]
    print(f'level {level}: {level_rows} x {level_cols} @ {level_gsd:.2f} m')

# %% [markdown]
# Note the pixel sizes: the levels cover the *same* full-scene extent (check `spatial:bbox` on each level if you don't believe it) at progressively coarser resolution, and the sizes aren't all clean powers of two because each level's dimensions are the ceiling of half its parent's (10980 → 5490 → 2745 → 1373 → 687).

# %% [markdown]
# ## Array metadata: the whole story in one document
#
# Time to look at a full array document. Let's fetch the base level's `zarr.json`.

# %%
#| scrub-note: cell4
red_0_meta = store_read_json('red/0/zarr.json')
print_json(red_0_meta)

# %% [markdown]
# Everything a reader needs to interpret the array's bytes, in one place:
#
# * `shape`: 10980 × 10980, our familiar grid
# * `data_type`: `float32`--wait, *what*? The COG stored `uint16`! Hold that thought; the answer is in the codecs.
# * `chunk_grid`: regular 1024 × 1024 chunks--the exact tile size of the COG's full-resolution IFD, so at this level the zarr chunks correspond 1:1 with the COG's tiles
# * `chunk_key_encoding`: chunk keys are named `c/{row}/{col}` with `/` as the separator (v2 used keys like `7.0`; v3 nests them under `c/`)
# * `fill_value`: the value a reader should assume where there's no data; `-0.10000000149011612` is just `-0.1` rendered from float32 into JSON's double precision
# * `dimension_names`: `["y", "x"]`--in v2, dimension naming was `_ARRAY_DIMENSIONS`, an attribute convention invented by xarray; in v3 it's part of the core spec
# * `codecs`: the pipeline that turns array values into stored chunk bytes, and the star of our next section

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
# The COG *implied* its decode recipe, scattered across TIFF tags and conventions we had to know to go looking for (quick, what's tag 317 again?). The zarr array *declares* its recipe as an ordered pipeline, in the same document as the shape and dtype. To read a chunk, you run the pipeline backwards: decompress, deserialize, un-difference, un-scale. No lookup tables, no spec spelunking.
#
# And this explains the `data_type` surprise. The COG's canonical array is `uint16` digital numbers (DNs), with scale and offset as side metadata a reader may or may not notice--remember, *we* had to read the GDAL XML and apply it ourselves. Here, scaling is *part of the codec chain*, so the canonical array is `float32` reflectance. A naive reader gets DNs from the COG but proper reflectance values from this store. Same bytes-on-disk philosophy, very different contract with the reader.
#
# ### Not every band declares the same recipe
#
# The recipe belongs to the array, so different arrays can declare different recipes. `scl` is the scene classification layer: unsigned 8-bit class codes (vegetation, cloud, snow, ...) on the 20 m grid. Class codes have no scale/offset--reflectance math on category labels would be nonsense--so its chain should look different. Let's check the `codecs` (and `data_type` and `fill_value`) in its base array's metadata.

# %%
#| scrub-note: cell5
scl_0_meta = store_read_json('scl/0/zarr.json')
print_json(
    {
        'data_type': scl_0_meta['data_type'],
        'fill_value': scl_0_meta['fill_value'],
        'codecs': scl_0_meta['codecs'],
    }
)

# %% [markdown]
# Plain `uint8`, no `fixedscaleoffset`, fill value of the nodata class code `0`. Each array tells you exactly how to read it--you just have to read the recipe first.

# %% [markdown]
# ## A quick look: the whole scene in one request
#
# Before we zoom to our POI at full resolution, let's put the pyramid to work. Level 4 is 687 × 687 pixels--smaller than one 1024 × 1024 chunk. Take a look at its metadata:

# %%
#| scrub-note: cell6
red_4_meta = store_read_json('red/4/zarr.json')
print(f'shape: {red_4_meta["shape"]}')
print(f'chunk shape: {red_4_meta["chunk_grid"]["configuration"]["chunk_shape"]}')

# %% [markdown]
# The chunk shape was clamped to the array shape, so the entire level is a single chunk: `red/4/c/0/0`. One GET gets us a whole-scene overview--this is the same trick that makes slippy-map zoom levels fast, and exactly why multiscale layouts exist.
#
# Let's fetch it and work through the decode recipe step by step, just like we did for the COG tile. First, the raw bytes.

# %%
#| scrub-note: cell7
quicklook_bytes = store_read('red/4/c/0/0')
print(f'{len(quicklook_bytes)} bytes')
print(f'first four bytes: {quicklook_bytes[:4].hex(" ")}')

# %% [markdown]
# Recognize the opening bytes? `28 b5 2f fd` is the zstd magic number--our old friend the file signature, making a reappearance from exercise 1 (where TIFF greeted us with `42`). The last codec applied when encoding is the first we undo when decoding, and the metadata said that codec is `zstd`.
#
# `numcodecs` (the same library that provides the scale-offset and delta codecs to zarr) gives us a zstd decoder, which we'll permit ourselves in the same spirit as exercise 1's `zlib`.

# %%
from numcodecs import Zstd

# %%
#| scrub-note: cell8
quicklook_decompressed = Zstd().decode(quicklook_bytes)
print(f'{len(quicklook_decompressed)} decompressed bytes')

# %% [markdown]
# Does that byte count make sense? 687 × 687 pixels × 2 bytes per `uint16` DN = 943,938 bytes. (Why uint16 when the array's `data_type` said float32? Because we're standing in the *middle* of the pipeline: the `fixedscaleoffset` codec's `astype` is `<u2`, so everything downstream of it--delta, bytes, zstd--operates on uint16 values.)
#
# Next we undo the `bytes` codec (interpret the buffer as little-endian uint16; `numpy` handles this directly, no `struct` gymnastics required) and the `delta` codec (a cumulative sum restores the original values from the differences).
#
# One subtlety for exercise 1 veterans: TIFF's predictor 2 restarts its differencing at every row, so back then we ran a cumulative sum per row (`axis=1`). The `numcodecs` delta codec differences the *flattened* chunk--one long run, no row resets--so here it's a single cumulative sum over the whole buffer. And note the dtype on the cumsum: the differences of uint16 values wrap around at 65536, so summing them back must wrap the same way.

# %%
#| scrub-note: cell9
quicklook_dns = np.cumsum(
    np.frombuffer(quicklook_decompressed, dtype='<u2'),
    dtype='<u2',
)
quicklook_dns

# %% [markdown]
# Now we reshape to the chunk shape and undo the `fixedscaleoffset` codec. Per its configuration, decoding maps stored DNs back to physical values as `value = dn / scale + offset`, i.e. `dn / 10000 - 0.1`--precisely the scale and offset we applied to the COG tile, except this time the recipe told us so.

# %%
#| scrub-note: cell10
quicklook_array = (
    quicklook_dns.reshape(red_4_meta['chunk_grid']['configuration']['chunk_shape'])
    / 10000.0
    - 0.1
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

scene_map = POI.explore(name='point')
folium.raster_layers.ImageOverlay(
    # atmospheric correction can push reflectance slightly outside [0, 1]
    # (bright snow!), so clip for display
    np.clip(quicklook_array, 0, 1),
    bounds=[[sw_lat, sw_lon], [ne_lat, ne_lon]],
    name='quicklook',
).add_to(scene_map)
folium.LayerControl().add_to(scene_map)
scene_map.fit_bounds([[sw_lat, sw_lon], [ne_lat, ne_lon]])
scene_map

# %% [markdown]
# There's our scene--and our POI sitting on it. Time to zoom in.

# %% [markdown]
# ## Locating our POI
#
# Now the same locate-the-cell flow as exercise 1: project the POI into the image CRS, build a `griffine` grid from the shape and affine transform, and find the pixel containing the point. The difference is where the inputs came from--last time we assembled them from binary TIFF tags; this time they came from the convention attributes we read a few cells ago.

# %%
#| scrub-note: cell11
POI_proj = POI.to_crs(image_crs)
grid = Grid(rows=image_rows, cols=image_cols).add_transform(transform)
cell = grid.point_to_cell(POI_proj)
print(f'row={cell.row}, col={cell.col}')

# %% [markdown]
# If everything is right, that's the *identical* pixel coordinate we found in exercise 1--the `red` group's level 0 sits on the COG's exact grid, so the math lands on the same cell.
#
# Next, which chunk holds that pixel? We can tile the grid by the chunk shape and locate our point in chunk coordinates, just like we did with the COG's tile grid.

# %%
#| scrub-note: cell12
chunk_rows, chunk_cols = red_0_meta['chunk_grid']['configuration']['chunk_shape']
chunk_grid = grid.tile_via(Grid(rows=chunk_rows, cols=chunk_cols))
poi_chunk = chunk_grid.point_to_tile(POI_proj)
print(f'chunk_row={poi_chunk.row}, chunk_col={poi_chunk.col}')

# %% [markdown]
# ### Addressing: keys instead of offsets
#
# Pause on what happens next, because this is the heart of the COG/zarr difference.
#
# In exercise 1, knowing "tile (7, 0)" wasn't enough to read anything: we had to compute the tile's linear index, then look up its byte offset and byte length in the `tile_offsets` and `tile_byte_counts` tags--an index we had to *fetch and parse* before we could read a single pixel--and then issue a range request into one big file.
#
# Here, the chunk coordinates *are* the address. Chunk (7, 0) of array `red/0` lives at the key `red/0/c/7/0`, by construction. No offset table, no linear index, no `Range` header--the naming convention replaces the byte-offset index, and each chunk is fetched whole by name.
#
# That cuts both ways, though. The COG's tile index was annoying to parse, but it was an *inventory*: it told us exactly which tiles existed and where. Zarr's computed addressing needs no inventory to read--and provides none. The metadata cannot tell us which chunks actually exist. Remember that; it's about to matter.

# %%
poi_chunk_key = f'red/0/c/{poi_chunk.row}/{poi_chunk.col}'
poi_chunk_key

# %% [markdown]
# ## Reading the POI chunk
#
# We already walked the decode recipe step by step for the quicklook, so let's do what we did in exercise 1 and wrap it in a function. This one reads any chunk of any level of a reflectance band, taking every parameter--chunk shape, delta dtype, scale, offset--from the array's declared metadata rather than hardcoding it.


# %%
def read_chunk(band: str, level: int, chunk_row: int, chunk_col: int) -> np.ndarray:
    meta = store_read_json(f'{band}/{level}/zarr.json')
    codecs = {c['name']: c.get('configuration', {}) for c in meta['codecs']}
    scale_offset = codecs['numcodecs.fixedscaleoffset']

    raw = store_read(f'{band}/{level}/c/{chunk_row}/{chunk_col}')
    dns = np.cumsum(
        np.frombuffer(Zstd().decode(raw), dtype=codecs['numcodecs.delta']['dtype']),
        dtype=codecs['numcodecs.delta']['dtype'],
    )
    chunk = dns.reshape(meta['chunk_grid']['configuration']['chunk_shape'])
    return chunk / scale_offset['scale'] + scale_offset['offset']


# %% [markdown]
# One note on that `reshape`: a decoded chunk buffer is *always* the full chunk shape from `zarr.json`, even at the ragged edges of the array. 10980 isn't a multiple of 1024, so the last row and column of chunks extend 284 pixels past the array bounds--and zarr v3 stores those edge chunks as full-size 1024 × 1024 buffers padded with `fill_value` beyond the edge. (The level 4 quicklook dodged this only because its chunk shape was clamped to exactly the array shape.)
#
# Now let's read our POI's chunk and pull out the pixel. The chunk covers a 1024 × 1024 window of the full grid starting at row `chunk_row * 1024`, so our pixel's position *within* the chunk is its full-image position minus the chunk's origin.

# %%
#| scrub-note: cell13
poi_chunk_array = read_chunk('red', 0, poi_chunk.row, poi_chunk.col)

in_chunk_row = cell.row - (poi_chunk.row * chunk_rows)
in_chunk_col = cell.col - (poi_chunk.col * chunk_cols)
poi_reflectance = poi_chunk_array[in_chunk_row, in_chunk_col]
print(f'in-chunk coords: ({in_chunk_row}, {in_chunk_col})')
print(f'POI red reflectance: {poi_reflectance:.4f}')

# %% [markdown]
# **Question**: In exercise 1, after decompressing, un-predicting, and scale/offsetting the COG tile, what value did we get for this same pixel? What DN does our reflectance value here correspond to?

# %% [markdown]
# <!-- scrub-omit -->
# **Answer**: The same value: reflectance 0.2736, from DN 3736 (0.2736 = 3736 / 10000 - 0.1). This is not a happy coincidence or an "agrees to within rounding" situation--the store's DNs round-trip bit-exactly against the COG's, because the `red` group's chunks were written from the very same COG we read in exercise 1. Same data, different container.

# %% [markdown]
# **Question**: At level 0, this store's chunks line up 1:1 with the COG's tiles--chunk (7, 0) here is tile (7, 0) there. Does that correspondence hold on the overview levels?

# %% [markdown]
# <!-- scrub-omit -->
# **Answer**: No. The COG's overview IFDs use 512 × 512 tiles, while this store uses uniform 1024 × 1024 chunks on every level, so the overview levels were rechunked when the store was built and the boundaries no longer line up. Chunking is a property of the container, not the data--the same pixels can be (and here, are) carved up differently on either side.

# %% [markdown]
# ## The bands that aren't there
#
# Way back at the beginning, we said this store models *every* band of the scene, and hinted at a wrinkle. Time to pull on that thread.
#
# Let's look at `green`. Fetch its base array's metadata and compare it to `red`'s--shape, chunks, codecs, the works.

# %%
#| scrub-note: cell14
green_0_meta = store_read_json('green/0/zarr.json')
for field in ('shape', 'data_type', 'fill_value', 'codecs'):
    print(f'{field}: match={green_0_meta[field] == red_0_meta[field]}')

# %% [markdown]
# Identical in every way that matters: same grid, same dtype, same fill value, same codec chain. By the metadata, `green` is exactly as real as `red`. So let's read the same chunk we just read for red:

# %%
#| scrub-note: cell15
try:
    store_read('green/0/c/7/0')
except urllib.error.HTTPError as e:
    print(f'{e.code} {e.reason}')

# %% [markdown]
# There is no chunk. Not just this one--`green` has *zero* chunk objects. Only `red` was materialized when this store was built; the other sixteen bands are metadata-only, their structure synthesized from the STAC item without ever opening their COGs.
#
# Is a missing chunk an error? Not to zarr! Sparse arrays are a *feature*: a chunk that was never written simply reads as `fill_value`, so you don't have to spend storage on regions with no data. Watch what a real zarr reader does with this band (yes, we're allowed to use the actual library now--we've earned it):

# %%
import zarr

green_easy = zarr.open_array(f'{STORE_URL}/green/0', mode='r')
green_easy[7168:7172, 208:212]

# %% [markdown]
# No exception, no warning: the underlying 404 is silently translated into a window of `-0.1`, the fill value. Perfectly valid nodata, indistinguishable from a region of the scene that was actually observed and actually empty.
#
# And *that* is the chunk-level discovery gap, the deeper version of the problem we met at the root group. The metadata told us what the array would look like *if it had data*; it cannot tell us which chunks exist. There's no manifest. `green` looks exactly like `red` in every `zarr.json`, and the only way to learn the truth is to request chunks and see what comes back.
#
# So zarr leaves us with the same gap at two levels:
#
# * **Catalog level**: nothing tells you what stores exist or what's in them--you start from a URL someone handed you
# * **Chunk level**: nothing tells you which chunks exist--absence is silently read as fill
#
# What's missing, in both cases, is an *inventory*: something that says "here is exactly what data exists, and where the bytes live." The COG had one (the tile offset tables--clunky, but an inventory). Zarr, by design, does not. In exercise 3 we'll build exactly that missing inventory by hand--a kerchunk manifest--and see how the modern tools (VirtualiZarr, Icechunk) turn "a manifest of where the bytes live" into the foundation of the whole virtual-dataset ecosystem.

# %% [markdown]
# ## Opening it the easy way
#
# To wrap up, let's do the payoff we did in exercise 1: after all that hard work, how does this look with the proper tooling?

# %%
red_easy = zarr.open_array(f'{STORE_URL}/red/0', mode='r')
red_easy

# %%
red_easy[cell.row, cell.col]

# %% [markdown]
# One line to open, one line to read: zarr fetched the `zarr.json`, ran the codec pipeline, and handed us reflectance--everything this notebook did by hand. Note we opened the array by its full path; direct addressing works beautifully.
#
# But watch what happens if we ask the library to *explore* rather than *address*:

# %%
root_group = zarr.open_group(STORE_URL, mode='r')
sorted(root_group.keys())

# %% [markdown]
# An empty listing--for a store we know holds seventeen bands! Over plain HTTP there's no way to list keys, the root `zarr.json` declares no children, and so even the official library cannot enumerate the store; it can only fetch what we name. The same applies to xarray, which needs to discover the arrays in a group to assemble a dataset:

# %%
import xarray

xarray.open_zarr(f'{STORE_URL}/red', consolidated=False)

# %% [markdown]
# It happily fetched the group attributes... and found zero data variables, for arrays we've been reading all notebook. (On a listable store--local disk, S3, or one with consolidated metadata--xarray would find the level arrays just fine. The gap isn't xarray's fault; the store simply has no inventory to offer.)
#
# The hard way and the easy way hit the same wall, which is the note to end on: zarr's layout and access story is excellent--declared codecs, computed addressing, in-band geospatial conventions--and its discovery story is "bring your own manifest". On to exercise 3, where we do exactly that.

# %% [markdown]
# ## Additional exercises to consider later
#
# * Read the edge chunk `red/0/c/10/10` with `read_chunk` and confirm the out-of-bounds region beyond row/column 740 is all fill value (-0.1).
# * Generalize `read_chunk` to handle `scl`'s codec chain (no `fixedscaleoffset`), read its base array, and look up the class code at our POI in the [SCL class table](https://sentinels.copernicus.eu/web/sentinel/technical-guides/sentinel-2-msi/level-2a/algorithm-overview).
# * How many requests would it take to read all of `red` at full resolution from this store? How would you do the equivalent read from the COG, and how many requests could that take in theory?
# * Use each level's `spatial:transform` to locate the POI's pixel on every level of the pyramid, and confirm the reflectance values are consistent across levels.
# * Can you determine which of the 17 bands actually have data without downloading any chunk data? (Hint: HTTP HEAD requests--but note you're still guessing keys, which is the whole problem.)
# * Zarr v3 has a `sharding` codec that packs many chunks into one stored object with an internal index--rather COG-like, no? Read up on it and consider: what would sharding change about the request patterns and the discovery story we saw here?
#
# Any other cool ideas? Let me know and/or share with the group.
