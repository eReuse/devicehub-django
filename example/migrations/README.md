Para poder hacer una migracion de los datos de devicehub-teal necesitamos varios ficheros csv con los datos.
Por ejemplo:

--csv-lots-dhid con la relación dhid con nombre del lote.
--csv-dhid es la relación de dhid con uuid de un snapshot.
--snapshots es el directorio donde buscar los snapshots reales. Los busca por uuid


```
  python example/migrations/migration-script.py --email user@example.org --csv-lots-dhid example/migrations/device-lots.csv --csv-dhid example/migrations/dhids.csv --snapshots example/migrations/snapshots
```
