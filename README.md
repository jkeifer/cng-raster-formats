# Deep Dive into Cloud-Native Geospatial Raster Formats Workshop

Originally created for the FOSS4G 2024 workshop ["Deep Dive into Cloud-Native
Geospatial Raster
Formats"](https://talks.osgeo.org/foss4g-2024-workshop/talk/TNYSY9/).

## Getting Started

The interesting contents of this repo are, primarily, the Jupyter notebooks. To
facilitate easily running the notebooks in a properly-initialized environment,
both a docker compose file and a GitHub Codespaces configuration are provided.
Alternately, one can set up their own python environment and run Jupyter
without a dependency on docker.

Docker compose is the recommended approach if wanting to keep all services
local (due to bad internet and/or concerns about leveraging GitHub serivces).

### Running locally without docker

This approach is not recommended as it is more subject to local environment
differences than the docker-based approaches. But it does have the benefit of
not requiring docker as a dependency.

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
with this project loaded. Select a notebook and work through it.

### Running locally with docker (recommended)

Using docker has the advantage of better constraining the execution
environment, which is also set up automatically with the required dependencies.

To begin, clone this repo:

```commandline
git clone https://github.com/jkeifer/cng-raster-formats.git
cd cng-raster-formats
```

Ensure docker is running via whatever mechanism is preferred (Docker Desktop,
colima, podman, etc.), then use docker compose to up the project:

```commandline
docker compose up
```

This will start up the Jupyter container within docker in the foreground. If
preferring to run compose in the background, add the detach option to the
compose command via the `-d` flag.

JupyterLab will be started with no authentication, running on port 8888 (by
default; use the env var `JUPYTER_PORT` to change it if that port is already
taken on your machine). Open a web browser and browse to
[`http://127.0.0.1:8888`](http://127.0.0.1:8888) to open the JupterLab
interface. Select a notebook and work through it.

### Running in GitHub Codespaces

This method is also recommended because it does not require any user
configuration to get up and running. However, it does depend on an external,
web-based service, which may not be ideal in environments with unknown internet
quality (i.e., FOSS4G). This said, it does not require the user to run
_anything_ locally, which may be necessary for users with Windows or
administratively locked-down machines.

To use GitHub Codespaces, browse to [the project repo in
Github](https://github.com/jkeifer/cng-raster-formats). There, click the green
`<> Code` dropdown button, select the `Codespaces` tab in the dropdown menu,
then click the button to add a new codespace from the `main` branch.

Once the codespace is fully started, go back into the codespaces dropdown menu
on the project repo page (you will likely need to refresh the page). You should
see the codespace listed, and a button with three dots `...` next to it. Click
that button to open a menu with more actions for the codespace, then select
"Open in JupyterLab". Select a notebook and work through it.
