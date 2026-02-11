#!/bin/sh
# inspired by https://github.com/Chocobozzz/PeerTube/blob/b9c3a4837e6a5e5d790e55759e3cf2871df4f03c/support/docker/production/entrypoint.nginx.sh

set -e
set -u
# DEBUG
set -x

generate_webserver() {
        export WEBSERVER_HOST="${1}"
        export APP_UPSTREAM="${2}"

        if [ "${ENABLE_LETSENCRYPT:-true}" = "true" ]; then
                export SSL_CERTIFICATE_PATH="/etc/letsencrypt/live/${WEBSERVER_HOST}/fullchain.pem"
                export SSL_CERTIFICATE_KEY_PATH="/etc/letsencrypt/live/${WEBSERVER_HOST}/privkey.pem";
        else
                # do selfsigned certs as `ssl-cert` debian package
                export SSL_CERTIFICATE_PATH="/etc/ssl/certs/ssl-cert-snakeoil.pem";
                export SSL_CERTIFICATE_KEY_PATH="/etc/ssl/private/ssl-cert-snakeoil.key";
        fi

        envsubst '${WEBSERVER_HOST} ${APP_UPSTREAM} ${SSL_CERTIFICATE_PATH} ${SSL_CERTIFICATE_KEY_PATH}' < ${SOURCE_FILE} > "/etc/nginx/conf.d/${WEBSERVER_HOST}.conf"
}

main() {
        # Process the nginx template
        SOURCE_FILE="/etc/nginx/conf.d/app.template"

        # Remove default nginx config
        rm -f /etc/nginx/conf.d/default.conf

        generate_webserver "${DEVICEHUB_HOST}" "${DEVICEHUB_UPSTREAM}"

        if [ "${IDHUB_ENABLED}" = 'true' ]; then
                generate_webserver "${IDHUB_DOMAIN}" "${IDHUB_UPSTREAM}"
        fi

        # DEBUG
        #sleep infinity

        while [ "${ENABLE_LETSENCRYPT:-}" = "true" ]; do
                sleep 12h & wait $!;
                nginx -s reload;
        done &

        exec nginx -g 'worker_processes 2; daemon off;'
}
main
