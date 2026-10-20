# syntax=docker/dockerfile:1.7
ARG BASE_IMAGE=apm-angie:dev
FROM python:3.13.15-slim-trixie@sha256:7c61056e61ac89e852de05f3dc6fa51a6dd2181797bceed46aa725dd7cb2cd3b AS compile
RUN apt-get update && apt-get install -y --no-install-recommends build-essential perl pkg-config git cmake \
    libpcre2-dev zlib1g-dev libbrotli-dev libzstd-dev libmaxminddb-dev libluajit-5.1-dev \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /build
COPY build/sources.lock.json build/sources.lock.json
COPY scripts/fetch_sources.py scripts/fetch_sources.py
RUN python scripts/fetch_sources.py /sources
# ngx_brotli submodules remain pinned by the locked parent Git tree.
RUN cd /sources/brotli && git init && git remote add origin https://github.com/google/ngx_brotli.git \
    && git fetch --depth 1 origin "$(python -c 'import json;print(json.load(open("/build/build/sources.lock.json"))["brotli"]["revision"])')" \
    && git reset --hard FETCH_HEAD && git submodule update --init --recursive --depth 1 \
    && cmake -S deps/brotli -B deps/brotli/out -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF \
    && cmake --build deps/brotli/out --parallel 4
ENV LUAJIT_INC=/usr/include/luajit-2.1 LUAJIT_LIB=/usr/lib
RUN cd /sources/openssl-ech && ./config --prefix=/opt/openssl-ech --openssldir=/etc/ssl \
    no-shared zlib enable-brotli enable-zstd && make -j4 && make install_sw
RUN cd /sources/angie && ./configure --prefix=/etc/angie --sbin-path=/usr/sbin/angie \
    --with-compat --with-threads --with-http_ssl_module --with-http_v2_module --with-http_v3_module \
    --with-http_realip_module --with-http_auth_request_module --with-http_gzip_static_module \
    --with-stream --with-stream_ssl_module --with-stream_ssl_preread_module --with-stream_realip_module \
    --with-cc-opt='-I/opt/openssl-ech/include' --with-ld-opt='-L/opt/openssl-ech/lib64 -L/opt/openssl-ech/lib' \
    --add-dynamic-module=/sources/ndk --add-dynamic-module=/sources/lua --add-dynamic-module=/sources/stream-lua \
    --add-dynamic-module=/sources/headers-more --add-dynamic-module=/sources/brotli --add-dynamic-module=/sources/zstd \
    --add-dynamic-module=/sources/geoip2 --add-dynamic-module=/sources/fancyindex \
    && make -j4 && mkdir -p /out/modules /out/licenses \
    && cp objs/angie /out/ && cp objs/*.so /out/modules/ \
    && find /sources -maxdepth 2 -iname '*license*' -type f -exec cp --parents '{}' /out/licenses/ ';'
FROM ${BASE_IMAGE}
USER 0:10001
RUN apt-get update && apt-get install -y --no-install-recommends libluajit-5.1-2 libmaxminddb0 libzstd1 libbrotli1 \
    && rm -rf /var/lib/apt/lists/* /usr/lib/angie/modules/* /etc/angie/modules/*
COPY --from=compile /out/angie /usr/sbin/angie
COPY --from=compile /out/modules/ /usr/lib/angie/modules/
COPY --from=compile /out/licenses/ /usr/share/apm/licenses/
COPY --from=compile /opt/openssl-ech /opt/openssl-ech
