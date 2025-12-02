"""
Image processing utilities for OCR and barcode scanning.
"""
import subprocess
import shutil
import logging
import json

logger = logging.getLogger(__name__)


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


def extract_exif(image_path):
    """
    Extract exif data using Pillow

    Args:
        image_path (str): Path to the image file

    Returns:
        dict: indexed by the EXIF tag name strings
    """
    if not shutil.which('exiftool'):
        logger.warning("exiftool is not installed. Skipping exif extraction.")
        return {
            'exif': {},
            'error': 'exiftool command not found'
        }

    try:
        result = subprocess.run(
            ['exiftool', "-json", image_path],
            capture_output=True,
            text=True,
            check=True,
            timeout=30  # 30 second timeout
        )
        # Parse JSON output
        metadata = json.loads(result.stdout)

        # exiftool returns a list with one item per file
        if not metadata:
            logger.error(f"No metadata returned from exiftool for image: {image_path}")
            return {
                'exif': {},
                'error': 'No metadata'
            }
        return {
            'exif': metadata[0],
            'error': None
        }

    except subprocess.TimeoutExpired:
        logger.error(f"exiftool timeout for image: {image_path}")
        return {
            'exif': {},
            'error': 'Barcode scanning timeout'
        }

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse exiftool JSON output for image: {image_path}: {e}")
        return {
            'exif': {},
            'error': 'JSON decode error'
        }
    except Exception as e:
        logger.error(f"Unexpected error during barcode scanning: {str(e)}")
        return {
            'exif': {},
            'error': str(e)
        }


def process_image(image_path):
    """
    Process an image to extract text (OCR), barcodes/QR codes and exif data.

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

    exif_result = extract_exif(image_path)

    return {
        'ocr_text': ocr_result['text'],
        'ocr_error': ocr_result['error'],
        'barcodes': barcode_result['barcodes'],
        'barcode_error': barcode_result['error'],
        'exif': exif_result['exif'],
        'exif_error': exif_result['error'],
    }
