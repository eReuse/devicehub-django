"""
Image processing utilities for OCR and barcode scanning.
"""
import subprocess
import shutil
import logging

logger = logging.getLogger(__name__)


# def check_command_available(command):
#     """
#     Check if a command is available in the system PATH.
#
#     Args:
#         command (str): The command name to check
#
#     Returns:
#         bool: True if command is available, False otherwise
#     """
#     return shutil.which(command) is not None


def extract_text_with_ocr(image_path):
    """
    Extract text from an image using Tesseract OCR.

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

    try:
        # Run tesseract with stdout output
        # --psm 6: Assume a single uniform block of text
        result = subprocess.run(
            ['tesseract', image_path, 'stdout', '--psm', '6'],
            capture_output=True,
            text=True,
            timeout=30,
            check=False
        )

        if result.returncode != 0:
            error_msg = result.stderr.strip() if result.stderr else 'Unknown tesseract error'
            logger.error(f"Tesseract OCR failed: {error_msg}")
            return {
                'text': None,
                'error': error_msg
            }

        extracted_text = result.stdout.strip()

        return {
            'text': extracted_text if extracted_text else None,
            'error': None
        }

    except subprocess.TimeoutExpired:
        logger.error(f"Tesseract OCR timeout for image: {image_path}")
        return {
            'text': None,
            'error': 'OCR processing timeout'
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
