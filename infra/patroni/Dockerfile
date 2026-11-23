FROM postgres:17.12-bookworm@sha256:837bed18782820fe967067cb5328b02b0d9992c1be9a37ee0c9c492cfc03af3b

RUN apt-get update \
    && apt-get install --no-install-recommends -y python3 python3-venv ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv /opt/patroni
COPY requirements.txt /opt/patroni/requirements.txt
RUN /opt/patroni/bin/pip install --no-cache-dir -r /opt/patroni/requirements.txt

ENV PATH="/opt/patroni/bin:${PATH}" \
    PGDATA=/var/lib/postgresql/data/pgdata \
    PATRONICTL_CONFIG_FILE=/run/patroni/patroni.yml
COPY patroni.yml /etc/patroni/patroni.yml
COPY configure.py bootstrap.py entrypoint.sh /usr/local/bin/
RUN chmod 755 /usr/local/bin/entrypoint.sh /usr/local/bin/bootstrap.py \
    && install -d -o postgres -g postgres -m 700 /run/patroni

EXPOSE 5432 8008
STOPSIGNAL SIGTERM
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
