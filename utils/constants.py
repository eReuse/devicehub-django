# constants declarated for all proyect


STR_XSM_SIZE = 16
STR_SM_SIZE = 32
STR_SIZE = 64
STR_BIG_SIZE = 128
STR_EXTEND_SIZE = 256


# Algorithm identifiers (string keys). Named constants so a typo raises
# NameError instead of silently producing a wrong key, and so the name lives
# in a single place.
ALGO_EREUSE24 = "ereuse24"
ALGO_EREUSE26 = "ereuse26"
ALGO_EREUSE22 = "ereuse22"
ALGO_PHOTO25 = "photo25"

# Algorithms for build hids
EREUSE24 = [
    "manufacturer",
    "model",
    "chassis",
    "serial_number",
    "mac"
]

EREUSE26 = [
    "manufacturer",
    "model",
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
    ALGO_EREUSE24: EREUSE24,
    ALGO_EREUSE26: EREUSE26,
    ALGO_EREUSE22: EREUSE22,
    ALGO_PHOTO25: PHOTO25
}

# Subset of ALGOS that build a device identity HID (excludes ereuse22, the DPP
# chid, and photo25, the photo evidence algorithm). migrate_hid_aliases maps
# RootAlias entries between these when the active algorithm changes.
DEVICE_IDENTITY_ALGOS = (ALGO_EREUSE24, ALGO_EREUSE26)


# utils/icons.py is the source of true about types of devices
CHASSIS_DH = {
    'Desktop': {'desktop', 'low-profile', 'tower', 'all-in-one',
                'mini-tower', 'space-saving', 'mini', 'pizzabox',
                'lunchbox', 'stick', 'docking', '_virtual'},
    'Laptop':  {'portable', 'laptop', 'convertible', 'detachable',
                'tablet', 'handheld', 'notebook', 'sub-notebook',
                'netbook'},
    'Server':  {'server'},
}


DATASTORAGEINTERFACE = [
 'ATA',
 'USB',
 'PCI',
 'NVME',
]
