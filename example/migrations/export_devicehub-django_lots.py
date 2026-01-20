import os
import django


try:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dhub.settings')
    django.setup()

    from user.models import User
    from lot.models import Lot

    # exports devicehub-django lots to csv

    ## TODO assuming this hardcoded user!
    email = 'user@example.org'

    i = User.objects.filter(email=email).first().institution
    devs = [["lot_name", "total"]]

    for l in Lot.objects.filter(owner=i):
        devs.append([l.name, "{}".format(len(l.devices))])

    # TODO hardcoded export file!
    with open("export_ereuse.csv", "w") as _f:
        _f.write("\n".join([";".join(l) for l in devs]))
except:
    print('ERROR: remember this should be ran as: python example/migrations/export_devicehub-django_lots.py')
