ARG MAVEN_IMAGE=public.ecr.aws/docker/library/maven:3.9.16-eclipse-temurin-17@sha256:1ed5d1f54416b706707b4f3238f63a20bb06aab27c6d240090a2bb9ad895ed45
ARG JAVA_RUNTIME_IMAGE=public.ecr.aws/docker/library/eclipse-temurin:17.0.19_10-jre-jammy@sha256:475d8e96b4b2bfe08999e5e854755c773af1581acdf959a4545d88f0696a2339

FROM ${MAVEN_IMAGE} AS build

WORKDIR /workspace

COPY pom.xml .
RUN --mount=type=cache,target=/root/.m2 mvn -B -ntp dependency:go-offline

COPY src ./src
RUN --mount=type=cache,target=/root/.m2 mvn -B -ntp -DskipTests package

FROM ${JAVA_RUNTIME_IMAGE}

ARG KINLIN_VERSION=dev
ARG KINLIN_REVISION=unknown
ARG KINLIN_CREATED=unknown
LABEL org.opencontainers.image.title="Kinlin AI Backend" \
      org.opencontainers.image.version="$KINLIN_VERSION" \
      org.opencontainers.image.revision="$KINLIN_REVISION" \
      org.opencontainers.image.created="$KINLIN_CREATED"

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends gosu iproute2 wget \
    && rm -rf /var/lib/apt/lists/* \
    && ln -s "$(command -v gosu)" /usr/local/bin/su-exec \
    && groupadd --gid 10001 kinlin \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin kinlin \
    && mkdir -p /app/data/uploads /run/kinlin-secrets \
    && chown -R 10001:10001 /app /run/kinlin-secrets

COPY --from=build /workspace/target/federal-hub-backend-*.jar /app/app.jar
COPY docker-entrypoint.sh /usr/local/bin/kinlin-entrypoint
RUN chmod 0755 /usr/local/bin/kinlin-entrypoint

EXPOSE 8080

ENTRYPOINT ["/usr/local/bin/kinlin-entrypoint"]
CMD ["java", "-jar", "/app/app.jar"]
