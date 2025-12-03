import uuid
from evidence.models import SystemProperty
from utils.save_snapshots import move_json, save_in_disk
from utils.photo_evidence import save_photo_in_disk
from utils.device import create_doc, create_index
from evidence.image_processing import process_image
from utils.device import create_property, create_doc, create_index
from datetime import datetime


def process_photo_upload(photo_data, user=None, algo_key='photo25'):
    if not photo_data:
        return None

    if not user:
        raise ValueError("User instance required for processing photo.")

    # Save physical file
    file_path = save_photo_in_disk(photo_data, user.institution.name)

    # Process image for OCR and barcode detection
    processing_result = process_image(file_path)


    # Clean cache
    json_photo_data = photo_data.copy()
    json_photo_data.pop('content', None)
    json_photo_data.pop('file', None)


    # Build document structure
    uuid_str = str(uuid.uuid4())

    doc = {
        'uuid': uuid_str,
        'type': algo_key,
        'endTime': datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        'software': 'DeviceHub',
        'photo': json_photo_data,
        'data':{
            'ocr': {
                'text': processing_result.get('ocr_text'),
                'error': processing_result.get('ocr_error')
            },
            'barcodes': processing_result.get('barcodes', []),
        }
    }

    path_name = save_in_disk(doc, user.institution.name)
    create_index(doc, user)
    move_json(path_name, user.institution.name)

    # Create SystemProperty with key='photo25' so photo appears in evidence list
    # Using photo hash as the value (similar to device CHID for snapshots)
    SystemProperty.objects.create(
        uuid=uuid_str,
        key=algo_key,
        value=json_photo_data['hash'],
        owner=user.institution,
        user=user
    )

    return doc



def save_device_data(main_data, attribute_formset, user, commit=True):
    row = {}

    if main_data.get("type"): row["type"] = main_data["type"]
    if main_data.get("amount"): row["amount"] = main_data["amount"]
    if main_data.get("custom_id"): row["CUSTOM_ID"] = main_data["custom_id"]

    for form in attribute_formset:
        if form.cleaned_data and not form.cleaned_data.get('DELETE', False):
            name = form.cleaned_data.get("name")
            val = form.cleaned_data.get("value", "")
            if name:
                row[name] = val

    doc = create_doc(row)
    if not commit:
        return doc

    path_name = save_in_disk(doc, user.institution.name, place="placeholder")
    create_index(doc, user)
    create_property(doc, user, commit=commit)
    move_json(path_name, user.institution.name, place="placeholder")

    return doc
