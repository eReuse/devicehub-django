rm db/*
./manage.py migrate
./manage.py add_user user@example.org 1234
./manage.py up_snapshots example/ user@example.org
