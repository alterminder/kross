# Database image: postgres:16-alpine without the vulnerable Go gosu.
#
# The official image ships gosu v1.19 (a Go binary; Critical/High stdlib
# advisories) at /usr/local/bin/gosu, plus a /usr/local/bin/su-exec symlink to
# the SAME binary. Replacing those paths with same-path symlinks to Alpine's C
# su-exec keeps the lower-layer Go artifact visible to image scanners (verified:
# Trivy still reported Go at usr/local/bin/gosu), so BOTH paths are removed for
# good and nothing is recreated at them. The entrypoint's `exec gosu postgres`
# call sites (docker-entrypoint.sh and docker-ensure-initdb.sh; the
# docker-enforce-initdb.sh alias points at the latter) are patched to the 67 KB
# C /sbin/su-exec from Alpine, which has the same call shape.
#
# Postgres major stays 16: existing data volumes are untouched.
FROM postgres:16-alpine
RUN apk add --no-cache su-exec \
    && apk upgrade --no-cache \
    && sed -i 's|exec gosu postgres|exec /sbin/su-exec postgres|g' \
        /usr/local/bin/docker-entrypoint.sh /usr/local/bin/docker-ensure-initdb.sh \
    && rm -f /usr/local/bin/gosu /usr/local/bin/su-exec \
    && if grep -n 'gosu' /usr/local/bin/docker-entrypoint.sh /usr/local/bin/docker-ensure-initdb.sh; then \
        echo 'a gosu reference survived the patch' >&2; exit 1; \
    fi
