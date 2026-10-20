#!/bin/sh
set -eu
umask 0027
while :; do
  if [ -s /logs/analytics.log ]; then
    goaccess /logs/analytics.log --no-global-config --log-format=COMBINED \
      --date-format='%d/%b/%Y' --time-format='%T' --no-progress --no-query-string \
      --output=/reports/.goaccess-next.html && mv /reports/.goaccess-next.html /reports/goaccess.html
  fi
  sleep 60
done
