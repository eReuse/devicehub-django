# INSTALACION:

la instalacion es muy estandar

```
  python -m venv env
  source env/bin/actevate
  python install -r requirements.txt
```

## IMPORTANT EXTERNAL DEPENDETS

Para arrancarlo es necesario tener el paquete xapian-bindings en tu ordenador. No se instala por pip asi que depende de cada sistema operativo:
https://xapian.org/download

Luego solo necesitas:

```
  ./manage.py migrate
  ./manage.py runserver
```
