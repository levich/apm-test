# Static sites / PHP

Static sites and PHP through existing FPM. Create a directory under APM_DATA_DIR/sites, deploy files and configure domains/root_id. The form neither uploads files nor starts FPM. Administrator-managed.

## Settings

### `name`

<!-- setting:name -->
A name for finding the site in the panel, for example Company website. Requests are matched by Domain names. This name does not set the directory containing the site's files.

Format: `string`. Default: `required`. Constraints: minLength=1; maxLength=128.

Example: `"test"`.

### `enabled`

<!-- setting:enabled -->
Include this site in Angie's configuration after saving and a successful apply. Disabling removes the site's configuration but keeps its settings and files; it does not stop a separate PHP-FPM service.

Format: `boolean`. Default: `true`.

Example: `true`.

### `domains`

<!-- setting:domains -->
Host names served by this site, one per line, for example www.example.com. Enter names without a protocol, port or path. Configure DNS separately to point to Angie. All names share the same site directory and certificate.

Format: `array`. Default: `required`. Constraints: minItems=1.

Example: `["app.example.com"]`.

### `root_id`

<!-- setting:root_id -->
The site's subdirectory under APM_DATA_DIR/sites, not a full path. For example, company uses /data/sites/company with the default data directory. Use 1–80 Latin letters, digits, underscores or hyphens. Place or mount the files there so Angie can read them. Saving this form does not upload files. Angie looks for index.html, then index.php.

Format: `string`. Default: `required`.

Example: `"company"`.

### `certificate_id`

<!-- setting:certificate_id -->
Select a certificate covering all of this site's domain names. Request or upload it on the Certificates page first. An empty selection serves HTTP only. A ready certificate adds HTTPS without an automatic redirect from HTTP. If the selected certificate is not ready, this site returns HTTP 503 until the certificate is ready and the configuration is successfully applied.

Format: `string / null`. Default: `null`.

Example: `"<resource-id>"`.

### `php_upstream`

<!-- setting:php_upstream -->
The FastCGI address of an existing PHP-FPM service, for example php-fpm:9000 or 192.0.2.10:9000, without http:// or a path. Angie and FPM must be able to reach each other and see the scripts at the same absolute path, for example /data/sites/company/index.php. This setting does not start a PHP container. Leave empty only for static sites: PHP files will not execute and may be served as source text.

Format: `string / null`. Default: `null`.

Example: `"php-fpm:9000"`.

### `directory_index`

<!-- setting:directory_index -->
Show a directory's files when no index.html or index.php is found. Disabled by default; a directory without an index normally returns 403. Enable for a public file catalog only if its contents may be listed. This does not add authentication or protect individual files.

Format: `boolean`. Default: `false`.

Example: `false`.

### `fancyindex`

<!-- setting:fancyindex -->
Enable formatted directory listings using Angie's fancyindex module when no index page is found. The module must be available in the Angie build; this switch does not install it. If the module is missing, applying the configuration fails and the previous working configuration stays active. Listed file names are visible to visitors.

Format: `boolean`. Default: `false`.

Example: `false`.

## Workflow example

Create a clearly named resource, complete required settings and save. Confirm apply completion in Operations. If angie -t fails, fix settings or dependencies; the previous working configuration remains. Observers read data; administrators delete resources no longer referenced.

[Operations](operations.md) · [System settings](environment.md) · [Contents](index.md)
