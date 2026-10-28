# Configuration files

The Configuration page in the system menu is available to administrators. It lists the active revision's files and displays their contents read-only. Select a file; Refresh reads the current revision again after an apply or rollback. Unsaved changes and inactive revisions are excluded. If the revision changes while browsing, refresh the list.

Generated directives use four-space indentation, one directive per line, and short comments identifying each file and system block. Administrator snippets retain their original text. Formatting takes effect in new revisions after applying; older immutable files are preserved.

The viewer excludes PEM, htpasswd and the CrowdSec secrets file. Administrator snippets can contain sensitive values, so access is restricted to administrators. In existing mode it shows only APM-generated files, excluding the existing server's main configuration.

User resources compile into separate files in revisions/ID/http and stream. Names come from the Name field; Cyrillic is transliterated, unsafe characters replaced, and collisions receive stable ID suffixes. Examples: test.proxy.conf, test.redirect.conf, test.stream.conf, test.site.conf, test.upstream.conf. A shared upstream can have separate HTTP and stream variants.

System entry points angie.conf/http.conf/stream.conf and standard PEM paths are retained. Includes are absolute and belong to one immutable revision. Renaming creates a new file in a new revision, preserving the old one. Do not edit revisions/current manually: applying regenerates them and the hash manifest enforces immutability.

Dependencies and HTTP zones load before routes. In existing mode shared HTTP policies affect only APM virtual hosts. Failed validation/activation restores the previous revision. [Operations](operations.md)
