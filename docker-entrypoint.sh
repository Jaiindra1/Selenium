#!/bin/sh
set -eu

# Render attaches persistent disks after the image is built, so repair the
# mount ownership at container startup before running the app unprivileged.
mkdir -p /var/data/reports
chown -R node:node /var/data

exec runuser -u node -- "$@"
