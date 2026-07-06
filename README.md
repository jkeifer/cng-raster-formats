# Exploring Cloud-Native Geospatial Formats: A Hands-on Workshop for Raster Data

This is the **participant branch** of the workshop: it contains the
ready-to-run exercise notebooks and everything needed to run them. (If you are
looking to contribute to the workshop content itself, see the
[`main` branch](https://github.com/jkeifer/cng-raster-formats/tree/main)
instead.)

## Workshop Overview

Ever wonder what GDAL is doing under the hood when you read a GeoTIFF file?
Doubly so when the file is a Cloud-Optimized GeoTIFF (COG) on a remote server
somewhere? Have you been wondering what this new GeoZarr thing is all about and
how it actually works? Then there's the whole Kerchunk/VirtualiZarr indexing to
get cloud-native access for non-cloud-native data formats, what's that about?

Cloud-native geospatial is all the rage these days, and for good reason. As
file sizes grow, layer counts increase, and analytical methods become more
complex, the traditional download-to-the-desktop approach is quickly becoming
untenable for many applications. It's no surprise then that users are turning
to cloud-based tools such as Dask to scale out their analyses, or that
traditional tooling is adopting new ways of finding and accessing data from
cloud-based sources. But as we transition away from opening whole files to now
grabbing ranges of bytes off remote servers it seems all the more important to
understand exactly how cloud-native data formats actually store data and what
tools are doing to access it.

This workshop digs into how cloud-native geospatial data formats enable new
operational paradigms, with a particular focus on raster data. All three
exercises work with the same Sentinel-2 scene — even the same pixel — so the
formats can be compared apples to apples:

1. **Reading Cloud-Optimized GeoTIFFs the Hard Way**
   (`01_reading-cogs-the-hard-way`): find a COG via STAC, then read it with
   nothing but HTTP range requests and the Python standard library — parse the
   TIFF headers by hand, chase byte offsets, and decode an image tile yourself.
2. **Reading Zarr the Hard Way** (`02_reading-zarr-the-hard-way`): read the
   very same scene from a Zarr v3 GeoZarr store, again by hand over plain
   HTTP — explore the v3 metadata and codec pipeline, the geospatial
   conventions, multiscales, and what zarr does (and does not) solve.
3. **Free-Range Artisanal Grass-Fed Kerchunk**
   (`03_free-range-artisanal-grass-fed-kerchunk`): hand-build a kerchunk
   reference manifest that maps zarr chunk keys onto the COG's internal tile
   bytes, then open the COG "as zarr" — and see the modern take on the same
   idea with VirtualiZarr and Icechunk.

### Prerequisites

This workshop expects some familiarity with geospatial programming in Python.
Most of the notebook code is already provided, so any gaps in understanding
don't necessarily prohibit completing the exercises. That said, a basic
knowledge of cloud-native geospatial Python tooling and working with rasters as
single and multidimensional arrays is quite helpful.

A good primer workshop is Alex Leith of Auspatious's [Cloud-Native Geospatial
for Earth Observation Workshop](
https://github.com/auspatious/cloud-native-geospatial-eo-workshop).
It is recommended to work through those activities or have an equivalent
knowledge prior to working through the notebooks in this workshop.

## What's in this repo

* [`notebooks/`](./notebooks) — the **exercise notebooks**, one per exercise.
  These are the ones to work through: some cells are cleared for you to fill
  in, and the answer cells are omitted.
* [`notebooks/completed/`](./notebooks/completed) — the **completed
  notebooks**, with every cell filled in. Use them if you get stuck, want to
  check an answer, or want to review the material after the workshop.
* [`notes/`](./notes) — per-exercise markdown notes extracted from the
  notebooks, handy as a reference during and after the workshop.

All three notebooks read public data over plain HTTP(S) — no credentials or
cloud accounts are needed, just an internet connection.

## Getting Started

To run the notebooks you need a Jupyter environment with this project's
dependencies installed. Three options, in rough order of ease:

* **GitHub Codespaces** — nothing to install locally; just a GitHub account
  and a browser.
* **Docker compose** — a locally-run, fully-specified environment; good when
  conference internet makes an external service risky.
* **`uv`** — run JupyterLab directly on your machine; no docker required.

### Running in GitHub Codespaces (easiest)

This method does not require any environment setup, repo cloning, or having to
execute any code locally. However, it does depend on an external, web-based
service, which may not be ideal in environments with unknown internet quality
(i.e., conferences). Codespaces also sometimes have instability or weirdness
that does not occur when executing locally. But the fact that all this option
requires is a GitHub account and a web browser means it can be a great solution
for many users.

To use GitHub Codespaces, first login to GitHub. Then, browse to [the project
repo in GitHub](https://github.com/jkeifer/cng-raster-formats). There, click
the green `<> Code` dropdown button, select the `Codespaces` tab in the
dropdown menu, then click the button to add a new codespace from the
`workshop` branch.

The codespace will launch in a new browser tab, running the web version of VS
Code. The notebooks can be opened and executed directly in this interface. The
notebook kernel will need to be selected to execute code; choose the `.venv`
kernel from the existing Python Environments option.

Codespaces also have experimental JupyterLab support. For users that might want
to try this, wait for the codespace to fully initialize. Then, go back to the
repo in GitHub and open the codespaces dropdown menu (you will likely need to
refresh the page). You should see the codespace listed, and a button with three
dots `...` next to it. Click that button to open a menu with more actions for
the codespace, then select "Open in JupyterLab". Select a notebook from the
`notebooks` directory and work through it.

### Running locally with docker

Using docker has the advantage of better constraining the execution
environment, which is also set up automatically with the required dependencies.

Note that the instructions below were written with a MacOS/Linux environment in
mind. Windows users will likely need to leverage WSL to access a Linux
environment to run docker.

To begin, clone this repo (the `workshop` branch):

```commandline
git clone --branch workshop https://github.com/jkeifer/cng-raster-formats.git
cd cng-raster-formats
```

Ensure the docker daemon or an equivalent is running via whatever mechanism is
preferred (on Linux via the docker daemon or podman; on MacOS via Docker
Desktop, colima, podman, OrbStack, or others), then use `docker compose` to
`up` the project:

```commandline
docker compose up
```

This will start up the Jupyter container within docker in the foreground. If
preferring to run compose in the background, add the detach option to the
compose command via the `-d` flag.

JupyterLab will be started with no authentication, running on port 8888 (by
default; use the env var `JUPYTER_PORT` to change it if that port is already
taken on your machine). Open a web browser and browse to
[`http://127.0.0.1:8888`](http://127.0.0.1:8888) to open the JupyterLab
interface. Select a notebook from the `notebooks` directory and work through
it.

### Running locally using `uv`

This approach is more subject to local environment differences than the
docker-based approaches, but it does have the benefit of not requiring docker
as a dependency. For users on Linux or MacOS that have experience managing a
python environment, this may quite honestly be the best option.

Note that the instructions below were written with a MacOS/Linux environment in
mind. Windows users will likely need to leverage something like [git for
Windows](https://gitforwindows.org/) and the included Git BASH tool to follow
along (WSL is also likely a viable solution to get a Linux environment on a
Windows machine).

To get started, clone this repository (the `workshop` branch) and start up
JupyterLab using `uv run`. Users will need to have
[`uv` installed](https://docs.astral.sh/uv/getting-started/installation/) to
use this option.

```commandline
git clone --branch workshop https://github.com/jkeifer/cng-raster-formats.git
cd cng-raster-formats
uv run jupyter lab
```

The `uv run jupyter lab` will create a virtual environment with a compatible
version of python, install all dependencies (locked in `uv.lock`), then launch
JupyterLab. A web browser window should automatically be launched with this
project loaded. Select a notebook from the `notebooks` directory and work
through it.

## Untrusted Notebooks

If when running a notebook certain cell outputs (folium maps, particularly) do
not display and instead show an error about the notebook not being trusted,
press CMD+Shift+P / CTRL+Shift+P to bring up the command pallet, then type
"Trust Notebook". Select the command with that name to trust the current
notebook.

## Presentation History

### Origin

This workshop was originally created for FOSS4G 2024 and was presented as a
["Deep Dive into Cloud-Native Geospatial Raster
Formats"](https://talks.osgeo.org/foss4g-2024-workshop/talk/TNYSY9/). The
slides from [that particular presentation are
here](https://docs.google.com/presentation/d/1qFckA0prY604I4dMkQlF1ZM-QSKS2ou4-YttgGQHzOU/).

### All Workshop Presentations

| Date | Location | Slides | Notes |
| ---- | -------- | ------ | ----- |
| TBD (2026) | TBD | TBD | 2026 presentation details to be announced. |
| 2025-11-17 | [FOSS4G Auckland, NZ](https://talks.osgeo.org/foss4g-2025/talk/KZGHTZ/) | [Link](https://docs.google.com/presentation/d/1oJ48g9Oc-60MlG2_wFTlAHo42SMYFGeiRG66Pc6cr48) | Full workshop presentation. |
| 2025-11-03 | [FOSS4G NA Reston, VA, USA](https://talks.osgeo.org/foss4g-na-2025/talk/MN7NCT/) | [Link](https://docs.google.com/presentation/d/1oJ48g9Oc-60MlG2_wFTlAHo42SMYFGeiRG66Pc6cr48) | Full workshop presentation. |
| 2025-05-01 | CNG Conference | [Link](https://docs.google.com/presentation/d/1nBKAhig0mXkxbzxLRGgu9ygY7Uc028pbdL4qQmlyZ4c/) | Partial presentation (only COG notebook) as part of [a combined workshop on CNG for EO](https://conference.cloudnativegeo.org/CNGConference2025#/workshops?lang=en#CNG%20Workshop:~:text=CNG%20for%20EO%20and%20Deep%20Dive%20into%20Cloud%2DNative%20Geospatial%20Raster%20Formats). |
| 2025-01-22 | Online (Virtual) | [Link](https://docs.google.com/presentation/d/1k5m2eYV8Tv4YrTAL6pfjmZMhls51cChW_QO1vcXH_0U/) | Partial presentation (only COG notebook) for users in Oceania. |
| 2024-12-03 | [FOSS4G Belém, Brazil](https://talks.osgeo.org/foss4g-2024-workshop/talk/TNYSY9/) | [Link](https://docs.google.com/presentation/d/1qFckA0prY604I4dMkQlF1ZM-QSKS2ou4-YttgGQHzOU/) | Original presentation. |
