# constants declarated for all proyect


STR_XSM_SIZE = 16
STR_SM_SIZE = 32
STR_SIZE = 64
STR_BIG_SIZE = 128
STR_EXTEND_SIZE = 256


# Algorithms for build hids
EREUSE24 = [
    "manufacturer",
    "model",
    "chassis",
    "serial_number",
    "mac"
]

# EREUSE22 is used for build the chid of DPP
EREUSE22 = [
    "manufacturer",
    "model",
    "chassis",
    "serial_number",
    "sku",
    "type",
    "version"
]

# Algorithm to build photo evidences
PHOTO25 = {
    "photo": {"extension", "mime_type", "size", "original_name", "name", "hash"},
    "ocr": {'text', 'error'},
    "barcodes": ['type', 'data'],
    "barcode_error": {'error'}
}

ALGOS = {
    "ereuse24": EREUSE24,
    "ereuse22": EREUSE22,
    "photo25": PHOTO25
}


# utils/icons.py is the source of true about types of devices
CHASSIS_DH = {
    'Desktop': {'desktop', 'low-profile', 'tower', 'all-in-one',
                'mini-tower', 'space-saving', 'mini', 'pizzabox',
                'lunchbox', 'stick', 'docking'},
    'Laptop':  {'portable', 'laptop', 'convertible', 'detachable',
                'tablet', 'handheld'},
    'Netbook': {'notebook', 'sub-notebook'},
    'Server':  {'server'},
}


DATASTORAGEINTERFACE = [
 'ATA',
 'USB',
 'PCI',
 'NVME',
]
