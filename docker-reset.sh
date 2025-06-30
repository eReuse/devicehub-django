#!/bin/sh

# Copyright (c) 2024 Pedro <copyright@cas.cat>
# SPDX-License-Identifier: AGPL-3.0-or-later

set -e
set -u
# DEBUG
set -x

prompt_env_var() {
        # Prompt for an env var if unset or empty, with a fallback default.
        # Usage: prompt_env_var VAR_NAME DEFAULT_VALUE

        var_name="${1}"
        default="${2}"
        info="${3:-}"

        # dereference: get current value of the variable named in $var_name
        eval "current=\${${var_name}:-}"

        if [ -z "${current}" ]; then
                if [ "${info}" ]; then
                        info="\n[${var_name}] info:\n${info}\n"
                fi
                # show the default in the prompt
                printf "${info}\n+ Enter value for %s (default is \"%s\"): " "${var_name}" "${default}"
                # read into a temporary
                read answer
                # if they just hit enter, use default
                if [ -z "${answer}" ]; then
                        answer=${default}
                fi
                # export the result back into the named variable
                export "${var_name}"="${answer}"
        fi
}

add_env_var() {
        # add env var to template
        var_name="${1}"
        template_env_vars="${template_env_vars} \${${var_name}}"
}

use_env_var() {
        # prompt env var for completion, and add env var to template

        var_name="${1}"
        default="${2}"
        info="${3:-}"
        prompt_env_var "${var_name}" "${default}" "${info}"
        add_env_var "${var_name}"
}

docker_wizard() {
        set +x
        printf "\nDetected .env file is missing, so let's initialize the config (if you
want to see again, remove .env file)\n\nPress enter to continue... "
        read enter

        template_env_vars=''
        #TODO: unused in .env.example
        use_env_var DEVICEHUB_DOMAIN_REQUEST "devicehub.example.org"

        use_env_var DEVICEHUB_TIME_ZONE_REQUEST "Europe/Madrid"
        use_env_var DEVICEHUB_REMOVE_DATA_REQUEST "false" 'Use false for production and true for development'

        docker_profiles_info="Use
  rproxy              if you want to add rproxy (nginx) to docker compose
  rproxy,letsencrypt  for managing a real HTTPS cert
by default does not use rproxy nor letsencrypt"
        use_env_var COMPOSE_PROFILES_REQUEST "" "${docker_profiles_info}"

        use_env_var DEVICEHUB_DB_TYPE_REQUEST "postgres" "Use
  postgres  production ready solution
  sqlite    minimalist solution"
        if echo "${DEVICEHUB_DB_TYPE_REQUEST}" | grep -q 'postgres' ; then
                echo "postgres docker profile detected, adding to COMPOSE_PROFILES env var"
                COMPOSE_PROFILES_REQUEST="${COMPOSE_PROFILES_REQUEST},postgres"
        fi

        #Shouldnt it be the other way? always build to latest on dev, but stable image on production
        use_env_var DOCKER_ALWAYS_BUILD_REQUEST 'false' 'Use true for production and false for development'

        set -x

        if echo "${COMPOSE_PROFILES_REQUEST}" | grep -q 'letsencrypt' ; then
                export DEVICEHUB_FAKE_HTTP_CERT_REQUEST=false
        else
                export DEVICEHUB_FAKE_HTTP_CERT_REQUEST=true
        fi
        add_env_var DEVICEHUB_FAKE_HTTP_CERT_REQUEST

        # adapt docker user to your runtime needs -> src https://denibertovic.com/posts/handling-permissions-with-docker-volumes/
        #   via https://github.com/moby/moby/issues/22258#issuecomment-293664282
        #   related https://github.com/moby/moby/issues/2259
        export DEVICEHUB_LOCAL_USER_ID_REQUEST="$(id -u "${USER}")"
        add_env_var DEVICEHUB_LOCAL_USER_ID_REQUEST

        # if user is root, place it in /opt
        if [ "${DEVICEHUB_LOCAL_USER_ID_REQUEST}" = 0 ]; then
                export DEVICEHUB_ROOT_DIR_REQUEST='/opt'
        else
                export DEVICEHUB_ROOT_DIR_REQUEST="${HOME}"
        fi
        add_env_var DEVICEHUB_ROOT_DIR_REQUEST

        # src https://stackoverflow.com/questions/41298963/is-there-a-function-for-generating-settings-secret-key-in-django
        export DEVICEHUB_SECRET_KEY_REQUEST="$(python3 -c 'import secrets; print(secrets.token_hex(100))')"
        add_env_var DEVICEHUB_SECRET_KEY_REQUEST


        envsubst "${template_env_vars}" < .env.example > .env

        # TODO volume map is incorrect (TODO touch file)
        if echo "${COMPOSE_PROFILES_REQUEST}" | grep -q 'letsencrypt' ; then
                echo "letsencrypt docker profile detected, you should run ./docker/certbot__generate-first-cert.sh before continuing"
                ./docker/certbot__generate-first-cert.sh
        fi
}


main() {
        cd "$(dirname "${0}")"

        if [ "${DETACH:-}" ]; then
                detach_arg='-d'
        fi

        if [ ! -f .env ]; then
                docker_wizard
        fi

        # load vars
        . ./.env

        if [ "${IDHUB_ENABLED:-}" = 'true' ]; then
                export COMPOSE_PROFILES='idhub'
        fi


        if [ "${DEVICEHUB_REMOVE_DATA}" = 'true' ];then
                #remove postgres volume
                docker volume rm DEVICEHUB_POSTGRES_DATA > /dev/null 2>&1 || true
                rm -vfr ./db/*
                docker compose down -v
        else
                docker compose down
        fi


        if [ "${DOCKER_ALWAYS_BUILD:-}" = 'true' ]; then
                docker compose build
        fi

        docker compose up ${detach_arg:-}
}

main "${@}"

# written in emacs
# -*- mode: shell-script; -*-
