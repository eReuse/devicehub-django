#!/bin/sh

set -e
set -u
# DEBUG
set -x

# TODO there is a conflict between two shared vars
#   1. from the original docker compose devicehub-teal
#   2. from the new docker compose that integrates all dpp services
wait_for_dpp_shared() {
        OPERATOR_TOKEN_FILE='operator-token.txt'
        echo "Waiting for file in shared: ${OPERATOR_TOKEN_FILE}"
        set +x
        while true; do
                if [ -f "/shared/${OPERATOR_TOKEN_FILE}" ] && \
                        [ -f "/shared/create_user_operator_finished" ]; then
                        sleep 5
                        echo "Files ready to process."
                        set -x
                        break
                else
                        sleep 5
                        # DEBUG
                        #echo "Waiting for file in shared: ${OPERATOR_TOKEN_FILE}"
                fi
        done
}

# 3. Generate an environment .env file.
# TODO cargar via shared
gen_env_vars() {
        INIT_ORG="${DEVICEHUB_INIT_ORG:-example-org}"
        INIT_USER="${DEVICEHUB_INIT_ADMIN_EMAIL:-user@example.org}"
        INIT_PASSWD="${DEVICEHUB_INIT_ADMIN_PASSWORD:-1234}"
        IS_ADMIN='True'
        DEMO_PREDEFINED_TOKEN="${DEVICEHUB_DEMO_PREDEFINED_TOKEN:-}"

        detect_app_version

        if [ "${DEVICEHUB_DEBUG:-}" = 'true' ]; then
                ${_RUN} ./manage.py print_settings
        fi

        # specific dpp env vars
        if [ "${DEVICEHUB_DPP:-}" = 'true' ]; then
                # fill env vars in this docker entrypoint
                wait_for_dpp_shared
                export DEVICEHUB_API_DLT='http://api_connector:3010'
                export DEVICEHUB_API_DLT_TOKEN="$(cat "/shared/${OPERATOR_TOKEN_FILE}")"
                export DEVICEHUB_API_RESOLVER='http://id_index_api:3012'
                # TODO hardcoded
                export DEVICEHUB_ID_FEDERATED='DH1'
        fi
}

handle_federated_id() {

        # devicehub host and id federated checker

        # //getAll queries are not accepted by this service, so we remove them
        EXPECTED_ID_FEDERATED="$(curl -s "${API_RESOLVER%/}/getAll" \
                | jq -r '.url | to_entries | .[] | select(.value == "'"${DEVICEHUB_HOST}"'") | .key' \
                | head -n 1)"

        # if is a new DEVICEHUB_HOST, then register it
        if [ -z "${EXPECTED_ID_FEDERATED}" ]; then
                # TODO better docker compose run command
                cmd="docker compose run --entrypoint= devicehub flask dlt_insert_members ${DEVICEHUB_HOST}"
                big_error "No FEDERATED ID maybe you should run \`${cmd}\`"
        fi

        # if not new DEVICEHUB_HOST, then check consistency

        # if there is already an ID in the DLT, it should match with my internal ID
        if [ ! "${EXPECTED_ID_FEDERATED}" = "${ID_FEDERATED}" ]; then

                big_error "ID_FEDERATED should be ${EXPECTED_ID_FEDERATED} instead of ${ID_FEDERATED}"
        fi

        # not needed, but reserved
        # EXPECTED_DEVICEHUB_HOST="$(curl -s "${API_RESOLVER%/}/getAll" \
        #         | jq -r '.url | to_entries | .[] | select(.key == "'"${ID_FEDERATED}"'") | .value' \
        #         | head -n 1)"
        # if [ ! "${EXPECTED_DEVICEHUB_HOST}" = "${DEVICEHUB_HOST}" ]; then
        #         big_error "ERROR: DEVICEHUB_HOST should be ${EXPECTED_DEVICEHUB_HOST} instead of ${DEVICEHUB_HOST}"
        # fi

}

config_dpp_part1() {
        # 12. Add a new server to the 'api resolver'
        if [ "${ID_SERVICE:-}" ]; then
                handle_federated_id
        else
                # TODO when this runs more than one time per service, this is a problem, but for the docker-reset.sh workflow, that's fine
                # TODO put this in already_configured
                # TODO hardcoded http proto and port
                ${_RUN} ./manage.py dlt_insert_members "http://${DEVICEHUB_HOST}:8000"
        fi

        # 13. Do a rsync api resolve
        ${_RUN} ./manage.py dlt_rsync_members

        # 14. Register a new user to the DLT
        DATASET_FILE='/tmp/dataset.json'
        cat > "${DATASET_FILE}" <<END
{
  "email": "${INIT_USER}",
  "password": "${INIT_PASSWD}",
  "api_token": "${API_DLT_TOKEN}"
}
END
        ${_RUN} ./manage.py dlt_register_user "${DATASET_FILE}"
}

# wait until idhub api is prepared to received requests
wait_idhub() {
        echo "Start waiting idhub API"
        set +x
        while true; do
                result="$(curl -s "${url}" \
                               | jq -r .error 2>/dev/null \
                               || echo "Reported errors, idhub API is still not ready")"

                if [ "${result}" = "Invalid request method" ]; then
                        echo "IdHub is ready"
                        set -x
                        break
                        sleep 2
                else
                        # DEBUG
                        #echo "Waiting idhub API"
                        sleep 3
                fi
        done
}

demo__send_snapshot_to_idhub() {
        filepath="${1}"
        # hashlib.sha3_256 of PREDEFINED_TOKEN for idhub
        DEMO_IDHUB_PREDEFINED_TOKEN="${DEMO_IDHUB_PREDEFINED_TOKEN:-}"
        auth_header="Authorization: Bearer ${DEMO_IDHUB_PREDEFINED_TOKEN}"
        json_header='Content-Type: application/json'
        curl -s -X POST \
             -H "${json_header}" \
             -H "${auth_header}" \
             -d @"${filepath}" \
             "${url}" \
                | jq -r .data
}

run_demo() {
        if [ "${DEMO_IDHUB_DOMAIN:-}" ]; then
                DEMO_IDHUB_DOMAIN="${DEMO_IDHUB_DOMAIN:-}"
                # this demo only works with FQDN domain (with no ports)
                url="https://${DEMO_IDHUB_DOMAIN}/webhook/sign/"
                wait_idhub
                prevc_in='example/demo-snapshots-vc/snapshot_pre-verifiable-credential.json'
                vc_out='example/snapshots/snapshot_workbench-script_verifiable-credential.json'
                if demo__send_snapshot_to_idhub "${prevc_in}" > "${vc_out}"; then
                        echo 'Credential signed'
                else
                        echo 'ERROR: Credential not signed'
                fi
        fi
        ${_RUN} ./manage.py create_default_states "${INIT_ORG}"
        # create demo data to play with users for B2B B2C interactions
        ${_RUN} ./manage.py load_demo_data
        ${_RUN} /usr/bin/time ./manage.py up_snapshots example/snapshots/ "${INIT_USER}"
}

init_db() {
        echo "INFO: INIT DEVICEHUB DATABASE"

        # move the migrate thing in docker entrypoint
        #   inspired by https://medium.com/analytics-vidhya/django-with-docker-and-docker-compose-python-part-2-8415976470cc
        ${_RUN} ./manage.py migrate

        # non DL user (only for the inventory)
        ${_RUN} ./manage.py add_institution "${INIT_ORG}"
        # TODO: one error on add_user, and you don't add user anymore
        ${_RUN} ./manage.py add_user "${INIT_ORG}" "${INIT_USER}" "${INIT_PASSWD}" "${IS_ADMIN}" "${DEMO_PREDEFINED_TOKEN}"

        if [ "${DPP:-}" = 'true' ]; then
                # 12, 13, 14
                config_dpp_part1

                # cleanup other snapshots and copy dlt/dpp snapshots
                # TODO make this better
                rm example/snapshots/*
                cp example/dpp-snapshots/*.json example/snapshots/
        fi

        # # 15. Add inventory snapshots for user "${INIT_USER}".
        if [ "${DEVICEHUB_DEMO:-}" = 'true' ]; then
                run_demo
        fi
}

check_app_is_there() {
        if [ ! -f "./manage.py" ]; then
                usage
        fi
}

usage() {
                cat <<END
ERROR: I don't have access to app source code (particularly, ${APP_DIR}/manage.py), review docker volumes, users and permissions
END
                exit 1
}

detect_app_version() {
        if [ -d "${APP_DIR}/.git" ]; then
                export DEVICEHUB_COMMIT="$(${_RUN} git log --format="%H %ad" --date=iso -n 1)"
        else
                # TODO if software is packaged in setup.py and/or pyproject.toml we can get from there the version
                #   then we might want to distinguish prod version (stable version) vs development (commit/branch)
                export DEVICEHUB_COMMIT="version: unknown (reason: git undetected)"
        fi
}

manage_db() {
        if [ "${DEVICEHUB_DB_TYPE:-}" = "postgres" ]; then
                echo "INFO: WAITING DATABASE CONNECTIVITY"
                set +x
                #   https://github.com/docker-library/postgres/issues/146#issuecomment-213545864
                #   https://github.com/docker-library/postgres/issues/146#issuecomment-2905869196
                while ! pg_isready -h "${DEVICEHUB_POSTGRES_HOST}"; do
                        sleep 1
                done
                set -x
                echo "INFO: DATABASE CONNECTIVITY OK"
        fi

        if [ "${DEVICEHUB_REMOVE_DATA}" = "true" ]; then
                echo "INFO: REMOVE DEVICEHUB DATABASE (reason: DEVICEHUB_REMOVE_DATA is equal to true)"
                # https://django-extensions.readthedocs.io/en/latest/reset_db.html
                # https://github.com/django-cms/django-cms/issues/5921#issuecomment-343658455
                ${_RUN} ./manage.py reset_db --close-sessions --noinput
        else
                echo "INFO: PRESERVE DEVICEHUB DATABASE"
        fi

        # detect if is an existing deployment
        if ${_RUN} ./manage.py showmigrations --plan \
                        | grep -F -q '[X]  user.0001_initial'; then
                echo "INFO: detected EXISTING deployment"
                ${_RUN} ./manage.py migrate
        else
                echo "INFO detected NEW deployment"
                init_db
        fi
}

_detect_proper_user() {
        # src https://denibertovic.com/posts/handling-permissions-with-docker-volumes/
        #   via https://github.com/moby/moby/issues/22258#issuecomment-293664282
        #   related https://github.com/moby/moby/issues/2259

        # user of current dir
        USER_ID="$(stat -c "%u" .)"
        if [ "${USER_ID}" = "0" ]; then
                APP_USER="root"
        else
                APP_USER="${APP}"
                if ! id -u "${APP_USER}" >/dev/null 2>&1; then
                        useradd --shell /bin/bash -u ${USER_ID} -o -c "" -m ${APP_USER}
                fi
        fi
        printf "${APP_USER}" > /app_user
        _RUN="gosu ${APP_USER}"
}

_prepare() {
        APP=devicehub-django
        _detect_proper_user
        # docker create root owned volumes, it is our job to map it to
        #   the right user
        chown -R ${APP_USER}: "${DEVICEHUB_MEDIA_ROOT}"
        chown -R ${APP_USER}: "${DEVICEHUB_STATIC_ROOT}"
        chown -R ${APP_USER}: "${DEVICEHUB_EVIDENCES_DIR}"
        chown -R ${APP_USER}: "${DEVICEHUB_BACKUPS_DIR}"
        APP_DIR="/opt/${APP}"
        cd "${APP_DIR}"
}

runserver() {
        PORT="${DEVICEHUB_PORT:-8000}"

        # this check might be nice, but not on every execution
        #${_RUN} ./manage.py check --deploy

        if [ "${DEVICEHUB_DEBUG:-}" = "false" ]; then
                ${_RUN} ./manage.py collectstatic --noinput
                # reloading on source code changing is a debugging future, maybe better then use debug
                #   src https://stackoverflow.com/questions/12773763/gunicorn-autoreload-on-source-change/24893069#24893069
                gunicorn --access-logfile - --error-logfile - -b :${PORT} dhub.wsgi:application
        else
                ${_RUN} ./manage.py runserver 0.0.0.0:${PORT}
        fi
}

main() {
        _prepare

        check_app_is_there

        gen_env_vars

        manage_db

        runserver
}

main "${@}"
