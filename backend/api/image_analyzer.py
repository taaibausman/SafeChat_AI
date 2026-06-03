import io
import os
import re
import time
from datetime import datetime, timezone
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session
import numpy as np
import requests
from backend.database.config import get_db
import backend.models.domain as models
import backend.schemas.domain as schemas
from backend.ai.engine import ai_engine
from backend.api.chat_analyzer import _build_analysis_payload
from backend.api.realtime import manager as realtime_manager
import asyncio
from PIL import Image
from PIL import ImageEnhance, ImageFilter, ImageOps
import pytesseract

try:
    from google.api_core.exceptions import GoogleAPICallError
    from google.auth.exceptions import DefaultCredentialsError
    from google.cloud import vision
except Exception:  # pragma: no cover - optional dependency
    GoogleAPICallError = Exception
    DefaultCredentialsError = Exception
    vision = None

router = APIRouter()

DEFAULT_TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
DEFAULT_EASYOCR_WORK_HOME = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    ".easyocr-home",
)
os.makedirs(DEFAULT_EASYOCR_WORK_HOME, exist_ok=True)
OCR_PROVIDER = os.environ.get("SAFECHAT_OCR_PROVIDER", "tesseract").strip().lower()
EASYOCR_LANG_LIST = [lang.strip() for lang in os.environ.get("EASYOCR_LANG_LIST", "en").split(",") if lang.strip()]
EASYOCR_USE_GPU = os.environ.get("EASYOCR_USE_GPU", "").strip().lower() in {"1", "true", "yes", "on"}
OCR_SPACE_API_KEY = os.environ.get("OCR_SPACE_API_KEY", "").strip()
OCR_SPACE_ENDPOINT = os.environ.get("OCR_SPACE_ENDPOINT", "https://api.ocr.space/parse/image").strip()
OCR_SPACE_LANGUAGE = os.environ.get("OCR_SPACE_LANGUAGE", "eng").strip().lower() or "eng"
OCR_SPACE_ENGINE = os.environ.get("OCR_SPACE_ENGINE", "2").strip() or "2"
OCR_SPACE_TIMEOUT_SECONDS = max(int(os.environ.get("OCR_SPACE_TIMEOUT_SECONDS", "60")), 5)
_EASYOCR_READER = None

if os.path.exists(DEFAULT_TESSERACT_PATH):
    pytesseract.pytesseract.tesseract_cmd = DEFAULT_TESSERACT_PATH


def _score_ocr_candidate(text: str) -> tuple[int, int, int]:
    alnum_count = sum(char.isalnum() for char in text)
    line_count = sum(1 for line in text.splitlines() if line.strip())
    symbol_count = sum(1 for char in text if not char.isalnum() and not char.isspace())
    return (alnum_count, line_count, -symbol_count)


def _normalize_ocr_text(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = normalized.replace("\u2018", "'").replace("\u2019", "'")
    normalized = normalized.replace("\u201c", '"').replace("\u201d", '"')
    normalized = normalized.replace("\u2013", "-").replace("\u2014", "-")
    normalized = normalized.replace("\u00a0", " ")

    cleaned_lines: list[str] = []
    for raw_line in normalized.split("\n"):
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            continue
        line = re.sub(r"^[^\w]+", "", line)
        line = re.sub(r"[^\w!?.,:/%+\-)\]]+$", "", line)
        if not line:
            continue
        if sum(char.isalnum() for char in line) < 2:
            continue
        cleaned_lines.append(line)

    if not cleaned_lines:
        return ""

    compact_lines: list[str] = []
    for line in cleaned_lines:
        if compact_lines and len(line) < 28 and not re.search(r"[:.!?]$", compact_lines[-1]):
            compact_lines[-1] = f"{compact_lines[-1]} {line}"
        else:
            compact_lines.append(line)

    return "\n".join(compact_lines).strip()


def _strip_inline_timestamp(text: str) -> str:
    return re.sub(r"\b\d{1,2}[.:]\d{2}\s*(?:am|pm)?\b", "", text, flags=re.IGNORECASE).strip(" -:|")


def _is_weird_mixed_case_token(token: str) -> bool:
    alpha = re.sub(r"[^A-Za-z]", "", token)
    if len(alpha) < 5:
        return False
    upper = sum(char.isupper() for char in alpha)
    lower = sum(char.islower() for char in alpha)
    return upper >= 2 and lower >= 2 and not alpha.istitle() and not alpha.isupper() and not alpha.islower()


def _token_looks_like_ocr_noise(token: str) -> bool:
    alpha = re.sub(r"[^A-Za-z]", "", token)
    if not alpha:
        return True
    if len(alpha) <= 2:
        return True
    if re.fullmatch(r"[aeiouyAEIOUY]+", alpha):
        return True
    vowel_count = sum(1 for char in alpha.lower() if char in {"a", "e", "i", "o", "u", "y"})
    if len(alpha) <= 3 and vowel_count / max(len(alpha), 1) >= 0.66:
        return True
    if _is_weird_mixed_case_token(alpha):
        return True
    return False


def _ocr_text_quality_score(text: str) -> float:
    compact = re.sub(r"\s+", " ", text).strip()
    if not compact:
        return float("-inf")

    alpha_tokens = re.findall(r"[A-Za-z']+", compact)
    if not alpha_tokens:
        return float("-inf")

    alpha_chars = sum(len(token) for token in alpha_tokens)
    short_tokens = sum(1 for token in alpha_tokens if len(token) <= 1)
    vowel_only_tokens = sum(1 for token in alpha_tokens if re.fullmatch(r"[aeiouyAEIOUY]+", token))
    weird_case_tokens = sum(1 for token in alpha_tokens if _is_weird_mixed_case_token(token))
    long_tokens = sum(1 for token in alpha_tokens if len(token) >= 13)
    symbol_count = sum(1 for char in compact if not char.isalnum() and not char.isspace())
    avg_len = alpha_chars / max(len(alpha_tokens), 1)

    score = alpha_chars + (len(alpha_tokens) * 2.5)
    score -= short_tokens * 4
    score -= vowel_only_tokens * 4
    score -= weird_case_tokens * 7
    score -= long_tokens * 4
    score -= symbol_count * 1.5
    if 2.6 <= avg_len <= 6.5:
        score += 6
    return score


def _clean_ocr_line_candidate(text: str) -> str:
    compact = re.sub(r"\s+", " ", text).strip(" -:|")
    if not compact:
        return ""

    raw_tokens = compact.split()
    filtered_tokens: list[str] = []
    for token in raw_tokens:
        cleaned = token.strip("`~!@#$%^&*()_+=[]{}|\\:;\",<>/?")
        if not cleaned:
            continue
        if cleaned.isdigit():
            continue
        if len(re.sub(r"[^A-Za-z]", "", cleaned)) <= 1:
            continue
        if _is_weird_mixed_case_token(cleaned):
            continue
        filtered_tokens.append(cleaned)

    if not filtered_tokens:
        return ""

    full_candidate = " ".join(filtered_tokens).strip()
    best_candidate = full_candidate
    best_score = _ocr_text_quality_score(full_candidate)
    best_density = best_score / max(len(re.findall(r"[A-Za-z']+", full_candidate)), 1)

    for separator in [",", "|", "="]:
        if separator not in compact:
            continue
        punct_suffix = compact.rsplit(separator, 1)[-1].strip()
        if not punct_suffix:
            continue
        candidate = _clean_ocr_line_candidate(punct_suffix)
        if not candidate:
            continue
        score = _ocr_text_quality_score(candidate)
        density = score / max(len(re.findall(r"[A-Za-z']+", candidate)), 1)
        if density > best_density + 0.5 or (density > best_density - 0.1 and score > best_score):
            best_candidate = candidate
            best_score = score
            best_density = density

    for start in range(len(filtered_tokens)):
        suffix_tokens = filtered_tokens[start:]
        if len(suffix_tokens) < 2:
            continue
        if start > 0 and not all(_token_looks_like_ocr_noise(token) for token in filtered_tokens[:start]):
            continue
        candidate = " ".join(suffix_tokens).strip()
        score = _ocr_text_quality_score(candidate)
        density = score / max(len(re.findall(r"[A-Za-z']+", candidate)), 1)
        if density > best_density + 0.8 or (density > best_density and score > best_score):
            best_candidate = candidate
            best_score = score
            best_density = density

    return best_candidate


def _looks_like_low_quality_ocr_line(text: str) -> bool:
    compact = re.sub(r"\s+", " ", text).strip()
    if not compact:
        return True

    alpha_tokens = re.findall(r"[A-Za-z']+", compact)
    if not alpha_tokens:
        return True
    if len(alpha_tokens) <= 1 and sum(len(token) for token in alpha_tokens) < 5:
        return True

    short_tokens = sum(1 for token in alpha_tokens if len(token) <= 1)
    vowel_only_tokens = sum(1 for token in alpha_tokens if re.fullmatch(r"[aeiouyAEIOUY]+", token))
    weird_case_tokens = sum(1 for token in alpha_tokens if _is_weird_mixed_case_token(token))
    avg_len = sum(len(token) for token in alpha_tokens) / max(len(alpha_tokens), 1)

    if len(alpha_tokens) >= 4 and short_tokens / len(alpha_tokens) >= 0.45:
        return True
    if len(alpha_tokens) >= 4 and vowel_only_tokens / len(alpha_tokens) >= 0.4:
        return True
    if len(alpha_tokens) >= 4 and weird_case_tokens / len(alpha_tokens) >= 0.25:
        return True
    if len(alpha_tokens) >= 5 and avg_len < 2.2:
        return True
    if _ocr_text_quality_score(compact) < 8:
        return True
    return False


def _looks_like_non_chat_ocr_line(text: str) -> bool:
    compact = re.sub(r"\s+", " ", text).strip().lower()
    if not compact:
        return True
    blocked_fragments = (
        "forwarded",
        "agent router",
        "openai code",
        "claude code",
        "gpt-4o",
        "deepseek",
        "agentrouter",
        "sign up with github",
        "free ai credits",
        "github account",
        "dont miss this opportunity",
        "don't miss this opportunity",
        "get up to",
        "view channel",
        "unread messages",
        "http://",
        "https://",
        "https ",
        "www.",
    )
    if any(fragment in compact for fragment in blocked_fragments):
        return True
    if compact.count("/") >= 1 or compact.count("aff") >= 1:
        return True
    return False


def _segment_ocr_text_into_messages(text: str) -> list[dict]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    segments: list[str] = []

    for raw_line in normalized.split("\n"):
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            continue
        if _looks_like_date_chip(line):
            continue
        if line.lower() in {"message", "view channel"}:
            continue
        if _looks_like_non_chat_ocr_line(line):
            continue

        timestamp_pattern = re.compile(r"\b\d{1,2}[.:]\d{2}\s*(?:am|pm)\b", flags=re.IGNORECASE)
        matches = list(timestamp_pattern.finditer(line))
        if len(matches) >= 1:
            for index, match in enumerate(matches):
                start = match.end()
                end = matches[index + 1].start() if index + 1 < len(matches) else len(line)
                candidate = _clean_ocr_line_candidate(line[start:end])
                if (
                    candidate
                    and len(re.sub(r"\W+", "", candidate)) >= 3
                    and not _looks_like_non_chat_ocr_line(candidate)
                    and not _looks_like_low_quality_ocr_line(candidate)
                ):
                    segments.append(candidate)
            prefix = _clean_ocr_line_candidate(line[: matches[0].start()])
            if (
                prefix
                and len(re.sub(r"\W+", "", prefix)) >= 3
                and not _looks_like_non_chat_ocr_line(prefix)
                and not _looks_like_low_quality_ocr_line(prefix)
            ):
                segments.append(prefix)
            continue

        cleaned = _clean_ocr_line_candidate(_strip_inline_timestamp(line))
        if (
            cleaned
            and len(re.sub(r"\W+", "", cleaned)) >= 3
            and not _looks_like_non_chat_ocr_line(cleaned)
            and not _looks_like_low_quality_ocr_line(cleaned)
        ):
            segments.append(cleaned)

    if not segments:
        fallback = _clean_ocr_line_candidate(_normalize_ocr_text(text))
        if fallback and not _looks_like_non_chat_ocr_line(fallback) and not _looks_like_low_quality_ocr_line(fallback):
            segments = [fallback]

    return [
        {
            "sender": "OCR Extract",
            "message": segment,
            "timestamp": None,
        }
        for segment in segments
    ]


def _extract_text_with_google_vision(content: bytes) -> str:
    if vision is None:
        raise RuntimeError("Google Cloud Vision client library is not installed.")

    client = vision.ImageAnnotatorClient()
    image = vision.Image(content=content)
    response = client.document_text_detection(image=image)

    if response.error.message:
        raise RuntimeError(response.error.message)

    text = response.full_text_annotation.text if response.full_text_annotation else ""
    normalized = _normalize_ocr_text(text)
    if not normalized:
        raise RuntimeError("Google Vision returned no usable OCR text.")
    return normalized


def _get_easyocr_reader():
    global _EASYOCR_READER
    if _EASYOCR_READER is not None:
        return _EASYOCR_READER

    try:
        import easyocr
    except Exception as exc:
        raise RuntimeError("EasyOCR could not be imported. Check that `easyocr` is installed correctly.") from exc

    try:
        _EASYOCR_READER = easyocr.Reader(
            EASYOCR_LANG_LIST,
            gpu=EASYOCR_USE_GPU,
            verbose=False,
            model_storage_directory=DEFAULT_EASYOCR_WORK_HOME,
            user_network_directory=DEFAULT_EASYOCR_WORK_HOME,
        )
    except TypeError:
        _EASYOCR_READER = easyocr.Reader(
            EASYOCR_LANG_LIST,
            gpu=EASYOCR_USE_GPU,
            model_storage_directory=DEFAULT_EASYOCR_WORK_HOME,
            user_network_directory=DEFAULT_EASYOCR_WORK_HOME,
        )
    except Exception as exc:
        raise RuntimeError(f"Could not initialize EasyOCR: {exc}") from exc

    return _EASYOCR_READER


def _bbox_bounds(points) -> tuple[float, float, float, float]:
    xs = [float(point[0]) for point in points]
    ys = [float(point[1]) for point in points]
    return min(xs), min(ys), max(xs), max(ys)


def _looks_like_timestamp_only(text: str) -> bool:
    compact = re.sub(r"\s+", " ", text).strip().lower()
    return bool(
        re.fullmatch(r"\d{1,2}[:.]\d{2}\s*(am|pm)?", compact)
        or re.fullmatch(r"\d{1,2}\s*(am|pm)", compact)
    )


def _looks_like_date_chip(text: str) -> bool:
    compact = re.sub(r"\s+", " ", text).strip().lower()
    if compact in {"today", "yesterday", "forwarded"}:
        return True
    return bool(
        re.search(r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b", compact)
        and re.search(r"\b20\d{2}\b", compact)
    )


def _filter_easyocr_lines(results, image_size: tuple[int, int]) -> list[str]:
    width, height = image_size
    kept: list[tuple[float, str]] = []

    if height < 800:
        simple_lines: list[tuple[float, str]] = []
        for item in results or []:
            if not (isinstance(item, (list, tuple)) and len(item) >= 2 and isinstance(item[1], str)):
                continue
            text = item[1].strip()
            if not text:
                continue
            try:
                _, min_y, _, _ = _bbox_bounds(item[0])
            except Exception:
                min_y = 0.0
            simple_lines.append((min_y, text))
        simple_lines.sort(key=lambda item: item[0])
        return [text for _, text in simple_lines]

    for item in results or []:
        if not (isinstance(item, (list, tuple)) and len(item) >= 2 and isinstance(item[1], str)):
            continue
        points = item[0]
        text = item[1].strip()
        if not text:
            continue

        try:
            min_x, min_y, max_x, max_y = _bbox_bounds(points)
        except Exception:
            kept.append((0.0, text))
            continue

        center_x = (min_x + max_x) / 2
        center_y = (min_y + max_y) / 2
        box_width = max_x - min_x
        box_height = max_y - min_y

        if center_y < height * 0.10:
            continue
        if center_y > height * 0.92:
            continue
        if box_height < 10 and center_y < height * 0.18:
            continue
        if _looks_like_timestamp_only(text) and center_x > width * 0.68:
            continue
        if _looks_like_date_chip(text) and abs(center_x - width / 2) < width * 0.18 and box_width < width * 0.45:
            continue
        if text.strip().lower() == "message" and center_y > height * 0.72:
            continue
        if ("unread messages" in text.strip().lower() or text.strip().lower() == "view channel") and abs(center_x - width / 2) < width * 0.25:
            continue

        kept.append((min_y, text))

    kept.sort(key=lambda item: item[0])
    return [text for _, text in kept]


def _extract_text_with_easyocr(content: bytes) -> str:
    try:
        image = Image.open(io.BytesIO(content))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to process image: {str(exc)}") from exc

    processed = ImageOps.exif_transpose(image).convert("RGB")
    if processed.width < 1600:
        scale = 1600 / max(processed.width, 1)
        processed = processed.resize((1600, max(int(processed.height * scale), 1)))
    processed = ImageEnhance.Contrast(processed).enhance(1.45)
    processed = ImageEnhance.Sharpness(processed).enhance(1.25)

    try:
        reader = _get_easyocr_reader()
        results = reader.readtext(np.array(processed), detail=1, paragraph=False)
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"EasyOCR inference failed: {exc}") from exc

    lines = _filter_easyocr_lines(results, processed.size)

    extracted_text = _normalize_ocr_text("\n".join(lines))
    if not extracted_text:
        raise HTTPException(status_code=400, detail="Could not extract any text from the image")
    return extracted_text


def _extract_text_with_ocr_space(content: bytes) -> str:
    if not OCR_SPACE_API_KEY:
        raise RuntimeError("OCR.space API key is not configured.")

    files = {
        "file": ("image-upload.png", content),
    }
    data = {
        "language": OCR_SPACE_LANGUAGE,
        "isOverlayRequired": "false",
        "OCREngine": OCR_SPACE_ENGINE,
        "scale": "true",
        "detectOrientation": "true",
        "isTable": "false",
    }

    try:
        response = requests.post(
            OCR_SPACE_ENDPOINT,
            headers={"apikey": OCR_SPACE_API_KEY},
            data=data,
            files=files,
            timeout=OCR_SPACE_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.Timeout as exc:
        raise RuntimeError("OCR.space request timed out.") from exc
    except requests.RequestException as exc:
        raise RuntimeError(f"OCR.space request failed: {exc}") from exc
    except ValueError as exc:
        raise RuntimeError("OCR.space returned invalid JSON.") from exc

    if payload.get("IsErroredOnProcessing"):
        errors = payload.get("ErrorMessage") or payload.get("ErrorDetails") or "OCR.space could not process the image."
        if isinstance(errors, list):
            errors = " ".join(str(item) for item in errors if item)
        raise RuntimeError(str(errors))

    parsed_results = payload.get("ParsedResults") or []
    extracted_blocks = [
        _normalize_ocr_text((item or {}).get("ParsedText", ""))
        for item in parsed_results
    ]
    extracted_text = "\n".join(block for block in extracted_blocks if block).strip()
    if not extracted_text:
        raise HTTPException(status_code=400, detail="Could not extract any text from the image")
    return extracted_text


def _extract_text_with_tesseract(content: bytes) -> str:
    try:
        image = Image.open(io.BytesIO(content))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to process image: {str(exc)}") from exc

    processed = ImageOps.exif_transpose(image).convert("L")
    processed = ImageEnhance.Contrast(processed).enhance(1.8)
    processed = ImageEnhance.Sharpness(processed).enhance(1.35)
    if processed.width < 1600:
        scale = 1600 / max(processed.width, 1)
        processed = processed.resize((1600, max(int(processed.height * scale), 1)))
    processed = processed.filter(ImageFilter.MedianFilter(size=3))
    processed = ImageOps.autocontrast(processed)

    thresholded = processed.point(lambda pixel: 255 if pixel > 170 else 0)
    candidates: list[str] = []

    try:
        candidates.append(pytesseract.image_to_string(processed, config="--oem 3 --psm 6"))
        candidates.append(pytesseract.image_to_string(processed, config="--oem 3 --psm 11"))
        candidates.append(pytesseract.image_to_string(thresholded, config="--oem 3 --psm 6"))
    except pytesseract.TesseractNotFoundError as exc:
        raise HTTPException(
            status_code=500,
            detail="Tesseract OCR is not installed or not in PATH. Please install Tesseract-OCR.",
        ) from exc

    extracted_text = max((_normalize_ocr_text(candidate) for candidate in candidates), key=_score_ocr_candidate, default="")
    if not extracted_text.strip():
        raise HTTPException(status_code=400, detail="Could not extract any text from the image")
    return extracted_text.strip()


def extract_text_from_image_bytes(content: bytes) -> str:
    if OCR_PROVIDER == "easyocr":
        try:
            return _extract_text_with_easyocr(content)
        except HTTPException:
            raise
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=f"EasyOCR failed: {exc}") from exc

    if OCR_PROVIDER == "ocrspace":
        try:
            return _extract_text_with_ocr_space(content)
        except HTTPException:
            raise
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=f"OCR.space failed: {exc}") from exc

    if OCR_PROVIDER == "google":
        try:
            return _extract_text_with_google_vision(content)
        except HTTPException:
            raise
        except (DefaultCredentialsError, GoogleAPICallError, RuntimeError) as exc:
            raise HTTPException(status_code=502, detail=f"Google Vision OCR failed: {exc}") from exc

    if OCR_PROVIDER == "tesseract":
        return _extract_text_with_tesseract(content)

    if OCR_PROVIDER == "auto":
        try:
            return _extract_text_with_easyocr(content)
        except HTTPException as exc:
            if exc.status_code == 400:
                raise
        except RuntimeError:
            pass

        try:
            return _extract_text_with_ocr_space(content)
        except HTTPException as exc:
            if exc.status_code == 400:
                raise
        except RuntimeError:
            pass

        try:
            return _extract_text_with_google_vision(content)
        except HTTPException as exc:
            if exc.status_code == 400:
                raise
        except (DefaultCredentialsError, GoogleAPICallError, RuntimeError):
            return _extract_text_with_tesseract(content)

    try:
        return _extract_text_with_easyocr(content)
    except HTTPException as exc:
        if exc.status_code == 400:
            raise
    except RuntimeError:
        pass

    try:
        return _extract_text_with_google_vision(content)
    except HTTPException as exc:
        if exc.status_code == 400:
            raise
    except (DefaultCredentialsError, GoogleAPICallError, RuntimeError):
        return _extract_text_with_tesseract(content)


def persist_image_analysis(
    *,
    db: Session,
    filename: str,
    extracted_text: str,
) -> tuple[models.Chat, models.ImageScan]:
    new_chat = models.Chat(platform="Image_OCR", chat_name=filename)
    db.add(new_chat)
    db.commit()
    db.refresh(new_chat)

    image_scan = models.ImageScan(
        file_path=filename or "uploaded-image",
        ocr_text=extracted_text,
        is_flagged=False,
        toxicity_score=0.0,
        scan_time=datetime.now(timezone.utc),
    )
    db.add(image_scan)
    db.commit()
    db.refresh(image_scan)
    return new_chat, image_scan

@router.post("/upload", response_model=schemas.ChatUploadResponse)
async def upload_image(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Only image files are supported")

    started_at = time.perf_counter()
    content = await file.read()
    print(
        f"[image-upload] start filename={file.filename or 'uploaded-image'} "
        f"size_bytes={len(content)} provider={OCR_PROVIDER}"
    )
    extracted_text = extract_text_from_image_bytes(content)

    parsed_messages = _segment_ocr_text_into_messages(extracted_text)
    new_chat, image_scan = persist_image_analysis(
        db=db,
        filename=file.filename or "uploaded-image",
        extracted_text=extracted_text,
    )

    total_messages, analysis_result, _ = _build_analysis_payload(
        parsed_messages,
        new_chat.id,
        new_chat.chat_name,
        persist=True,
        db=db,
    )

    latest_message = (
        db.query(models.Message)
        .filter(models.Message.chat_id == new_chat.id)
        .order_by(models.Message.id.desc())
        .first()
    )
    image_scan.is_flagged = analysis_result.unsafe_percentage > 0
    image_scan.toxicity_score = analysis_result.overall_score
    db.commit()

    # Broadcast live message
    if latest_message is not None:
        try:
            payload = {
                "type": "message",
                "payload": {
                    "id": latest_message.id,
                    "chat_id": new_chat.id,
                    "chat_name": new_chat.chat_name,
                    "sender": latest_message.sender,
                    "message": latest_message.message,
                    "timestamp": latest_message.timestamp.isoformat() if latest_message.timestamp else None,
                    "risk_score": latest_message.risk_score,
                    "label": latest_message.label,
                }
            }
            asyncio.create_task(realtime_manager.broadcast(payload))
        except Exception:
            pass
    # Save overall AnalysisResult
    result = models.AnalysisResult(
        chat_id=new_chat.id,
        overall_score=analysis_result.overall_score,
        safe_percentage=analysis_result.safe_percentage,
        unsafe_percentage=analysis_result.unsafe_percentage,
        summary=analysis_result.summary,
    )
    db.add(result)
    db.commit()

    elapsed = time.perf_counter() - started_at
    print(
        f"[image-upload] complete filename={file.filename or 'uploaded-image'} "
        f"messages={total_messages} elapsed_seconds={elapsed:.2f}"
    )
    return {"chat_id": new_chat.id, "message": f"Successfully extracted and analyzed {total_messages} OCR message(s)."}
