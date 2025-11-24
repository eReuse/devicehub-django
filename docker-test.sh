#!/bin/sh

set -e
set -u

# Docker Test Runner for DeviceHub Django
# Runs unit tests in a Docker container with demo data loaded

main() {
	echo "DeviceHub Django - Docker Test Runner"
	echo "======================================"
	echo ""

	# Build the image if needed
	echo "Building Docker image (if needed)..."
	docker compose build devicehub-django-test

	echo ""
	echo "Starting test container..."
	echo ""

	# Run tests
	# --rm: Remove container after test run
	# Pass any command line arguments to the test runner
	docker compose run --rm devicehub-django-test "$@"

	exit_code=$?

	echo ""
	echo "======================================"
	if [ ${exit_code} -eq 0 ]; then
		echo "Test run completed successfully!"
	else
		echo "Test run failed with exit code ${exit_code}"
	fi
	echo "======================================"

	exit ${exit_code}
}

main "$@"
