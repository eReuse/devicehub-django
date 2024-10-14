# INSTALACIÓN:

La instalación es muy estándar

```
python -m venv env
source env/bin/actevate
python install -r requirements.txt
```

## IMPORTANT EXTERNAL DEPENDENCIES

Para arrancarlo es necesario tener el paquete `xapian-bindings` en tu ordenador. No se instala mediante `pip`, así que depende de cada [sistema operativo](https://xapian.org/download).

Luego solo necesitas:

```
./manage.py migrate
./manage.py runserver
```
