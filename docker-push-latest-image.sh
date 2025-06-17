#!/bin/sh

# SPDX-License-Identifier: AGPL-3.0-or-later

set -e
set -u
# DEBUG
set -x

_check_tag() {
        if [ ! "${tag}" = "${DEVICEHUB_DOCKER_TAG}" ]; then
                set +x
                printf "ERROR: ABORTED: mismatch between:\n"
                printf "%-20s %-25s %s\n" "var" "value" "location"
                printf "%-20s %-25s %s\n" "tag" "issue_261__dpp_v3" "retrieved from git branch"
                printf "%-20s %-25s %s\n" "IDHUB_DOCKER_TAG" "issue_261__dpp_v3AA" "retrieved from .env env vars file"
                set -x
                exit 1
        fi
}

_proc() {
        name="${1}"
        #registry_url="farga.pangea.org/ereuse/${name}:${tag}"

        . ./.env
        _check_tag

        registry_url="ghcr.io/ereuse/${name}:${tag}"
        docker compose build ${name} 
        docker push "${registry_url}"
}

main() {
        branch="$(git branch --show-current)"
        tag="${tag:-$branch}"

        # TODO hardcoded
        main_branch="main"

        if [ "${tag}" = "${main_branch}" ]; then
                tag='stable'
        fi

        _proc devicehub-django
}

main "${@:-}"

# written in emacs
# -*- mode: shell-script; -*-

