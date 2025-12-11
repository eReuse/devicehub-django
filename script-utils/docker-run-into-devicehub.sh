#!/bin/sh

# SPDX-License-Identifier: AGPL-3.0-or-later

set -e
set -u
# DEBUG
set -x

main() {
       docker compose run --rm  --entrypoint bash devicehub-django
}

main "${@}"

# written in emacs
# -*- mode: shell-script; -*-
