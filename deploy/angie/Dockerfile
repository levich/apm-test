# syntax=docker/dockerfile:1.7
ARG APP_IMAGE=apm-manager:dev
ARG ANGIE_IMAGE=docker.angie.software/angie:1.12.4-debian
FROM ${APP_IMAGE} AS application
FROM ${ANGIE_IMAGE}
ARG TARGETARCH
ARG S6_OVERLAY_VERSION=3.2.0.2
USER root
RUN apt-get update && apt-get install -y --no-install-recommends curl xz-utils ca-certificates openssl libffi8 lua-cjson lua-resty-core \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 apm
RUN set -eu; case "$TARGETARCH" in amd64) s6_arch=x86_64; s6_hash=59289456ab1761e277bd456a95e737c06b03ede99158beb24f12b165a904f478;; arm64) s6_arch=aarch64; s6_hash=8b22a2eaca4bf0b27a43d36e65c89d2701738f628d1abd0cea5569619f66f785;; *) exit 1;; esac; \
    for archive in s6-overlay-noarch.tar.xz s6-overlay-${s6_arch}.tar.xz; do \
      curl -fsSL --retry 3 "https://github.com/just-containers/s6-overlay/releases/download/v${S6_OVERLAY_VERSION}/${archive}" -o "/tmp/${archive}"; \
      if [ "$archive" = s6-overlay-noarch.tar.xz ]; then expected=6dbcde158a3e78b9bb141d7bcb5ccb421e563523babbe2c64470e76f4fd02dae; else expected="$s6_hash"; fi; \
      printf "%s  %s\n" "$expected" "/tmp/$archive" | sha256sum -c -; tar -C / -Jxpf "/tmp/${archive}"; \
    done; rm -f /tmp/s6-overlay-*
COPY --from=application /usr/local /usr/local
COPY --from=application /opt/apm /opt/apm
RUN mkdir -p /opt/apm/lua && cp /opt/apm/src/apm/integrations/access.lua /opt/apm/lua/access.lua \
    && cp /opt/apm/src/apm/integrations/apm.lua /opt/apm/lua/apm.lua \
    && cp -r /opt/apm/src/apm/integrations/crowdsec/lib/* /opt/apm/lua/ \
    && cp -r /opt/apm/src/apm/integrations/resty-http/lib/* /opt/apm/lua/
COPY deploy/angie/rootfs/ /
RUN chmod +x /etc/cont-init.d/10-apm /etc/services.d/*/run
ENV PATH=/opt/apm/.venv/bin:$PATH APM_DATA_DIR=/data PYTHONUNBUFFERED=1 S6_BEHAVIOUR_IF_STAGE2_FAILS=2
USER 0:10001
ENTRYPOINT ["/init"]
CMD []
