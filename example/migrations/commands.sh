# upload snapshots
python example/migrations/migration-script.py --email user@example.org  --snapshots snapshots_dir

# upload dhids
python example/migrations/migration-script.py --email user@example.org --csv-dhid dhids.csv

# insert devices in lots
python example/migrations/migration-script.py --email user@example.org --csv-lots-dhid devices-lots.csv

# insert monitors
python example/migrations/migration-script.py --email user@example.org  --monitors monitors.csv

# insert monitors in lots
python example/migrations/migration-script.py --email user@example.org --csv-lots-dhid monitors-lots.csv
