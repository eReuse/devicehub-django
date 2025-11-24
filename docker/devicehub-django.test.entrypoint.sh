#!/bin/sh

set -e
set -u
# DEBUG
set -x

# Test-specific entrypoint for DeviceHub Django
# This script sets up a test environment and runs unit tests

gen_env_vars() {
	INIT_ORG="${INIT_ORG:-test-org}"
	INIT_USER="${INIT_USER:-test@example.org}"
	INIT_PASSWD="${INIT_PASSWD:-test1234}"
	ADMIN='True'
	DEMO_PREDEFINED_TOKEN="${DEMO_PREDEFINED_TOKEN:-}"
}

setup_test_environment() {
	program_dir='/opt/devicehub-django'
	cd "${program_dir}"

	if [ ! -w . ]; then
		echo "ERROR: Permission denied for docker user 1000."
		exit 1
	fi

	# Create db directory if it doesn't exist
	if [ ! -d "${program_dir}/db/" ]; then
		mkdir -p "${program_dir}/db/"
	fi

	# Run migrations
	echo "Running migrations..."
	./manage.py migrate

	# Create institution and user for tests
	echo "Setting up test data..."
	./manage.py add_institution "${INIT_ORG}"
	./manage.py add_user "${INIT_ORG}" "${INIT_USER}" "${INIT_PASSWD}" "${ADMIN}" "${DEMO_PREDEFINED_TOKEN}"

	# Create default states
	./manage.py create_default_states "${INIT_ORG}"

	# Load demo data if DEMO=true
	if [ "${DEMO:-}" = 'true' ]; then
		echo "Loading demo data..."
		./manage.py load_demo_data
		./manage.py up_snapshots example/snapshots/ "${INIT_USER}"
	fi
}

run_tests() {
	echo "Running unit tests..."
	echo "================================"

	# Run Django tests
	# Pass any additional arguments from command line to manage.py test
	if [ $# -gt 0 ]; then
		./manage.py test "$@"
	else
		./manage.py test
	fi

	exit_code=$?

	echo "================================"
	if [ ${exit_code} -eq 0 ]; then
		echo "Tests PASSED"
	else
		echo "Tests FAILED"
	fi

	return ${exit_code}
}

main() {
	gen_env_vars
	setup_test_environment
	run_tests "$@"
}

main "$@"
