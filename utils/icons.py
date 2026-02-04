
ICONS = {
    "Laptop": "bi-laptop",
    "Netbook": "bi-laptop",
    "Desktop": "bi-pc-display",
    "Server": "bi-pc-display",
    "Motherboard": "bi-motherboard",
    "GraphicCard": "bi-gpu-card",
    "HardDrive": "bi-hdd",
    "SolidStateDrive": "bi-device-ssd",
    "NetworkAdapter": "bi-pci-card-network",
    "Processor": "bi-cpu",
    "RamModule": "bi-memory",
    "SoundCard": "bi-speaker",
    "Display": "bi-display",
    "Battery": "bi-battery",
    "Camera": "bi-camera"
}

def get_icon_by_type(value):
    return ICONS.get(value, 'bi-question-circle')
