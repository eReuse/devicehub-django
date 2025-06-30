#!/bin/sh

set -e
set -u
# DEBUG
set -x

main() {
        cd "$(dirname "${0}")"
        . ../.env
        # inspiration: https://docs.joinpeertube.org/install/docker
        mkdir -p ${DEVICEHUB_ROOT_DIR}/${DEVICEHUB_DOCKER_DIR}/${DEVICEHUB_HOST}/certbot
        certbot_vol="${DEVICEHUB_ROOT_DIR}/${DEVICEHUB_DOCKER_DIR}/${DEVICEHUB_HOST}/certbot/conf:/etc/letsencrypt"
        certbot_args="certonly --standalone --agree-tos --register-unsafely-without-email -d ${DEVICEHUB_HOST}"
        docker run -it --rm --name certbot-init -p 80:80 -v "${certbot_vol}" certbot/certbot ${certbot_args}
}

main "${@:-}"

# written in emacs
# -*- mode: shell-script; -*-
