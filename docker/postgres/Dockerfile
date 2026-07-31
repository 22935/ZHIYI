ARG POSTGRES_IMAGE=public.ecr.aws/docker/library/postgres:15.17-alpine@sha256:09e4f20b14ddb3dfe3a0c825b206032aaf8f28300ba2070c0b60fc1c10c6abc7
FROM ${POSTGRES_IMAGE}

COPY secret-entrypoint.sh /usr/local/bin/kinlin-postgres-entrypoint
COPY init-app-role.sh /docker-entrypoint-initdb.d/20-kinlin-app-role.sh
RUN chmod 0755 /usr/local/bin/kinlin-postgres-entrypoint /docker-entrypoint-initdb.d/20-kinlin-app-role.sh

ENTRYPOINT ["/usr/local/bin/kinlin-postgres-entrypoint"]
CMD ["postgres"]
