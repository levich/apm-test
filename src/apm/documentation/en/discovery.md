# Docker discovery

Enable APM_DISCOVERY_ENABLED, allowlist networks/domains, then add container labels. ACME also requires APM_DISCOVERY_ACME_TERMS_AGREED and an email. Keep secrets out of labels. Edit discovered resources through labels, not the UI; manual resources are not overwritten. Removing a container disables its route at the next reconciliation.

## `apm.enable`

<!-- label:apm.enable -->
Enable discovery for this container: string true. Disabled by default.

## `apm.host`

<!-- label:apm.host -->
Required domain, e.g. app.example.com, inside APM_DISCOVERY_DOMAINS.

## `apm.network`

<!-- label:apm.network -->
Required network from APM_DISCOVERY_NETWORKS, e.g. apps. Requires container IPv4.

## `apm.port`

<!-- label:apm.port -->
Required internal application port, 1–65535; discovery does not guess from EXPOSE.

## `apm.scheme`

<!-- label:apm.scheme -->
http, https, grpc or grpcs; default http. This is the backend protocol.

## `apm.tls`

<!-- label:apm.tls -->
off, http or dns; default off. http/dns require ACME terms; wildcards require dns.

## `apm.dns-profile`

<!-- label:apm.dns-profile -->
Name of a pre-created DNS profile for dns; it must enable discovery_allowed.

## `apm.weight`

<!-- label:apm.weight -->
Group member weight, 1–1000, default 1. Compatible containers sharing a domain form an upstream.

```yaml
labels:
  apm.enable: "true"
  apm.host: app.example.com
  apm.network: apps
  apm.port: "8080"
  apm.scheme: http
  apm.tls: dns
  apm.dns-profile: production-dns
```

Remote Docker requires a VPN/read-only gateway and a separate Angie route to container IPs. Reachability from manager does not prove reachability from Angie. For failures check allowlists, IPv4, port and label compatibility.
