#!/bin/sh

# SPDX-License-Identifier: AGPL-3.0-or-later

set -e
set -u
# DEBUG
set -x

main() {
        cd "$(dirname "${0}")"
        browser="${browser:-firefox}"
        project="${project:-firefox}"
        headed="${headed:---headed}"
        npx playwright test --project "${project}" "${headed}"
}

main "${@}"

# written in emacs
# -*- mode: shell-script; -*-
