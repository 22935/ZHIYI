ARG FLYWAY_IMAGE=flyway/flyway:9.22.3@sha256:9e78682c33f6b22e83b00a2971a3e8b0f257a51857dfc34ed4a5f6a839038239
FROM ${FLYWAY_IMAGE}

USER root
COPY entrypoint.sh /usr/local/bin/kinlin-flyway-entrypoint
RUN apt-get update \
    && apt-get install -y --no-install-recommends gosu \
    && rm -rf /var/lib/apt/lists/* \
    && ln -s "$(command -v gosu)" /usr/local/bin/su-exec \
    && groupadd --gid 10004 kinlin \
    && useradd --uid 10004 --gid 10004 --no-create-home --shell /usr/sbin/nologin kinlin \
    && chmod 0755 /usr/local/bin/kinlin-flyway-entrypoint
ENTRYPOINT ["/usr/local/bin/kinlin-flyway-entrypoint"]
