#!/bin/sh

set -e
set -u
# DEBUG
set -x

check_app_is_there() {
        if [ ! -f "./manage.py" ]; then
                usage
        fi
}

deploy() {
        # detect if existing deployment (TODO only works with sqlite)
        if [ -f "${program_dir}/db/db.sqlite3" ]; then
                echo "INFO: detected EXISTING deployment"
                ./manage.py migrate
        else
                # move the migrate thing in docker entrypoint
                #   inspired by https://medium.com/analytics-vidhya/django-with-docker-and-docker-compose-python-part-2-8415976470cc
                echo "INFO detected NEW deployment"
                ./manage.py migrate
                ./manage.py add_user user@example.org 1234
        fi
}

runserver() {
        PORT="${PORT:-8000}"
        if [ "${DEBUG:-}" = "true" ]; then
                ./manage.py runserver 0.0.0.0:${PORT}
        else
                # TODO
                #./manage.py collectstatic
                true
                if [ "${EXPERIMENTAL:-}" = "true" ]; then
                        # TODO
                        # reloading on source code changing is a debugging future, maybe better then use debug
                        #   src https://stackoverflow.com/questions/12773763/gunicorn-autoreload-on-source-change/24893069#24893069
                        # gunicorn with 1 worker, with more than 1 worker this is not expected to work
                        #gunicorn --access-logfile - --error-logfile - -b :${PORT} trustchain_idhub.wsgi:application
                        true
                else
                        ./manage.py runserver 0.0.0.0:${PORT}
                fi
        fi
}

main() {
        program_dir='/opt/devicehub-django'
        cd "${program_dir}"
        deploy
        runserver
}

main "${@}"
