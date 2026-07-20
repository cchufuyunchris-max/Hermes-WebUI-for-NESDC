FROM jupyterhub/jupyterhub:5

RUN python3 -m pip install --no-cache-dir dockerspawner jupyterhub-nativeauthenticator oauthenticator

COPY docker/jupyterhub/jupyterhub_config.py /srv/jupyterhub/jupyterhub_config.py

WORKDIR /srv/jupyterhub

CMD ["jupyterhub", "-f", "/srv/jupyterhub/jupyterhub_config.py"]
