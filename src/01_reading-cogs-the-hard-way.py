# %% [markdown]
# # Reading Cloud-Optimized GeoTIFFs the Hard Way
#
# In this notebook we will explore how one can read Cloud-Optimized GeoTIFFs (COGs) the hard way, i.e., by requesting and parsing byte ranges by hand. We'll query the Earth Search STAC catalog to find an image in COG format, parse the embedded metadata and file structure out of the file, then use that information to read the bytes of an image tile from the file and process them into a usable numpy array. We'll then visualize that array in a slippy map to verify what we did got us the expected result.
#
# Before we get into it, we have to get some initial stuff out of the way, like imports and some other defs we'll need for later.

# %%
from __future__ import annotations

import dataclasses
import enum
import json
import struct
import urllib.request

from collections.abc import Iterator
from pprint import pprint
from typing import Any, Literal, Self, TypedDict

import folium
import numpy as np

from griffine import Affine, Grid
from odc.geo.geom import point
from pystac_client import Client

# %%
# This is a mapping of the TIFF data types to the struct package's format charaters
# see https://docs.python.org/3/library/struct.html#format-characters

DATA_TYPES = {
    1: 'B',  # BYTE (uint8)
    2: 's',  # ASCII (char[1])
    3: 'H',  # SHORT (uint16)
    4: 'I',  # LONG (uint32)
    5: 'II',  # RATIONAL (uint32[2])
    6: 'b',  # SBYTE (int8)
    7: 'B',  # UNDEFINED (uint8)
    8: 'h',  # SSHORT (int16)
    9: 'i',  # SLONG (int32)
    10: 'ii',  # SRATIONAL (int32[2])
    11: 'f',  # FLOAT (float32)
    12: 'd',  # DOUBLE (float64)
    13: 'I',  # SUBIFD (uint32)
    # 14: '',
    # 15: '',
    16: 'Q',  # ? (uint64)
    17: 'q',  # ? (int64)
    18: 'Q',  # ? (uint64)
}

# %%
EPSG_4326 = 'EPSG:4326'

ENDIANNESS = {
    b'MM': '>',  # big endian
    b'II': '<',  # little endian
}


# %%
def binary(_bytes: bytes, join_str: str = ' ') -> None:
    _hex = _bytes.hex()
    return join_str.join(
        [f'{int(_hex[i : i + 2], 16):08b}' for i in range(0, len(_hex), 2)]
    )


def url_read_bytes(url: str, start: int, end: int) -> bytes:
    request = urllib.request.Request(
        url,
        headers={'Range': f'bytes={start}-{end - 1}'},
    )
    with urllib.request.urlopen(request) as response:
        return response.read()


# %% [markdown]
# ## Point of Interest (POI)
#
# To give us something to use for our query, let's define a point of interest.

# %%
# Point of Interest
POI = point(-121.695833, 45.373611, crs=EPSG_4326)

# Let's find out where the point is
point_map = POI.explore(name='point')
point_map

# %% [markdown]
# ## Querying Earth Search
#
# We'll use pystac-client to search the Earth Search Sentinel 2 L2A collection for a scene intersecting our POI. We'll aim for something with low cloud cover, in the year 2023, and we'll pick the most recent scene that matches these parameters.
#
# **NOTE**: You could change this notebook to fetch a different POI, scenes from a different collection, or even scenes from a different STAC API. You could even not use STAC and just put in an href directly to a COG of your choosing. That said, this POI and the resulting COG is used throughout this workshop, so it is best to stick with it on the first pass through. It's also important to understand that differences in the way a TIFF is created might mean the steps in this exercise will not apply or will need to be performed differently. If you do want to try reading a different COG I suggest doing so after successfully reading the curated scene.

# %%
client = Client.open('https://earth-search.aws.element84.com/v1')

search = client.search(
    max_items=1,
    collections=['sentinel-2-c1-l2a'],
    intersects=POI,
    datetime='2023/2023',
    query=['eo:cloud_cover<10'],
    sortby=[{'direction': 'desc', 'field': 'properties.datetime'}],
)
item = next(search.items())
print(json.dumps(item.to_dict(), indent=4))

# %% [markdown]
# We can throw that item onto our map to see its footprint relative to our POI.

# %%
stac_item_layer = folium.GeoJson(item, name='stac-item-footprint')
point_map.fit_bounds(stac_item_layer.get_bounds())
stac_item_layer.add_to(point_map)

point_map

# %% [markdown]
# The item we retrieved has many different bands, all of them COGs. We only need one for this exercise, so we'll grab the red band's href because that should be a good looking band visually.

# %%
href = item.assets['red'].href
print(href)

# %% [markdown]
# ## The TIFF file header
#
# The first few bytes of a TIFF file tell us a couple important things we'll need to process the rest of the file. First is the endianness of the file, second is that the file is really a TIFF file.
#
# Note that not all files with a `.tif` extension are a standard TIFF. Most notably, a standard TIFF file uses 32-bit integer offsets within the file to index particular bytes within the file (such as the offset to the first byte in an image tile, for example). Due to the maximum value of such an integer, standard TIFF files have a maximum file size of 4GB (or 2GB for certain archaic implementations that mistakenly used _signed_ integers for offset values). To get around this limitation, the BigTIFF format was developed using 64-bit integer offsets--but this is not a standard TIFF! It is close, but different enough we're not going to worry about supporting it for our little TIFF "library" that we're going to build.
#
# Actually, we're not going to support a lot of things. This implementation is going to be very specific to what we need for the specific Earth Search COG we selected. That's okay: sometimes a purpose-built implementation is more performant because it doesn't have to handle all the weird edge cases. Or at least that's what we can tell ourselves to feel better as we go along and notice how many conditions we're not handling in a more general way.
#
# ### So what's in the header already?
#
# Enough jibber-jabber, let's read out the header. It's the first 4 bytes of a standard TIFF.

# %%
#| scrub-note: cell0
header = url_read_bytes(href, 0, 4)
print(header)
print(header.hex())
print(binary(header))

# %% [markdown]
# ### Endianness and the TIFF Byte-Order Mark
#
# TIFF uses the first two bytes of the file to encode the endianness of the file as the "Byte-Order Mark". This presumably enables writers to use the most efficient endianess for their host system, if needed. Readers must support reading big or little endian files, where writers can pick one endianness.
#
# We can consider the endianness of a TIFF file to "describe the order of the bytes in a multi-byte data type". That is, when we have a 16-, 32-, or 64-bit value, the endianness tells how to interpret which bytes are most- and least-significant. In the case of a 32-bit integer value, that looks like this:
#
# ```
# 16^1
# |16^0
# || 16^3
# || |16^2
# || || 16^5
# || || |16^4
# || || || 16^7
# || || || ⎮16^6
# C0 00 00 00    = 192  little endian (II)
#
# 00 00 00 C0    = 192  big endian (MM)
# || || || ⎮16^0
# || || || 16^1
# || || |16^2
# || || 16^3
# || |16^4
# || 16^5
# |16^6
# 16^7
# ```
#
# Big endian is encoded as the byte-order mark `MM` (from Motorola processors), and little endian is encoded as `II` (from Intel processors).*
#
# The doubled letter is used to ensure that the binary sequence is the same no matter the endianness. Again, this is because the endianness affects only the order of the bytes in that two-byte word, not the order of the bits within each of the bytes.
#
# ----
#
# *Naively, the above example might make it seem silly to use little endian notation--big endian seems much more natural, given the way we generally have been taught to read and write numbers. However, when it comes to how most microprocessors and memory operations actually work, little endian has some clear benefits which has generally led to its dominance outside networking. More of the nuance and complication of endianness is well documented on [its wikipedia page](https://en.wikipedia.org/wiki/Endianness).

# %%
endianness = ENDIANNESS[
    header[0:2]
]  # We'll need this later, so let's save it into a var now
print(
    f"Endianness signature: {header[0:2]}; struct endianness format char: '{endianness}'"
)

# %% [markdown]
# To reiterate this point: we care about endianness to ensure we interpret the bytes in each word in the appropriate order. Beyond that simple concern, we don't need to worry about endianness in this exercise.

# %% [markdown]
# ### Magic number
#
# Many files encode a special number in their first few bytes, which can be used to distinguish the files is of a given format. Wikipedia has [a big long list of these "magic numbers"](https://en.wikipedia.org/wiki/List_of_file_signatures) for anyone curious. TIFF uses the value `42` for it's magic number (and BigTIFF is `43`).

# %%
#| scrub-note: cell1
magic_number = struct.unpack(f'{endianness}H', header[2:4])[0]
magic_number

# %% [markdown]
# ## The Python `struct` module
#
# Note the use of the `struct` module above. This is a module from the Python stdlib that is super handy when working with binary data, as it is able to pack (Python type to binary representation) and unpack (binary representation to Python type) data values given a specific format. Packing and unpacking allow specifying the endianness of the binary data using the `>` and `<` characters, which designate big and little endianness, respectively.
#
# The `H` in the magic number unpacking indicates that the data type is `uint16`. Some of data types with which we'll be working and their struct format characters include:
#
# | Data type | Format character |
# | --------- | ---------------- |
# | `uint8`   | `B`              |
# | `char[1]` | `s`              |
# | `uint16`  | `H`              |
# | `uint32`  | `I`              |
#
# Additional format characters are listed in the `DATA_TYPES` dict defined near the beginning of this notebook; also consider reviewing [the `struct` docs](https://docs.python.org/3/library/struct.html) for the full list of format codes available and other details on how to use `struct`.

# %% [markdown]
# ## First IFD offset: the next four bytes
#
# Immediately following the TIFF header is the offset to the first image file directory (IFD) in the file. In a standard TIFF this offset is a 32-bit unsigned integer (`uint32`). We can read in and view those bytes:

# %%
#| scrub-note: cell2
ifd_offset_bytes = url_read_bytes(href, 4, 8)
print(ifd_offset_bytes)
print(binary(ifd_offset_bytes))

# %% [markdown]
# Though that's not super useful until we unpack those bytes into in integer (here using `I` because the offset is a `uint32` value):

# %%
#| scrub-note: cell3
ifd_offset = struct.unpack(f'{endianness}I', ifd_offset_bytes)[0]
print(ifd_offset)

# %% [markdown]
# ## Parsing the Image File Directory
#
# The Image File Directory (IFD) is a data structure composed of entries called tags (hence the name "Tag Image File Format"). The IFD doesn't start with the first tag entry, however. It begins with a 2-byte `uint16` value indicating the number of tags within the IFD. This value enables us, along with the IFD offset within the file, to read the entire sequence of tag bytes via `file_bytes[ifd_offset + 2:ifd_offset + (tags_count * tag_size)]`.
#
# ### Tag structure
#
# In a standard TIFF, tags are a 12-byte sequence (so `tag_size` above is 12 bytes) with the following structure:
#
# | Tag Bytes | Tag field name  | Field data type |
# | --------- | --------------- | --------------- |
# | 0 - 1     | `code`          | `uint16`        |
# | 2 - 3     | `data_type`     | `uint16`        |
# | 4 - 7     | `count`         | `uint32`        |
# | 8 - 11    | `value`         | `char[4]`       |
#
# In the case of BigTIFF files, each tag is a 20-byte sequence where the `count` and `value` are both doubled, using the types `uint64` and `char[8]`, respectively.
#
# The tag `code` field gives us a way to find the meaning of the tag `value`, as the `code` is an integer that maps to a tag's identity. The Library of Congress has [a handy table](https://www.loc.gov/preservation/digital/formats/content/tiff_tags.shtml) we can use to look up the tags by their codes.
#
# #### Tag data types
#
# The tag `data_type` is also an integer value, in this case mapping to the data type we can use to interpret `value` per the following table:
#
# | `data_type` | Type Name | Data type   |
# | ----------- | --------- | ----------- |
# | 1           | BYTE      | `uint8`     |
# | 2           | ASCII     | `char[1]`   |
# | 3           | SHORT     | `uint16`    |
# | 4           | LONG      | `uint32`    |
# | 5           | RATIONAL  | `uint32[2]` |
# | 6           | SBYTE     | `int8`      |
# | 7           | UNDEFINED | `uint8`     |
# | 8           | SSHORT    | `int16`     |
# | 9           | SLONG     | `int32`     |
# | 10          | SRATIONAL | `int32[2]`  |
# | 11          | FLOAT     | `float32`   |
# | 12          | DOUBLE    | `float64`   |
# | 13          | SUBIFD    | `uint32`    |
# | 14          | n/a       | n/a         |
# | 15          | n/a       | n/a         |
# | 16*         | ?         | `uint64`    |
# | 17*         | ?         | `int64`     |
# | 18*         | ?         | `uint64`    |
#
# *Data types 16, 17, and 18 are specifc to BigTIFF.
#
# The `count` field tells us how many of the listed `data_type` make up the value of the tag. Note that even a `count` of 1 for a `data_type` of `12` (a double precision float with a length of 8 bytes) would not fit in a tag's `value` field in a standard TIFF file, as `value` itself is only 4 bytes long. Similarly, a `count` greater than 4 with a `data_type` of 1 (`uint8`) would also be larger than can fit in `value`.
#
# In such cases where `count * len_in_bytes(data_type) > 4`, `value` itself is not actually the tag's value. Instead, `value` is an offset to some location in the file where the actual value's bytes begin. The length of that value is given by that previous expression, `count * len_in_bytes(data_type)`. Thus, to get the actual value when a value is oversized (again, `count * len_in_bytes(data_type) > 4`), we can read `file_bytes[value:value + (count * len_in_bytes(data_type))]`.
#
# A IFD doesn't end at last tag. Each IFD contains a 4-byte (`uint32`) offset to the next IFD in the file (or 8-byte `uint64` in the case of BigTIFF). In the event an IFD is the last one in the file, it will have a value of 0 for this next IFD offset. As a result, a reader can build a map of the complete contents of a TIFF by iterating through its IFDs and parsing their tags into some appropriate hierarchical data structure (TIFF --< IFDs --< Image segments) .

# %% [markdown]
# ### Finding the tag count and reading the tag bytes
#
# As mentioned, an IFD starts with a 2-byte `uint16` value indicating the number of tags it contains. If we have an IFD's offset (`ifd_offset`) within the file---which for the first IFD we know is given to us as the first bytes in the file immediately following the TIFF header---then we also know that IFD's tag offset (`tags_start`), which we can calculate as `ifd_offset + 2`.
#
# Parsing the tag count (`tags_count`) is simply a matter of using `struct.unpack` to unpack the two tag count bytes into an integer (struct format char `H` for `uint16`). Again, we need to make sure we use the endianness indicated in the file header.

# %%
#| scrub-note: cell4
tags_start = ifd_offset + 2
tags_count = struct.unpack(
    f'{endianness}H', url_read_bytes(href, ifd_offset, tags_start)
)[0]
tags_count

# %% [markdown]
# If we know the tag count and the tag size (12 bytes for TIFF, 20 for BigTIFF), then we can find the total number of bytes in the IFD's tags by `tag_count * tag_size`. From this we should be able to find the last byte of the tags with `tags_end = tags_start + (tag_count * tag_size)`, allowing us to read the tag bytes (`tags_bytes`) from the file.

# %%
#| scrub-note: cell5
tag_size = 12  # because we only support standard TIFF
tags_end = tags_start + (tags_count * tag_size)
tags_bytes = url_read_bytes(href, tags_start, tags_end)
print(tags_bytes)
print(binary(tags_bytes))

# %% [markdown]
# We can also use the `tags_end` to know the offset to the next IFD offset value, which is a 4-byte value we can unpack into a `uint32`. We won't use this offset for anything in this notebook, but it is good to know in case you want to take parsing further and go on to the other IFDs in this file.

# %%
#| scrub-note: cell6
next_ifd_offset = struct.unpack(
    f'{endianness}I', url_read_bytes(href, tags_end, tags_end + 4)
)[0]
next_ifd_offset

# %% [markdown]
# ### Parsing each tag
#
# To parse each tag we need to split each tag's bytes out of the larger bytes string. Python gives us many valid ways of doing this. Let's try using a `for` loop and see what each tag looks like.

# %%
#| scrub-note: cell7
for i in range(0, len(tags_bytes), tag_size):
    tb = tags_bytes[i : i + tag_size]
    print(tb)
    print(binary(tb))

# %% [markdown]
# #### Unpacking the tag values
#
# The above show us we can easily isolate each tag's bytes, but we still need to use `struct.unpack` to convert the tag's `code`, `data_type`, `count`, and `value` binary values into Python types. Remember that `code` and `data_type` are `uint16` values, which map to the struct `H` format. Look up the proper struct format values for `count` and `value` using what you know about the data types of those tag fields, and verify if the format passed into `struct.unpack` in the example here is correct (consult the `DATA_TYPES` dict above or the struct docs directly).
#
# This example uses a `while` loop to extract the tag bytes instead of a `for` loop like above, just to show both approaches work effectively. Each tag's fields are added into a dictionary indexed by the tag `code` to facilitate easy access later.

# %%
tags = {}
tag_index = 0

while tag_index < tags_count:
    try:
        tag_bytes = tags_bytes[(tag_size * tag_index) : (tag_size * (tag_index + 1))]
        tag_index += 1
    except IndexError:
        break

    code, data_type, count, value = struct.unpack(f'{endianness}HHI4s', tag_bytes)
    tags[code] = {
        'data_type': data_type,
        'count': count,
        'value': value,
    }

tags

# %% [markdown]
# #### Understanding tag codes
#
# Now that we have TIFF tag values to look at, it would be good to mention the [Libray of Congress' guide to TIFF Tags](https://www.loc.gov/preservation/digital/formats/content/tiff_tags.shtml) again. We can use that lookup table to interpret each of the integer codes in a meaningful way. Note that some codes we will see in every file, while others may be specific to the way a file was encoded or the type of data it contains. Further, a number of the tags we have here are specific to the GeoTIFF format, while some are GDAL-specific metadata conventions.
#
# For example, we should always expect to see tags 256, 257, 258, and 259 (among others):
#
# | Code | Tag Name      | Tag Description              |
# | ---- | ------------- | ---------------------------- |
# | 256  | ImageWidth    | Number of image columns      |
# | 257  | ImageLength   | Number of image rows         |
# | 258  | BitsPerSample | Number of bits in each pixel |
# | 259  | Compression   | Integer mapping to compression algorithm used for each image segment |

# %% [markdown]
# #### Unpacking the tag values
#
# Recalling the earlier explanation about tag data types, counts, and values, we know that the process for unpacking values will not be the same for each tag, given the differences in those three fields across each of the tags. That is, for tags that have a small count of a shorter data type (total length less than 4 bytes), we can unpack the tag `value` directly. But for longer values we'll have to interpret the tag `value` as an offset in the file containing the actual value bytes.
#
# To see how this works, we'll start with two of the easier tags and unpack the image size tags 256 and 257. Check the data types for these tags. What are the struct format chars for each? Will we need to unpack all four bytes of the `value` for either of these tags? Unpack these tags and see what the values are.

# %%
#| scrub-note: cell8
# image column count (width)
cols = struct.unpack(endianness + 'H', tags[256]['value'][0 : struct.calcsize('H')])[0]

# image row count (height)
# we can also resolve the struct char in a more automated fashion
tag = tags[257]
struct_dtype = DATA_TYPES[tag['data_type']]
rows = struct.unpack(
    endianness + struct_dtype, tags[257]['value'][0 : struct.calcsize(struct_dtype)]
)[0]

print(f'Image size is {cols} x {rows}')

# %% [markdown]
# In the "big value" case, where the tag `value`'s four bytes are not sufficient to contain the whole tag value, parsing becomes a bit more complex. We not only need to find the struct format character (`struct_dtype`) and size for the tag's data type, but then we need to:
#
# * use the data type's size and the tag `count` to calculate how many bytes we need to read (the tag value's `size`)
# * unpack the `value` field to get the offset to the actual value bytes (`offset`)
# * combine `size` and `offset` to get the byte range and read that out of the file (giving us `values`)
# * build the struct format string (`endianness + (struct_dtype * count)`) then unpack `values`
#
# We'll preview this approach with an example unpacking the tile offsets tag (324). The values we unpack (`tile_offsets`) are the byte offsets for each image segment (tile) in the image represented by this IFD. We will be able to use these offsets in the next section to read the specific tile containing our POI (though we'll have unpack the rest of our tags and do a bit of math to figure out which one and what to do with the bytes).

# %%
tag = tags[324]
struct_dtype = DATA_TYPES[tag['data_type']]
size = tag['count'] * struct.calcsize(struct_dtype)
offset = struct.unpack(f'{endianness}I', tag['value'])[0]
values = url_read_bytes(href, offset, offset + size)
tile_offsets = struct.unpack(endianness + (struct_dtype * tag['count']), values)

for idx, tile_offset in enumerate(tile_offsets):
    print(f'Offset tile {idx}: {tile_offset}')


# %% [markdown]
# ### Questions
#
# * Refer back to the STAC item and see if the `file` STAC extension is in use. Is the file size listed for the COG asset your are examining, and if so how close to the end of the file do these tiles appear to get?
# * Can you use the unpacking examples to create a generalized approach to unpacking the tag values and apply that to the rest of the tags in the IFD? The next section will have you unpack all the tags, so finding a quicker and more efficient way to do this might be helpful.

# %% [markdown]
# <!-- scrub-omit -->
# ### Answers
#
# * The COG is 218,693,282 bytes. The last tile starts at offset 217,929,856. The difference between those two is 763,426 bytes. Looking at the offset of the second-to-last tile, 216,879,023, we can see that tile to be 217,929,856 - 216,879,023 = 1,050,833 bytes in size. So 763,426 bytes is will within the expected size of a tile, and because of that we can reasonably conclude that this tile is the last data in the file.
#
#   We can check if this interpretation is correct by unpacking tag 325, which gives us the tile byte sizes. From that list of values we see that the last tile is 763,422 bytes, leaving four bytes at the end of the file unaccounted for. While the exact role of those bytes is not terribly relevant to our concerns here ([the GDAL COG driver docs has more info about those bytes](https://gdal.org/en/stable/drivers/raster/cog.html#tile-data-leader-and-trailer)), what we can say is there's no significant chunk of data remaining at the end of the file after this last tile of the first IFD.
#
#   Note this finding more or less aligns with our understanding of the structure of a COG: the IFDs are in the beginning of the file, and the actual image data follows with the full resolution data at the end (each overview progressively lower resolution stacked on top from highest resolution at the end to lowest at the top).
# * Yes, in fact we can draw from the above tag unpacking examples to implement a generalized function that handles unpacking all types of tag values, and such a function is provided in the next section.

# %% [markdown]
# ## Reading a tile from the image
#
# Reading the tile intersecting our POI will require almost all of our tags to be unpacked and decoded. Refer back to the tags dictionary `tags` keys for the list of all tag codes in our TIFF's first IFD and the above documentation on the tag codes. Unpack each tag's value into the corresponding variable name in the list below:
#
# * `image_width`
# * `image_length`
# * `bits_per_sample`
# * `compression`
# * `samples_per_pixel`
# * `predictor`
# * `tile_width`
# * `tile_length`
# * `tile_offsets`
# * `tile_byte_counts`
# * `sample_format`
# * `pixel_scale`
# * `tie_point`
# * `geo_key_directory`
# * `geo_double_params` (if defined, else `tuple()`)
# * `geo_ascii_params` (if defined, else `b''`)
# * `gdal_metadata`
# * `nodata_value`
#
# **NOTE**: if you have chosen a different COG source than the Sentinel 2 COG from Earth Search, you might need to consider additional tags and processing to get the rest of the notebook to work (if you've even made it this far). TIFF is an extremely flexible format, but this means it has many different cases that need to be handled to be able to read any arbitrary file (which also means some atypical features supported by one implementation might lead to incompatibilities with other implementations).

# %% [markdown]
# ### Let's define a function to make unpacking the tags easier
#
# We have a lot of tags to unpack. For the sake of time, here's a function that we can use to make unpacking all the tags easier.


# %%
class TagDict(TypedDict):
    data_type: int
    count: int
    value: bytes


type TagsDict = dict[int:TagDict]


def unpack_tag(tag: TagsDict, endianness: Literal['>', '<']) -> Any:
    struct_dtype = DATA_TYPES[tag['data_type']]
    size = tag['count'] * struct.calcsize(struct_dtype)
    value = tag['value']

    offset = None
    if size > len(value):
        offset = struct.unpack(endianness + 'I', value)[0]
        value = url_read_bytes(href, offset, offset + size)

    unpacked = struct.unpack(endianness + (struct_dtype * tag['count']), value[:size])

    # if data_type == 2 (ASCII) we want to join the chars together
    if tag['data_type'] == 2:
        return b''.join(unpacked)
    elif tag['count'] == 1:
        return unpacked[0]
    return unpacked


# %% [markdown]
# Let's try that out on the tags we unpacked above and see how this works!

# %%
#| scrub-note: cell9
unpack_tag(tags[257], endianness)

# %%
#| scrub-note: cell10
unpack_tag(tags[324], endianness)

# %% [markdown]
# Now let's use that function to unpack all our tags into the corresponding variable.

# %%
image_width = unpack_tag(tags[256], endianness)
image_length = unpack_tag(tags[257], endianness)
bits_per_sample = unpack_tag(tags[258], endianness)
compression = unpack_tag(tags[259], endianness)
samples_per_pixel = unpack_tag(tags[277], endianness)
predictor = unpack_tag(tags[317], endianness)
tile_width = unpack_tag(tags[322], endianness)
tile_length = unpack_tag(tags[323], endianness)
tile_offsets = unpack_tag(tags[324], endianness)
tile_byte_counts = unpack_tag(tags[325], endianness)
sample_format = unpack_tag(tags[339], endianness)
pixel_scale = unpack_tag(tags[33550], endianness)
tie_point = unpack_tag(tags[33922], endianness)
geo_key_directory = unpack_tag(tags[34735], endianness)
geo_double_params = ()  # we don't have any double params in this image
geo_ascii_params = unpack_tag(tags[34737], endianness)
gdal_metadata = unpack_tag(tags[42112], endianness)
original_nodata_value = unpack_tag(tags[42113], endianness)

# %% [markdown]
# ### Interpreting tag values
#
# Many of the tags are straightforward. Some are enumerations which require an external lookup table. Others require cross-references between their values to make sense of the contents. Let's take a look at the few that are not straightforward to understand them better.
#
# #### Compression
#
# The `compression` tag value represents one of an enumerated set of possible compression methods. Continuing with the spirit of needing to consult various external lookup tables, the [Wikipedia entry for TIFF has a great table of possible compression formats and their integer values](https://en.wikipedia.org/wiki/TIFF#TIFF_Compression_Tag) is a great resource for understanding the meaning of the different possible values.
#
# **Question**: What is the value of the `compression` tag and what compression scheme does it indicate?

# %%
#| scrub-note: cell11
compression

# %% [markdown]
# <!-- scrub-omit -->
# **Answer**: In this case we have a value of `8`, which maps to `DEFLATE`. Thus, any tile we read will need to be appropriately decompressed (ehm, inflated? Actually, yes!). We can use the Python stdlib `zlib` to inflate `DEFLATE`-compressed data.

# %% [markdown]
# #### Sample format
#
# The `sample_format` tag value represents one of an enumerated set of possible data types. Those values map as follows:
#
# | Format Value | Data Type |
# | ------------ | --------- |
# | 1 | `uint`   |
# | 2 | `int`    |
# | 3 | `float`  |
# | 4 | untyped  |
# | 5 | `cint`   |
# | 6 | `cfloat` |
#
# The bit depth of the specified format is dependent on the value of the `bits_per_sample` tag.

# %%
#| scrub-note: cell12
sample_format, bits_per_sample

# %% [markdown]
# **Question**: What does the value of the `sample_format` tag indicate with regards to the data type and length of the cell values in this image (e.g., `uint32`, `int8`, `float32`, etc.)? What does this data type map to in the struct format characters?

# %% [markdown]
# <!-- scrub-omit -->
# **Answer**: Our data type is `uint16`, which is char `H`.

# %% [markdown]
# #### Pixel scale and tie point
#
# The `pixel_scale` tag is part of the GeoTIFF specification. It is a three-tuple where each value represents one dimension of the pixel scale, specifically the x, y, and z scales, respectively. In other words, each of the scale values represent the change in coordinate from one pixel origin to the next along the specified dimension. The units of each scale value are the same as those specified in coordinate reference system (CRS; we'll see this when reviewing the `geo_key_directory` below).
#
# The `tie_point` tag is again a member of the GeoTIFF specification. It defines a set of coordinates in the image space and their mappings to coordinates in the model space as a list of six-tuples. The first three tuple values are the image space x, y, and z coordinates, respectively. The latter three tuple values are the model space x, y, and z, respectively. The model space is perhaps best understood to be the coordinate reference system defined for the image.
#
# What is most notable for us about these two tags is that we can use them to build a simple affine transform to convert between image space and model space. Most GeoTIFF files, like ours, use such an affine transform, which means the following is frequently true:
#
# * the set of coordinate mappings has length one, i.e., only one point is mapped from image space to coordinate space
# * the image space coordinates of that point are (0, 0, 0), which effectively allows us to consider the model space coordinates to be the geographic point represented by the image origin
#
# The [GeoTIFF spec docs detailing how to use these values are here](http://geotiff.maptools.org/spec/geotiff2.6.html). Note that the `pixel_scale` tag is optional; in some cases a `ModelTransformationTag` is used instead to encode the affine transformation matrix into the file, such as when needing to express grid rotation. Sometimes neither of these tags are present, such as when the transformation is not affine, which is typically when the `tie_point` tag would have multiple points describing a warp mesh over the image. Consult the docs to fully understand the interactions of these three tags and how to interpret their values outside this simple affine case.
#
# Why does all of this matter for us? We can use the `pixel_scale` and `tie_point` tag values to construct an affine transform object, which we'll use to perform coordinate transformations between model space (the image CRS) and image space (pixel coordinates). We need to be able to do this to find what pixel in the image contains our POI, so we can find which image tile to read.

# %%
transform = Affine(
    # w-e pixel resolution / pixel width
    pixel_scale[0],
    # row rotation (typically zero)
    0,
    # x-coordinate of the upper-left corner of the upper-left pixel (origin)
    tie_point[3] - (pixel_scale[0] * tie_point[0]),
    # column rotation (typically zero)
    0,
    # n-s pixel resolution / pixel height (negative value for a north-up image)
    -pixel_scale[1],
    # y-coordinate of the upper-left corner of the upper-left pixel (origin)
    tie_point[4] - (-pixel_scale[1] * tie_point[1]),
)


# %% [markdown]
# #### Geo key directory and the params
#
# Another set of GeoTIFF-spec tags, `geo_key_directory`, `geo_double_params`, and `geo_ascii_params` represent a collection of geospatial information we need to interpret the data in a spatially-aware way. For example, such important information as the CRS is stored amongst these tags. The [GeoTIFF spec docs also document these tags and their interactions](http://geotiff.maptools.org/spec/geotiff2.4.html).
#
# In short, `geo_double_params` and `geo_ascii_params` are sets of parameters that can be used to fill in information that cannot be represented directly in the `geo_key_directory` due to data type differences (the latter is a `uint16` tuple whereas the former two are tuples of double precision floats and ASCII-encoded strings, respectively). The `geo_key_directory` is a collection of four-tuples (potentially with some additional trailing values), the first of which is a header that documents the tuples that follow. It has the following 8-byte structure:
#
# ```
# Header = (KeyDirectoryVersion, KeyRevision, MinorRevision, NumberOfKeys)
# ```
#
# For our purposes, the important piece here is the number of keys: we need to know how many keys are in the remainder of the directory. As we'll see, with this count we can work out the offset to each directory entry, and also the start of any additional values stored in the directory structure (we might need these values to fill out directory entries containing multiple `uint16` values).
#
# After the header, each of the keys in the directory have the 8-byte structure:
#
# ```
# KeyEntry = (KeyID, TIFFTagLocation, Count, Value_Offset)
# ```
#
# The `KeyID` here is just like our TIFF tags: it is an identifier that can be used with an external lookup table to interpret the meaning of the key's value. The `TIFFTagLocation` points to the TIFF tag containing the value for this key: if the value is directly embedded in the key (in the place of `Value_Offset`) then the location is `0` and this key's value is of type `uint16`.
#
# In the case of a non-0 `TIFFTagLocation` value, we know the value is not directly embedded in the key's `Value_Offset`, and that `Value_Offset` is in fact an offset. Unlike other offsets we've grown accustomed to working with in out TIFF traversal, this offset is not a byte offset relative to the file, but instead is "an index based on the natural data type of the specified tag array" pointed to by `TIFFTagLocation`. Combined with `Count`, we have what we need to isolate the set of values pertaining to this key from the target tag's data. The data type of the key value is given by that target tag's data type.
#
# For example, if we have a key entry with the values `(1024, 0, 1, 1)`, then we know: the key ID is `1024`, the location of `0` means the value is embedded in the key entry, our count is `1`, and thus that we can interpret the `Value_Offset` as the key value, in this case `1`.
#
# A more complex example could be like `(2049, 34737, 7, 22)`: in this case we have a non-zero location, so we have to read the values---in this case seven values per the count value---from a separate tag. The location of `34737` corresponds to the `geo_ascii_params` tag, which not only tells us where to get the values for this key, but also their data type. If the value of the `34737` tag is `b'WGS 84 / UTM zone 10N|WGS 84|\x00'`, then taking 7 bytes from position 22 we end up with `b'WGS 84|'`. The `|` is intended to be converted into a null byte to terminate the extracted string; Python makes it easy enough to simply read one less byte than the key's count for ASCII-type values, as string termination is handled for us and we don't need an explicit string terminator.
#
# The above explanation and examples give us what we need to write a general-purpose function to extract the keys into a dict, like we did with the IFD tags. Let's see what that looks like then use it to extract our keys. Refer to the [GeoTIFF document "Geocoding Raster Data"](http://geotiff.maptools.org/spec/geotiff2.7.html#2.7) for and explanation of the key IDs and how to understand their meanings. These keys are critical for finding the CRS of the file via the information presented in that documentation.


# %%
def extract_geo_keys(
    key_directory: tuple[int, ...],
    double_params: tuple[float, ...],
    ascii_params: bytes,
) -> dict[int, int | float | bytes]:
    keys: dict[int, int | float | bytes] = {}

    try:
        _, _, _, key_count = key_directory[0:4]
        for key_index in range(key_count):
            offset = (4 * key_index) + 4
            key_id, location, count, value_offset = key_directory[offset : offset + 4]

            if location == 0:
                keys[key_id] = value_offset
            elif location == 34735:
                keys[key_id] = key_directory[value_offset : value_offset + count]
            elif location == 34736:
                keys[key_id] = double_params[value_offset : value_offset + count]
            elif location == 34737:
                keys[key_id] = ascii_params[value_offset : value_offset + (count - 1)]
            else:
                raise ValueError(f'Unknown location: {location}')
    except Exception as e:
        # Chain the original exception (`from e`) so we keep the underlying
        # traceback instead of hiding it behind a generic message--important
        # for debugging when a different COG throws something unexpected here.
        raise ValueError('Could not parse geo keys') from e

    return keys


# %%
geo_keys = extract_geo_keys(geo_key_directory, geo_double_params, geo_ascii_params)
geo_keys

# %% [markdown]
# **Question**: From the extracted geo key values, can you find the CRS and it's EPSG code?

# %% [markdown]
# <!-- scrub-omit -->
# **Answer**: Key `3072` here is `ProjectedCSTypeGeoKey`, which, as this is a projected coordinate system (as defined by key `1`), maps to the EPSG code for the CRS of these data, `32610`. That EPSG code is for the CRS for UTM zone 10N, which it turns out is not a particularly surprising given the value we can see for key `1026` (`GTCitationGeoKey`).

# %% [markdown]
# #### Nodata
#
# The GDAL nodata value is stored in GeoTIFFs as a null-terminated ASCII string. On the surface this seems strange, but doing so is necessary to ensure it can be parsed with the correct data type. That is, the nodata value needs to be interpreted via the data type of the actual array data, which we saw above comes from the combination of `sample_format` and `bits_per_sample`. What those define together might not map directly to the TIFF-defined tag data types, hence the string format.
#
# Because of this string business, the `nodata` value needs some additional processing before we can use it. Specifically, we need to clip the final character off (the null terminator), then we need to cast it the appropriate data type (again, as given by `sample_format` and `bits_per_sample`). For example, if we have an integer data type for our image data then we need to do something like `nodata_value = int(original_nodata_value[:-1])`.

# %%
# We need to clip the string terminator off the nodata value
# before coercing to an int (because it is stored as ASCII)
nodata_value = int(original_nodata_value[:-1])
nodata_value

# %% [markdown]
# ## Reading an image tile
#
# Now that we have parsed all the necessary metadata, we can focus on using that metadata to read a tile. If we recall way back at the beginning we defined a POI, so we presumably should find the tile containing said POI, instead of reading some other arbitrary tile. To find this tile, we'll need to do some [highly automated] math.
#
# ### Transforming our POI
#
# First, we need to find the point coordinates of our POI in the same reference system as the image. We can use the `to_crs` method on our POI with our image's CRS as parsed from the geo keys above.

# %%
image_crs = f'EPSG:{geo_keys[3072]}'
POI_proj = POI.to_crs(image_crs)
print(f'x={POI_proj.geom.x}, y={POI_proj.geom.y}')

# %% [markdown]
# Check the above output. Does it make sense given what we know about the origin of our image, and the relation of our POI to the image footprint?

# %% [markdown]
# ### Finding the pixel coordinates of our POI
#
# Now that we have our POI geographic coordinates in the same CRS as our image, we can use the image's affine transform to convert our POI's geographic coordinates into pixel coordinates in our image's pixel grid. The author of this notebook has created a small library to make tasks involving raster grids with affine transforms easier, called `griffine`. We can make an instance of a `griffine.Grid` and attach our transform to it, which will help us in a number of operations to come. Then we can use the grid to find the cell containing our point.

# %%
grid = Grid(rows=image_length, cols=image_width).add_transform(transform)
cell = grid.point_to_cell(POI_proj)
print(f'row={cell.row}, col={cell.col}')

# %% [markdown]
# Again, check the above output. Does it make sense given what we know about the origin of our image, its grid, and the relation of our POI to the image footprint?

# %% [markdown]
# ### Finding our tile coordinates
#
# Knowing the pixel is great, but to know which tile we need to read we need tile coordinates, not pixel coordinates. To find these, we can "tile" our `grid` object and find the `tile` containing our POI and its coordinates.

# %%
tile_grid = grid.tile_via(Grid(rows=tile_length, cols=tile_width))
tile = tile_grid.point_to_tile(POI_proj)
print(f'tile_row={tile.row}, tile_col={tile.col}')

# %% [markdown]
# One last time: check the above output. Does it make sense given what we know about the structure our image, and the relation of our POI to the image footprint?

# %% [markdown]
# ### Finding our tile offset and byte length
#
# The tag values of `tile_offsets` and `tile_byte_counts` give us the offset and byte lengths of each tile. To retrieve them for a given tile we need to know the tile's index within those tuples. We use our `tile` object with our `tile_grid` to find the tile's linear index within the grid.

# %%
tile_index = tile_grid.linear_index(tile)
tile_offset = tile_offsets[tile_index]
tile_byte_length = tile_byte_counts[tile_index]
print(
    f'tile ({tile.row}, {tile.col}) has index {tile_index} and is at offset {tile_offset} with length {tile_byte_length}'
)

# %% [markdown]
# ### Actually reading the tile
#
# Now that we know where the tile bytes are in the file we can read them, decompress them (per the algorithm specified by `compression`), then unpack them into a numpy array.

# %%
tile_bytes = url_read_bytes(href, tile_offset, tile_offset + tile_byte_length)

# %%
# Per our `compression` tag we know we the data is compressed using `DEFLATE`,
# which can be extracted using the stdlib `zlib` module.
import zlib

tile_extracted = zlib.decompress(tile_bytes, 0)

# %%
# Our data type is `uint16` as we previously found; using our
# lookup table we know that maps to a struct format char of `H`.
# That dtype is 2-bytes in length, so we know our tile data
# contains `len(tile_extracted) // 2` pixel values.
struct_dtype = 'H'
tile_array = np.array(
    struct.unpack(
        endianness
        + (struct_dtype * (len(tile_extracted) // struct.calcsize(struct_dtype))),
        tile_extracted,
    ),
    dtype=np.uint16,
).reshape(tile_width, tile_length)
tile_array

# %%
# Or, more easily but perhaps too abstractly
np.frombuffer(tile_extracted, dtype=np.uint16).reshape(tile_width, tile_length)

# %% [markdown]
# #### A note on `predictor`
#
# The `predictor` tag is used when a filtering step is done prior to compression to improve compressibility. Values of `2` and `3` are common: `2` is generally effective for integer data (this predictor calculates the horizontal difference between cells, which with spatial autocorrelation is typically an effective optimization), and `3` is always optimal for floating point data. In other words, if we have a predictor set and it isn't `1` (indicating no predictor) then we can't just extract the data and start using it. The data will require processing step to reverse the prediction operation and restore the data back to its original values.

# %%
print(predictor)

# %%
# as our data is using predictor `2` (horizontal difference),
# we'll need to reverse the difference using a cumulative sum
tile_array_unfiltered = np.cumsum(tile_array, axis=1, dtype=tile_array.dtype)
tile_array_unfiltered

# %% [markdown]
# #### Scale and offset
#
# We have yet one more operation we need to perform on our data array to make it usable. As it turns out, the stored data format `uint16` isn't actually the real data format. Rather, the data are limited-precision floats having been mapped to `uint16` via a specified scaling factor. Moreover, due to the atmospheric correction process applied to this L2A data, it's possible to have negative data values, which must be accounted for by shifting the raw values by a specified offset.
#
# Both the `scale` and `offset` values are contained within the `gdal_metadata` tag. The GDAL metadata format is XML, though for our purposes we can just print out tag value as a string. The values we need are human-readable enough that we can skip having to spend time handling XML-parsing complexities.

# %%
gdal_metadata

# %%
# fill in the value_offset and value_scale from the above
value_offset = -0.1
value_scale = 0.0001
tile_array_scaled_offset = (tile_array_unfiltered * value_scale) + value_offset
tile_array_scaled_offset

# %% [markdown]
# ## Visualizing the tile on our map
#
# Now that we have our tile data, it would be great to see it alongside our POI to visually confirm we got the tile we expected. It turns out Folium has a kinda hokey way of converting numpy arrays to PNGs for display on the map, which we can leverage here to visually verify the data we've read for our tile and the operations we've done on it. It's not perfect, as it assumes our data is aligned to the mercator grid (which it probably isn't), but it's close enough for us to take a look.
#
# We just need the tile's min and max latitude and longitude (in EPSG:4326 coordinates) so we can tell Folium it's bounding box (roughly), then we can (re-)make our map and add our layers. We can use our `tile` object to compute those coordinates in our image CRS then convert them to EPSG:4326.

# %%
tile_origin_x, tile_origin_y = (
    point(*tile.origin.coords[0], crs=image_crs).to_crs(EPSG_4326).coords[0]
)
tile_antiorigin_x, tile_antiorigin_y = (
    point(*tile.antiorigin.coords[0], crs=image_crs).to_crs(EPSG_4326).coords[0]
)

# we make a whole new map because if we screwed
# something up we only have to re-run this cell to fix it
raster_map = POI.explore(name='point')

stac_item_layer.add_to(raster_map)
raster_map.fit_bounds(stac_item_layer.get_bounds())

folium.raster_layers.ImageOverlay(
    tile_array_scaled_offset,
    bounds=[[tile_antiorigin_y, tile_origin_x], [tile_origin_y, tile_antiorigin_x]],
    name='tile',
).add_to(raster_map)

folium.LayerControl().add_to(raster_map)

raster_map


# %% [markdown]
# ## Additional exercises to consider later
#
# * Find how many overviews are in this file.
# * Find the dimensions and gsd of each overview.
# * Repeat reading the tile containing your point of interest, but do so from one of the overviews.
# * How can we make reading the file more efficient? Can we get all the IFDs in the file with a single read without having to read in image data?
# * Consider what it would take to write a TIFF. What do you have to track for that? What process would you follow?
# * Repeat these exercises with a multiband TIFF to see how the file structure differs to support the additional bands.
#
# Any other cool ideas? Let me know and/or share with the group.

# %% [markdown]
# ## Appendix: example TIFF metadata parser
#
# Could we take parsing another step further, to better facilitate the above exercises? Wouldn't it be great if we could parse the tags into a complete objects? What if we could start with just a reference to the TIFF itself, and have an entire data structure built up to parse all the IFDs out of the file in one go?
#
# Turns out this is a fun problem and I wanted to code up a solution. Here's my attempt; what might yours look like?


# %%
class Endianness(bytes, enum.Enum):
    BIG_ENDIAN = b'MM'
    LITTLE_ENDIAN = b'II'

    @property
    def unpack_char(self: Self) -> str:
        match self:
            case Endianness.BIG_ENDIAN:
                return '>'
            case Endianness.LITTLE_ENDIAN:
                return '<'


@dataclasses.dataclass
class TIFFBytes:
    data: bytes
    endianness: Endianness

    def unpack(self: Self, format: str) -> tuple[Any, ...]:
        return struct.unpack(f'{self.endianness.unpack_char}{format}', self.data)

    def chunk(self: Self, chunk_size) -> Iterator[Self]:
        if len(self) % chunk_size != 0:
            raise ValueError(
                f'Cannot chunk data exactly into {chunk_size}: length {len(self)}',
            )
        yield from (
            self[chunk_index * chunk_size : (chunk_index * chunk_size) + chunk_size]
            for chunk_index in range(len(self) // chunk_size)
        )

    def __len__(self: Self) -> int:
        return len(self.data)

    def __getitem__(self: Self, key: int | slice) -> Self:
        return type(self)(
            data=self.data[key],
            endianness=self.endianness,
        )


@dataclasses.dataclass
class Tag:
    code: int
    data_type: int
    count: int
    value: Any
    raw: TIFFBytes = dataclasses.field(repr=False)
    offset: int | None = dataclasses.field(default=None, repr=False)

    @classmethod
    def from_bytes(
        cls: type[Self],
        tiff: TIFFMeta,
        tag_bytes: TIFFBytes,
    ) -> Self:
        code, data_type, count = tag_bytes[:8].unpack('HHI')
        offset, raw, unpacked = cls.unpack_tag_value(
            tiff, data_type, count, tag_bytes[8:]
        )
        return cls(
            code=code,
            data_type=data_type,
            count=count,
            value=unpacked,
            raw=raw,
            offset=offset,
        )

    @staticmethod
    def unpack_tag_value(
        tiff: TIFFMeta, data_type: int, count: int, value: TIFFBytes
    ) -> tuple[int | None, bytes, Any]:
        struct_dtype = DATA_TYPES[data_type]
        size = count * struct.calcsize(struct_dtype)

        offset = None
        if size > len(value):
            offset = value.unpack('I')[0]
            value = tiff.read_bytes(offset, offset + size)

        unpacked = value[:size].unpack(str(count) + struct_dtype)

        # if data_type == 2 (ASCII) we want to join the chars together
        if data_type == 2:
            return offset, value, b''.join(unpacked)
        elif count == 1:
            return offset, value, unpacked[0]
        return offset, value, unpacked


class Tags(dict[int, Tag]):
    @classmethod
    def from_tags(cls: type[Self], tags: list[Tag]) -> Self:
        return cls((t.code, t) for t in tags)

    @classmethod
    def from_tiff_bytes(cls: type[Self], tiff: TIFFMeta, tags_bytes: TIFFBytes) -> Self:
        return cls.from_tags(
            [Tag.from_bytes(tiff, tag_bytes) for tag_bytes in tags_bytes.chunk(12)]
        )


@dataclasses.dataclass
class IFD:
    offset: int
    tags: Tags
    next_offset: int

    @classmethod
    def from_tiff_offset(cls: type[Self], tiff: TIFFMeta, offset: int) -> Self:
        tags_start = offset + 2
        tags_count = tiff.read_bytes(offset, tags_start).unpack('H')[0]
        tags_end = tags_start + (tags_count * tag_size)
        tags_bytes = tiff.read_bytes(tags_start, tags_end)
        next_offset = tiff.read_bytes(tags_end, tags_end + 4).unpack('I')[0]

        return cls(
            offset=offset,
            tags=Tags.from_tiff_bytes(tiff, tags_bytes),
            next_offset=next_offset,
        )


@dataclasses.dataclass
class TIFFMeta:
    """Class to help parse TIFF IFDs. Only supports standard TIFFs, not BigTIFF."""

    href: str
    endianness: Endianness
    ifds: list[IFD]

    # We can track the max byte read to parse out IFD stuff.
    # This could be an interesting data point to learn how to better optimize reads.
    max_ifd_byte: int = 0

    def __init__(self: Self, href: str) -> None:
        self.href = href

        # we don't use self.read_bytes yet because we don't have endianness
        __bytes = url_read_bytes(self.href, 0, 8)
        self.max_ifd_byte = 8
        self.endianness = Endianness(__bytes[0:2])

        _bytes = TIFFBytes(data=__bytes, endianness=self.endianness)

        magic_number = _bytes[2:4].unpack('H')[0]
        if magic_number != 42:
            raise TypeError(f'Unsupported file type: magic number {magic_number} != 42')

        self.ifds: list[IFD] = []
        ifd_offset = _bytes[4:8].unpack('I')[0]
        while ifd_offset:
            ifd = self.parse_ifd(ifd_offset)
            self.ifds.append(ifd)
            ifd_offset = ifd.next_offset

    def read_bytes(self: Self, start: int, end: int) -> TIFFBytes:
        # Note that reading for each byte range we want is terribly inefficient.
        # We could instead use some sort of filelike object that will read and cache
        # larger chunks of the file, as needed to accommodate requested byte ranges.
        # Of course if we wanted to read the whole file this way we'd need to be careful
        # of the memory requirements of such a solution.
        self.max_ifd_byte = max(self.max_ifd_byte, end)
        return TIFFBytes(
            data=url_read_bytes(self.href, start, end),
            endianness=self.endianness,
        )

    def parse_ifd(self: Self, offset: int) -> IFD:
        return IFD.from_tiff_offset(self, offset)


# %%
tiff_meta = TIFFMeta(href)
pprint(tiff_meta)

# %% [markdown]
# #### A note about `tiff_meta.max_ifd_byte`
#
# After parsing all IFDs in the file, including reading and unpacking all the tags, we see that the max byte read from the file (`max_ifd_byte`) is merely 4208. Thus we could be pretty sure, for many TIFF files, that reading something like the first 32KB of file data would give us the entire set of IFDs. We could use this insight to make our reader more efficient: if we made only one read request to for the first 32KB of the file (like real readers do), we could be pretty certain we could parse the IFD without having to incur the penalty of any further network round trips, at least until we are ready to retrieve image data.
