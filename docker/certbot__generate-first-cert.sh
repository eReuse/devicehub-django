#!/bin/sh

set -e
set -u
# DEBUG
set -x

generate_certificate() {
        APP_HOST="${1}"
        certbot_args="certonly --standalone --agree-tos --register-unsafely-without-email -d ${APP_HOST}"
        docker run -it --rm --name certbot-init -p 80:80 -v "${certbot_vol}" certbot/certbot ${certbot_args}
}

main() {
        cd "$(dirname "${0}")"
        . ../.env

        # inspiration: https://docs.joinpeertube.org/install/docker
        certbot_dir=${DOCKER_DEVICEHUB_DATA_DIR}/certbot
        mkdir -p "${certbot_dir}"
        certbot_vol="${certbot_dir}/conf:/etc/letsencrypt"

        generate_certificate "${DEVICEHUB_HOST}"

        if [ "${IDHUB_ENABLE}" = 'true' ]; then
                generate_certificate "${IDHUB_DOMAIN}"
        fi
}

main "${@:-}"

# written in emacs
# -*- mode: shell-script; -*-
