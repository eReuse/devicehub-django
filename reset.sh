rm db/*
python3 manage.py migrate
python3 manage.py add_user user@example.org 1234
python3 manage.py up_snapshots example/snapshots/ user@example.org
