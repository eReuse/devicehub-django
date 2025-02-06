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
    "sku"
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

ALGOS = {
    "ereuse24": EREUSE24,
    "ereuse22": EREUSE22
}


CHASSIS_DH = {
    'Tower': {'desktop', 'low-profile', 'tower', 'server'},
    'Docking': {'docking'},
    'AllInOne': {'all-in-one'},
    'Microtower': {'mini-tower', 'space-saving', 'mini'},
    'PizzaBox': {'pizzabox'},
    'Lunchbox': {'lunchbox'},
    'Stick': {'stick'},
    'Netbook': {'notebook', 'sub-notebook'},
    'Handheld': {'handheld'},
    'Laptop': {'portable', 'laptop'},
    'Convertible': {'convertible'},
    'Detachable': {'detachable'},
    'Tablet': {'tablet'},
    'Virtual': {'_virtual'},
}


DATASTORAGEINTERFACE = [
 'ATA',
 'USB',
 'PCI',
 'NVME',
]
