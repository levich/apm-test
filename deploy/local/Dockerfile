# syntax=docker/dockerfile:1.7
# Optional local source base when docker.angie.software is unavailable.
# Put the official Angie archive in build/cache/angie.tar.gz first.
FROM python:3.13.15-slim-trixie@sha256:7c61056e61ac89e852de05f3dc6fa51a6dd2181797bceed46aa725dd7cb2cd3b AS compile
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpcre2-dev zlib1g-dev libssl-dev \
    && rm -rf /var/lib/apt/lists/*
COPY build/sources.lock.json /sources.lock.json
COPY build/cache/angie.tar.gz /tmp/angie.tar.gz
RUN python -c 'import hashlib,json; expected=json.load(open("/sources.lock.json"))["angie"]["sha256"]; assert hashlib.sha256(open("/tmp/angie.tar.gz","rb").read()).hexdigest()==expected, "Angie source checksum mismatch"' \
    && mkdir /source && tar -xzf /tmp/angie.tar.gz -C /source --strip-components=1
WORKDIR /source
RUN ./configure --prefix=/etc/angie --sbin-path=/usr/sbin/angie \
    --with-compat --with-threads --with-http_ssl_module --with-http_v2_module --with-http_v3_module \
    --with-http_realip_module --with-http_auth_request_module --with-http_gzip_static_module \
    --with-stream --with-stream_ssl_module --with-stream_ssl_preread_module --with-stream_realip_module \
    && make -j4

FROM python:3.13.15-slim-trixie@sha256:7c61056e61ac89e852de05f3dc6fa51a6dd2181797bceed46aa725dd7cb2cd3b
RUN apt-get update && apt-get install -y --no-install-recommends libpcre2-8-0 zlib1g libssl3t64 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system angie && useradd --system --gid angie --no-create-home angie
COPY --from=compile /source/objs/angie /usr/sbin/angie
COPY --from=compile /source/conf/ /etc/angie/
COPY --from=compile /source/LICENSE /usr/share/doc/angie/LICENSE
