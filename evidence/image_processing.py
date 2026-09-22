"""
Image processing utilities for OCR and barcode scanning.
"""
import hashlib
import uuid
import shutil
import logging
import subprocess
from datetime import datetime
from django.conf import settings
from utils.constants import ALGOS
from evidence.mixin_parse import BuildMix
from utils.save_snapshots import move_json, save_in_disk
from evidence.models import SystemProperty
from utils.photo_evidence import save_photo_in_disk
from utils.device import create_property, create_doc, create_index

logger = logging.getLogger(__name__)


class Build(BuildMix):
    def has_hardware_data(self, data):
        return bool(self.json.get("photo") or self.json.get("photos"))

    def get_details(self):
        # Old photo evidence stores one ``photo``. New evidence stores a
        # ``photos`` collection and identifies the collection as a whole.
        self.hash = self.json.get("photo_hash", "")
        if not self.hash:
            self.hash = self.json.get("photo", {}).get("hash", "")
        if not self.hash and self.json.get("photos"):
            self.hash = photo_bundle_hash(self.json["photos"])
        self.type = "Image"

        return

    def from_credential(self):
        return

    def _get_components(self):
        "an image wont have any components to be extracted,"
        return

    def get_hid(self, algo="photo25"):
        return self.hash


def photo_bundle_hash(photos):
    """Stable identity for one evidence containing one or more photos."""
    hashes = sorted(photo.get("hash", "") for photo in photos if photo.get("hash"))
    if len(hashes) == 1:
        return hashes[0]
    return hashlib.sha256(("photo-bundle-v1\n" + "\n".join(hashes)).encode()).hexdigest()


def build_json(photos):
    _uuid = str(uuid.uuid4())

    return {
        'uuid': _uuid,
        'endTime': datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        'type': "photo25",
        'software': settings.APP_NAME,
        'photo_hash': photo_bundle_hash(photos),
        'photos': photos,
        'data': {
            'snapshot_type': "Image",
            'photo_count': len(photos),
        }
    }


def process_photo_upload(photo_data, user=None, algo_key='photo25'):
    """Backward-compatible entry point for a one-photo evidence."""
    if not photo_data:
        return None
    return process_photo_uploads([photo_data], user=user, algo_key=algo_key)


def process_photo_uploads(photo_data_list, user=None, algo_key='photo25'):
    """Create one evidence document containing all supplied photos."""
    if not photo_data_list:
        return None

    if not user:
        raise ValueError("User instance required for processing photo.")

    photos = []
    for photo_data in photo_data_list:
        file_path = save_photo_in_disk(photo_data, user.institution.name)
        processing_result = process_image(file_path)
        photo = photo_data.copy()
        photo.pop('content', None)
        photo.pop('file', None)
        photo['ocr'] = {
            'text': processing_result.get('ocr_text'),
            'error': processing_result.get('ocr_error'),
        }
        photo['barcodes'] = processing_result.get('barcodes', [])
        photo['barcode_error'] = processing_result.get('barcode_error')
        photos.append(photo)

    doc = build_json(photos)

    path_name = save_in_disk(doc, user.institution.name)
    create_index(doc, user)
    move_json(path_name, user.institution.name)

    # One property represents the complete photo collection and is aliased to
    # the product just like the previous one-photo evidence.
    prop_value = "{}:{}".format(algo_key, doc["photo_hash"])
    SystemProperty.objects.create(
        uuid=doc.get("uuid", ""),
        key=algo_key,
        value=prop_value,
        owner=user.institution,
        user=user
    )

    return doc


def extract_text_with_ocr(image_path):
    """
    Extract text from an image using Tesseract OCR.
    Uses ImageMagick's convert to auto-orient the image before OCR.

    Args:
        image_path (str): Path to the image file

    Returns:
        dict: Dictionary with 'text' (extracted text or None) and 'error' (error message or None)
    """
    if not shutil.which('tesseract'):
        logger.warning("Tesseract OCR is not installed. Skipping text extraction.")
        return {
            'text': None,
            'error': 'tesseract command not found'
        }

    if not shutil.which('convert'):
        logger.warning("ImageMagick convert is not installed. Skipping text extraction.")
        return {
            'text': None,
            'error': 'convert command not found'
        }

    try:
        # Run: convert image_path -auto-orient - | tesseract stdin stdout
        # This auto-orients the image based on EXIF data before OCR
        convert_process = subprocess.Popen(
            ['convert', image_path, '-auto-orient', '-'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        tesseract_process = subprocess.Popen(
            ['tesseract', 'stdin', 'stdout', '-l', 'spa+cat+eng'],
            stdin=convert_process.stdout,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        # Close convert's stdout in parent process to allow SIGPIPE
        convert_process.stdout.close()

        # Wait for tesseract to complete with timeout
        try:
            stdout, stderr = tesseract_process.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            tesseract_process.kill()
            convert_process.kill()
            logger.error(f"Tesseract OCR timeout for image: {image_path}")
            return {
                'text': None,
                'error': 'OCR processing timeout'
            }

        # Check if convert failed
        convert_returncode = convert_process.wait()
        if convert_returncode != 0:
            _, convert_stderr = convert_process.communicate()
            error_msg = convert_stderr.decode() if convert_stderr else 'Unknown convert error'
            logger.error(f"ImageMagick convert failed: {error_msg}")
            return {
                'text': None,
                'error': f'Image conversion failed: {error_msg}'
            }

        # Check if tesseract failed
        if tesseract_process.returncode != 0:
            error_msg = stderr.strip() if stderr else 'Unknown tesseract error'
            logger.error(f"Tesseract OCR failed: {error_msg}")
            return {
                'text': None,
                'error': error_msg
            }

        extracted_text = stdout.strip()

        return {
            'text': extracted_text if extracted_text else None,
            'error': None
        }

    except Exception as e:
        logger.error(f"Unexpected error during OCR: {str(e)}")
        return {
            'text': None,
            'error': str(e)
        }


def extract_barcodes(image_path):
    """
    Extract barcode/QR code information from an image using zbar.

    Args:
        image_path (str): Path to the image file

    Returns:
        dict: Dictionary with 'barcodes' (list of barcode data) and 'error' (error message or None)
    """
    if not shutil.which('zbarimg'):
        logger.warning("zbarimg is not installed. Skipping barcode extraction.")
        return {
            'barcodes': [],
            'error': 'zbarimg command not found'
        }

    try:
        # Run zbarimg with --quiet (no verbose output) and --raw (only data)
        result = subprocess.run(
            ['zbarimg', '--quiet', image_path],
            capture_output=True,
            text=True,
            timeout=30,
            check=False
        )

        # zbarimg returns exit code 4 when no barcodes are found (not an error)
        if result.returncode != 0 and result.returncode != 4:
            error_msg = result.stderr.strip() if result.stderr else 'Unknown zbarimg error'
            logger.error(f"zbarimg failed: {error_msg}")
            return {
                'barcodes': [],
                'error': error_msg
            }

        # Parse output - each line is a barcode
        barcodes = []
        if result.stdout:
            for line in result.stdout.strip().split('\n'):
                if line:
                    # split at first colon to separate type and data
                    parts = line.split(':', 1)
                    if len(parts) == 2:
                        _type, data = parts
                        barcodes.append({'type': _type, 'data': data.strip()})
        return {
            'barcodes': barcodes,
            'error': None
        }

    except subprocess.TimeoutExpired:
        logger.error(f"zbarimg timeout for image: {image_path}")
        return {
            'barcodes': [],
            'error': 'Barcode scanning timeout'
        }
    except Exception as e:
        logger.error(f"Unexpected error during barcode scanning: {str(e)}")
        return {
            'barcodes': [],
            'error': str(e)
        }


def process_image(image_path):
    """
    Process an image to extract text (OCR) and barcodes/QR codes.

    Args:
        image_path (str): Path to the image file to process

    Returns:
        dict: Dictionary containing:
            - ocr_text (str|None): Extracted text from OCR
            - ocr_error (str|None): OCR error message if any
            - barcodes (list): List of detected barcode/QR code data
            - barcode_error (str|None): Barcode scanning error message if any
    """
    # Extract text with OCR
    ocr_result = extract_text_with_ocr(image_path)

    # Extract barcodes
    barcode_result = extract_barcodes(image_path)

    return {
        'ocr_text': ocr_result['text'],
        'ocr_error': ocr_result['error'],
        'barcodes': barcode_result['barcodes'],
        'barcode_error': barcode_result['error']
    }
