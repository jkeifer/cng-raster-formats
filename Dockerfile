FROM quay.io/jupyter/base-notebook:python-3.13

USER root

RUN pip install uv --no-cache-dir --root-user-action ignore

USER ${NB_UID}

COPY uv.lock pyproject.toml /tmp/
RUN rmdir "/home/${NB_USER}/work" && \
    cd /tmp/ && \
    uv export --locked --format requirements.txt \
    | uv pip install -r - --system --no-cache-dir

COPY notebooks/ "/home/${NB_USER}/notebooks"
COPY notes/ "/home/${NB_USER}/notes"
COPY README.md "/home/${NB_USER}/"

CMD start-notebook.py --IdentityProvider.token=''
