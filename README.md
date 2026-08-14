# Exploring Cloud-Native Geospatial Formats: A Hands-on Workshop for Raster Data

Dig into three cloud-native raster formats—COGs, Zarr, and Kerchunk—and learn
how data access works under the hood with hands-on Python exercises, no image
libraries required!

[Slides for the 2026 FOSS4G Workshop are
here.]()

Using the [docker execution
method](#running-locally-with-docker) may be
the best option due to the uncertainty of conference internet quality. But
GitHub Codespaces can be a good fallback option for those that want/need a
simpler solution.

## Workshop Overview

Cloud-native geospatial is all the rage these days, and for good reason. As
data sizes grow, layer counts increase, and analytical methods become more
complex, the traditional download-to-the-desktop approach is often untenable.
It's no surprise then that users are turning to cloud-native tools to scale out
their analyses. But as we transition away from opening whole files to now
grabbing ranges of bytes off remote servers it seems all the more important to
understand exactly how cloud native data formats actually store data and what
tools are doing to access it.

This workshop aims to dig into how cloud-native geospatial data formats are
enabling new operational paradigms, with a focus on raster formats. We'll start
by surveying the current cloud-native geospatial landscape to understand the
importance of cloud native and how it is being used, including the core tenants
of cloud-native, common formats, and how things like SpatioTemporal Asset
Catalogs (STAC) and STAC-based tooling integrate to provide more efficient
access paradigms.

Then we'll get hands-on to build up an understanding of how these formats work
at a deep level. We'll extract a tile from a COG by hand, then try the same
with Zarr data to see how those formats compare. Lastly, we'll look at
Kerchunk/VirtualiZarr and see how these allow optimized data access for
non-cloud-native formats.

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

> [!IMPORTANT]
> Remember, this branch is `workshop`, so all the clone commands below require
> you to select the `workshop` branch (or switch to it once you clone).

### Running in GitHub Codespaces (easiest)

This method does not require any environment setup, repo cloning, or having to
execute any code locally. All this option requires is a GitHub account and a
web browser, making it simple solution for many users. However, it does depend
on an external, web-based service, which may not be ideal in environments with
unknown internet quality (i.e., conferences).

To use GitHub Codespaces, first login to GitHub. Then, go to this link
https://codespaces.new/jkeifer/cng-raster-formats/tree/workshop and click the
green "Create Codespace" button.

(To do the same as that link manually, browse to [the project repo in
Github](https://github.com/jkeifer/cng-raster-formats). There, click the green
`<> Code` dropdown button, select the `Codespaces` tab in the dropdown menu. On
that menu click the three dot menu and select "New with options...". On the
screen the opens changes the branch to the `workshop` branch, usa all the other
defaults, and click the green "Create Codespace" button.)

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
| 2026-08-30 | [FOSS4G Hiroshima, Japan](https://talks.osgeo.org/foss4g-2026-workshop/talk/8ZUPMV/) | [Link](https://docs.google.com/presentation/d/1qiGfzzhOrWNkxmfskMmoIji-JGGjj2s-8KcUhnBPzUM) | Full workshop presentation. |
| 2025-11-17 | [FOSS4G Auckland, NZ](https://talks.osgeo.org/foss4g-2025/talk/KZGHTZ/) | [Link](https://docs.google.com/presentation/d/1oJ48g9Oc-60MlG2_wFTlAHo42SMYFGeiRG66Pc6cr48) | Full workshop presentation. |
| 2025-11-03 | [FOSS4G NA Reston, VA, USA](https://talks.osgeo.org/foss4g-na-2025/talk/MN7NCT/) | [Link](https://docs.google.com/presentation/d/1oJ48g9Oc-60MlG2_wFTlAHo42SMYFGeiRG66Pc6cr48) | Full workshop presentation. |
| 2025-05-01 | CNG Conference | [Link](https://docs.google.com/presentation/d/1nBKAhig0mXkxbzxLRGgu9ygY7Uc028pbdL4qQmlyZ4c/) | Partial presentation (only COG notebook) as part of [a combined workshop on CNG for EO](https://conference.cloudnativegeo.org/CNGConference2025#/workshops?lang=en#CNG%20Workshop:~:text=CNG%20for%20EO%20and%20Deep%20Dive%20into%20Cloud%2DNative%20Geospatial%20Raster%20Formats). |
| 2025-01-22 | Online (Virtual) | [Link](https://docs.google.com/presentation/d/1k5m2eYV8Tv4YrTAL6pfjmZMhls51cChW_QO1vcXH_0U/) | Partial presentation (only COG notebook) for users in Oceania. |
| 2024-12-03 | [FOSS4G Belém, Brazil](https://talks.osgeo.org/foss4g-2024-workshop/talk/TNYSY9/) | [Link](https://docs.google.com/presentation/d/1qFckA0prY604I4dMkQlF1ZM-QSKS2ou4-YttgGQHzOU/) | Original presentation. |
