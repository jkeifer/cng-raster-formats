# Exploring Cloud-Native Geospatial Formats: A Hands-on Workshop for Raster Data

[Slides for the 2025-05-01 CNG Conf workshop are here.](https://docs.google.com/presentation/d/1nBKAhig0mXkxbzxLRGgu9ygY7Uc028pbdL4qQmlyZ4c/)

## Workshop Overview

Ever wonder what GDAL is doing under the hood when you read a GeoTIFF file?
Doubly so when the file is a Cloud-optimized GeoTIFF (COG) on a remote server
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
understand exactly how cloud native data formats actually store data and what
tools are doing to access it.

This workshop aims to dig into how cloud-native geospatial data formats are
enabling new operational paradigms, with a particular focus on raster data
formats. We'll start on the surface by surveying the current cloud-native
geospatial landscape to gain an understanding of why cloud native is important
and how it is being used, including:

* the core tenets of cloud-native geospatial data formats
* cloud-native data formats for both raster and non-raster geospatial data
* introduction to SpatioTemporal Asset Catalogs (STAC) and how higher-level
  STAC-based tooling can leverage cloud-native formats for efficient raster
  data access
  processing of cloud-native data

Then we'll get hands-on and go deep to build up an in-depth understanding of
how cloud native raster formats work. We'll examine the COG format and read a
COG from a cloud source by hand using just Python, selectively extracting data
from the image without any geospatial dependencies. We'll repeat the same
exercise for geospatial data in Zarr format to see how that compares to our
experience with COGs. Lastly we'll turn our attention to Kerchunk/VirtualiZarr
to see how these technologies might allow us to optimize data access for
non-cloud-native formats.

### Prerequisites

This workshops expects some familiarity with geospatial programming in Python.
Most of the notebook code is already provided, so any gaps in understanding
don't necessarily prohibit completing the exercises. That said, a basic
knowledge of Cloud-Native Geospatial Python tooling and working with rasters as
single and multidimensional arrays is quite helpful.

A good primer workshop is Alex Leith of Auspatious's [Cloud-Native Geospatial
for Earth Observation Workshop](
https://github.com/auspatious/cloud-native-geospatial-eo-workshop).
It is recommended to work through those activities or have an equivalent
knowledge prior to working through the notebooks in this workshop.

## Getting Started

The interesting contents of this repo are, primarily, the Jupyter notebooks in
the [`./notebooks`](./notebooks) directory. To facilitate easily running the
notebooks in a properly-initialized environment, a docker compose file is
provided. The project can also be run in a GitHub codespace without having to
run anything locally. Alternately, one can set up their own python environment
and run Jupyter without a dependency on docker.

Docker compose is the recommended approach if wanting to keep all services
local (due to bad internet and/or concerns about leveraging GitHub serivces).
GitHub codespaces are recommended if considering ease of use alone.

### Running in GitHub Codespaces (recommended as easiest approach)

This method is also recommended because it does not require any user
configuration to get up and running. However, it does depend on an external,
web-based service, which may not be ideal in environments with unknown internet
quality (i.e., FOSS4G). This said, it does not require the user to run anything
locally beyond a web browser, which may be necessary for users with Windows or
administratively locked-down machines.

To use GitHub Codespaces, browse to [the project repo in
Github](https://github.com/jkeifer/cng-raster-formats). There, click the green
`<> Code` dropdown button, select the `Codespaces` tab in the dropdown menu,
then click the button to add a new codespace from the `main` branch.

Once the codespace is fully started, go back into the codespaces dropdown menu
on the project repo page (you will likely need to refresh the page). You should
see the codespace listed, and a button with three dots `...` next to it. Click
that button to open a menu with more actions for the codespace, then select
"Open in JupyterLab". Select a notebook from the `notebooks` directory and work
through it.

### Running locally with docker (recommended for local executions)

Using docker has the advantage of better constraining the execution
environment, which is also set up automatically with the required dependencies.

Note that the instructions below were written with a MacOS/Linux environment in
mind. Windows users will likely need to leverage WSL to access a Linux
environment to run docker.

To begin, clone this repo:

```commandline
git clone https://github.com/jkeifer/cng-raster-formats.git
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

### Running locally without docker (least recommended approach)

This approach is not recommended as it is more subject to local environment
differences than the docker-based approaches. But it does have the benefit of
not requiring docker as a dependency.

Note that the instructions below were written with a MacOS/Linux environment in
mind. Windows users will likely need to leverage something like [git for
Windows](https://gitforwindows.org/) and the included Git BASH tool to follow
along (WSL is also likely a viable solution to get a Linux environment on a
Windows machine).

To get started, clone this repository and set up a python venv. Python >=3.12
is recommended:

```commandline
git clone https://github.com/jkeifer/cng-raster-formats.git
cd cng-raster-formats
python -m venv .venv
source .venv/bin/activate
```

With the activated virtual environment, install the required python dependencies:

```commandline
pip install -r requirements.txt
```

Doing so will install Jupyter, which can then be started by running the
following command:

```commandline
jupyter lab
```

Jupyter should automatically launch the JupyterLab interface in a web browser
with this project loaded. Select a notebook from the `notebooks` directory and
work through it.

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
| 2025-05-01 | CNG Conference | [Link](https://docs.google.com/presentation/d/1nBKAhig0mXkxbzxLRGgu9ygY7Uc028pbdL4qQmlyZ4c/) | Partial presentation (only COG notebook) as part of [a combined workshop on CNG for EO](https://conference.cloudnativegeo.org/CNGConference2025#/workshops?lang=en#CNG%20Workshop:~:text=CNG%20for%20EO%20and%20Deep%20Dive%20into%20Cloud%2DNative%20Geospatial%20Raster%20Formats). |
| 2025-01-22 | Online (Virtual) | [Link](https://docs.google.com/presentation/d/1k5m2eYV8Tv4YrTAL6pfjmZMhls51cChW_QO1vcXH_0U/) | Partial presentation (only COG notebook) for users in Oceania. |
| 2024-12-03 | FOSS4G Belém, Brazil | [Link](https://docs.google.com/presentation/d/1qFckA0prY604I4dMkQlF1ZM-QSKS2ou4-YttgGQHzOU/) | Original presentation. |
