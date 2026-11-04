# Les images bde2020 (Debian 9) ne contiennent pas Python, et le python3 de Debian 9
# est trop ancien pour les f-strings du TD1 : on ajoute un Python 3.11 autonome.
ARG BASE_IMAGE
FROM ${BASE_IMAGE}
ADD https://github.com/astral-sh/python-build-standalone/releases/download/20241016/cpython-3.11.10+20241016-x86_64-unknown-linux-gnu-install_only.tar.gz /tmp/python.tar.gz
RUN tar -xzf /tmp/python.tar.gz -C /opt \
    && rm /tmp/python.tar.gz \
    && ln -s /opt/python/bin/python3 /usr/bin/python3
