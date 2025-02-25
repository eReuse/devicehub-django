#!/bin/sh

# Copyright (c) 2024 Pedro <copyright@cas.cat>
# SPDX-License-Identifier: AGPL-3.0-or-later

set -e
set -u
# DEBUG
set -x

main() {
        cd "$(dirname "${0}")"

        if [ "${DETACH:-}" ]; then
                detach_arg='-d'
        fi

        if [ ! -f .env ]; then
                cp -v .env.example .env
                echo "WARNING: .env was not there, .env.example was copied, this only happens once"
        fi

        # load vars
        . ./.env

        if [ "${IDHUB_ENABLED:-}" = 'true' ]; then
                export COMPOSE_PROFILES='idhub'
        fi
        # remove old database
        rm -vfr ./db/*
        # deactivate configured flag
        rm -vfr ./already_configured
        docker compose down -v
        if [ "${DEV_DOCKER_ALWAYS_BUILD:-}" = 'true' ]; then
                docker compose pull --ignore-buildable
                docker compose build
        else
                docker compose pull
        fi
        docker compose up ${detach_arg:-}
}

main "${@}"

# written in emacs
# -*- mode: shell-script; -*-
