# Configuration files

User resources compile into separate files in revisions/ID/http and stream. Names come from the Name field; Cyrillic is transliterated, unsafe characters replaced, and collisions receive stable ID suffixes. Examples: test.proxy.conf, test.redirect.conf, test.stream.conf, test.site.conf, test.upstream.conf. A shared upstream can have separate HTTP and stream variants.

System entry points angie.conf/http.conf/stream.conf and standard PEM paths are retained. Includes are absolute and belong to one immutable revision. Renaming creates a new file in a new revision, preserving the old one. Do not edit revisions/current manually: applying regenerates them and the hash manifest enforces immutability.

Dependencies and HTTP zones load before routes. In existing mode shared HTTP policies affect only APM virtual hosts. Failed validation/activation restores the previous revision. [Operations](operations.md)
