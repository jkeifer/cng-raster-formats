# Notebook Notes

This file contains the original content of cells marked for note-taking.

## cell0

```python
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
```

## cell1

```python
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
```

## cell2

```python
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
```

## cell3

```python
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
```

## cell4

```python
#| scrub-note: cell4
root_group = zarr.open_group(store, mode='r')
sorted(root_group.keys())
```

## cell5

```python
#| scrub-note: cell5
red_array = root_group['red']
red_array.info
```

## cell6

```python
#| scrub-note: cell6
import xarray

dataset = xarray.open_zarr(store, consolidated=False)
dataset
```

## cell7

```python
#| scrub-note: cell7
poi_reflectance = float(dataset.red[7471, 211].values)
print(f'POI red reflectance: {poi_reflectance:.4f}')
```

## cell8

```python
#| scrub-note: cell8
two_tiles = dataset.red[7168:8192, 0:2048].values
two_tiles.shape
```

## cell9

```python
#| scrub-note: cell9
two_tiles_apart = dataset.red[7168:9216, 0:1024].values
two_tiles_apart.shape
```

## cell10

```python
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
```

## cell11

```python
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
```

## cell12

```python
#| scrub-note: cell12
virtual_dataset = manifest_store.to_virtual_dataset()
virtual_dataset
```

## cell13

```python
#| scrub-note: cell13
session = repo.writable_session('main')
virtual_dataset.vz.to_icechunk(session.store)
snapshot_id = session.commit('add virtual references to the S2 B04 COG')
snapshot_id
```

## cell14

```python
#| scrub-note: cell14
readonly_session = repo.readonly_session(branch='main')
ic_dataset = xarray.open_zarr(readonly_session.store, consolidated=False)
print(f'POI red reflectance: {float(ic_dataset.red[7471, 211].values):.4f}')
```

## cell15

```python
#| scrub-note: cell15
print(set(readonly_session.all_virtual_chunk_locations()))
for snapshot in repo.ancestry(branch='main'):
    print(f'{snapshot.id}: {snapshot.message}')
```

---
*Generated by ipynb-scrubber*
