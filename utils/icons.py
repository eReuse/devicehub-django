
ICONS = {
    "Laptop": "bi-laptop",
    "Netbook": "bi-laptop",
    "Desktop": "bi-pc-display",
    "Tower": "bi-pc",
    "Server": "bi-pc-display",
    "Smartphone": "bi-phone",
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
    "Camera": "bi-camera",
    "Switch": "bi-hdd-network",
    "Router": "bi-hdd",
    "RouterWifi": "bi-router",
}

def get_icon_by_type(value):
    return ICONS.get(value, 'bi-question-circle')
