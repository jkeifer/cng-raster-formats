FROM quay.io/jupyter/base-notebook:python-3.13

USER root

RUN pip install uv

USER ${NB_UID}

COPY uv.lock pyproject.toml .
RUN uv export --locked --format requirements.txt | uv pip install -r - --system

CMD start-notebook.py --IdentityProvider.token=''
