FROM postgres:17.12-bookworm@sha256:837bed18782820fe967067cb5328b02b0d9992c1be9a37ee0c9c492cfc03af3b

RUN apt-get update \
    && apt-get install --no-install-recommends -y python3 python3-venv ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv /opt/patroni \
    && /opt/patroni/bin/pip install --no-cache-dir 'patroni[etcd3,psycopg3]==4.1.5'

ENV PATH="/opt/patroni/bin:${PATH}" \
    PATRONICTL_CONFIG_FILE=/etc/patroni/patroni.yml
COPY patroni.yml patroni-participant.yml /etc/patroni/
COPY --chmod=755 bootstrap.sh /usr/local/bin/bootstrap.sh

USER postgres
EXPOSE 5432 8008
STOPSIGNAL SIGTERM
ENTRYPOINT ["patroni"]
CMD ["/etc/patroni/patroni.yml"]
