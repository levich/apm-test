# Third-party notices

Original application code is licensed under MIT. Dependencies retain their own licenses; the application license does not replace them.

| Component | Version/lock | License/source |
|---|---|---|
| Tabler Core | 1.6.0 | MIT, `src/apm/static/vendor/TABLER-LICENSE` |
| Tabler Icons | 3.34.1 | MIT, `src/apm/static/vendor/ICONS-LICENSE` |
| HTMX | 2.0.11 | BSD-2-Clause, `src/apm/static/vendor/HTMX-LICENSE` |
| Swagger UI | 5.30.1 | Apache-2.0, `src/apm/static/vendor/SWAGGER-LICENSE` |
| lua-cs-bouncer | 1.0.19 | MIT, `src/apm/integrations/crowdsec/LICENSE` |
| lua-resty-http | 0.17.1 | BSD-2-Clause, `src/apm/integrations/resty-http/LICENSE` |
| Angie OSS | 1.12.4 | BSD-2-Clause; official image/source retains upstream notices |
| Angie PRO | external | Commercial; not distributed in this repository |
| Certbot | `uv.lock` | Apache-2.0; installed as a dependency |
| GoAccess | optional 1.12 image | MIT; upstream image retains its notices |
| Python and Python dependencies | `uv.lock` | See installed package metadata; exact distributions are locked |
| Extended image modules/OpenSSL | `build/sources.lock.json` | Each upstream source license; Dockerfile collects upstream license files |
| s6-overlay | 3.2.0.2 | Upstream project and bundled component licenses |

Frontend and Lua source provenance and SHA256 are stored beside their vendored files. Build inputs are not copied from NPMPlus; NPMPlus is used as a functionality reference. Redistribution of optional images must include the notices required by their own dependencies. Release SBOM and full container dependency audit remain release tasks.
