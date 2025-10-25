FROM quay.io/jupyter/base-notebook:python-3.13

USER root

RUN pip install uv

USER ${NB_UID}

COPY uv.lock pyproject.toml .
RUN uv sync --locked

CMD start-notebook.py --IdentityProvider.token=''
