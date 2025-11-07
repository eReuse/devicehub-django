import os

from django.conf import settings


def get_photos_dir(user):
    tmp_snapshots = settings.EVIDENCES_DIR
    photos_dir = os.path.join(tmp_snapshots, user, "photos")
    return photos_dir


def save_photo_in_disk(image_data, user):
    name = image_data.get("name")

    photos_dir = get_photos_dir(user)
    filename = os.path.join(photos_dir, name)

    if not os.path.exists(photos_dir):
        os.makedirs(photos_dir, exist_ok=True)

    with open(filename, 'wb') as image_file:
        image_file.write(image_data['content'])

    return filename
