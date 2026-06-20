set -a; source ./.env; set +a
export DEVICEHUB_EVIDENCES_DIR="$PWD/_local/evidences"
export DEVICEHUB_MEDIA_ROOT="$PWD/_local/media"
export DEVICEHUB_BACKUPS_DIR="$PWD/_local/backups"
export DEVICEHUB_STATIC_ROOT="$PWD/_local/static"
export DEVICEHUB_ALLOWED_HOSTS="localhost,127.0.0.1,10.0.2.2,0.0.0.0"
export DEVICEHUB_DEBUG=true
