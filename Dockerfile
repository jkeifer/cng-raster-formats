FROM quay.io/jupyter/base-notebook:python-3.12

USER root

RUN apt-get update && \
    apt-get install -y gcc gdal-bin && \
    rm -rf /var/cache/apt/archives /var/lib/apt/lists

USER ${NB_UID}

COPY requirements.txt .
RUN pip install -r requirements.txt

CMD start-notebook.py --IdentityProvider.token=''
