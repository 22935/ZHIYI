FROM alpine:3.20

RUN apk add --no-cache socat \
    && addgroup -g 10005 -S kinlin \
    && adduser -S -D -H -u 10005 -G kinlin kinlin

USER 10005:10005
ENTRYPOINT ["socat"]
