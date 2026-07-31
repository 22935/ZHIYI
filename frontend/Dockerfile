ARG NODE_IMAGE=public.ecr.aws/docker/library/node:24.18.0-alpine3.23@sha256:595398b0081eacda8e1c4c5b97b76cd1020e4d58a8ebcb4843b9bca1e79e7436
ARG NGINX_IMAGE=public.ecr.aws/docker/library/nginx:1.31.1-alpine@sha256:8b1e78743a03dbb2c95171cc58639fef29abc8816598e27fb910ed2e621e589a

FROM ${NODE_IMAGE} AS build

WORKDIR /app

COPY package*.json ./
RUN --mount=type=cache,target=/root/.npm npm ci

COPY . .
RUN npm run build

FROM ${NGINX_IMAGE}

ARG KINLIN_VERSION=dev
ARG KINLIN_REVISION=unknown
ARG KINLIN_CREATED=unknown
LABEL org.opencontainers.image.title="Kinlin AI Frontend" \
      org.opencontainers.image.version="$KINLIN_VERSION" \
      org.opencontainers.image.revision="$KINLIN_REVISION" \
      org.opencontainers.image.created="$KINLIN_CREATED"

RUN addgroup -g 10003 -S kinlin \
    && adduser -S -D -H -u 10003 -G kinlin kinlin \
    && chown -R 10003:10003 /usr/share/nginx/html /etc/nginx/conf.d

COPY --from=build --chown=10003:10003 /app/dist /usr/share/nginx/html

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY nginx-main.conf /etc/nginx/nginx.conf

WORKDIR /usr/share/nginx/html
EXPOSE 8080
USER 10003:10003
CMD ["nginx", "-g", "daemon off;"]

