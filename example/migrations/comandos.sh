# create lots
python example/migrations/migration-script.py --email user@example.org --lots migration_tau/lot_temporary.csv
python example/migrations/migration-script.py --email user@example.org --lots migration_tau/lot_incoming.csv
python example/migrations/migration-script.py --email user@example.org --lots migration_tau/lot_outgoing.csv

# upload devices
python example/migrations/migration-script.py --email user@example.org --csv-dhid migration_tau/dhids.csv --snapshots snapshots_tau/

# insert devices in lots
python example/migrations/migration-script.py --email user@example.org --csv-lots-dhid migration_tau/devices-lots.csv
