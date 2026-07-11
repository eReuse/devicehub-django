#!/bin/sh

# SPDX-License-Identifier: AGPL-3.0-or-later

set -e
set -u
# DEBUG
set -x

main() {
        echo 'WARNING! This is going to delete all data to restore it with a previous one'
        sleep 10
       docker compose exec --user devicehub-django devicehub-django \
               sh -c './manage.py reset_db --close-sessions --noinput'
        docker compose exec --user devicehub-django devicehub-django \
               sh -c './manage.py dbrestore --noinput && ./manage.py evidence_restore'
}

main "${@}"

# written in emacs
# -*- mode: shell-script; -*-
