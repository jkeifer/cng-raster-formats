FROM quay.io/jupyter/base-notebook:python-3.12
COPY requirements.txt .
RUN pip install -r requirements.txt

CMD start-notebook.py --IdentityProvider.token=''
