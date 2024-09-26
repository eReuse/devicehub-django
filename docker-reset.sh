#!/bin/sh

# Copyright (c) 2024 Pedro <copyright@cas.cat>
# SPDX-License-Identifier: AGPL-3.0-or-later

set -e
set -u
# DEBUG
set -x

main() {
        if [ "${DETACH:-}" ]; then
                detach_arg='-d'
        fi
        # remove old database
        sudo rm -vf db/*
        docker compose down
        docker compose build
        docker compose up ${detach_arg:-}
}

main "${@}"

# written in emacs
# -*- mode: shell-script; -*-
