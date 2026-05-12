"""
Tool 4: OCR (이미지 텍스트 추출)
=================================
OpenAI GPT-4o Vision API를 사용하여 이미지에서 텍스트를 추출합니다.

기능:
  - extract_text_from_image()   : 단일 이미지 OCR
  - extract_text_from_directory(): 디렉토리 내 전체 이미지 일괄 OCR → .txt 저장

환경변수:
  OPENAI_API_KEY  : OpenAI API 키
  OPENAI_MODEL    : 사용할 모델 (기본: gpt-4o)
"""

import base64
import glob
import logging
import os
from datetime import datetime
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("mcp-server.ocr")

# OpenAI API 설정
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o")

# 지원 이미지 확장자
SUPPORTED_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".tif"
}


def _encode_image_to_base64(image_path: str) -> str:
    """이미지 파일을 Base64 문자열로 인코딩합니다."""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _get_image_mime_type(image_path: str) -> str:
    """파일 확장자로부터 MIME 타입을 결정합니다."""
    ext = Path(image_path).suffix.lower()
    mime_map = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".gif": "image/gif",
        ".bmp": "image/bmp", ".webp": "image/webp",
        ".tiff": "image/tiff", ".tif": "image/tiff",
    }
    return mime_map.get(ext, "image/jpeg")


def extract_text_from_image(image_path: str) -> dict:
    """
    단일 이미지에서 GPT-4o Vision을 사용하여 텍스트를 추출합니다.

    Args:
        image_path: 이미지 파일의 절대 경로

    Returns:
        추출 결과 딕셔너리
    """
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        return {"error": "OPENAI_API_KEY 환경변수가 설정되지 않았습니다."}

    if not os.path.exists(image_path):
        return {"error": f"파일을 찾을 수 없습니다: {image_path}"}

    ext = Path(image_path).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        return {"error": f"지원하지 않는 이미지 형식입니다: {ext}"}

    try:
        base64_image = _encode_image_to_base64(image_path)
        mime_type = _get_image_mime_type(image_path)

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": OPENAI_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "당신은 전문 OCR 엔진입니다. 이미지에서 모든 텍스트를 정확하게 추출하세요.\n"
                        "규칙:\n"
                        "- 원본의 구조(제목, 단락, 목록, 표 등)를 최대한 유지하세요.\n"
                        "- 마크다운 형식으로 출력하세요.\n"
                        "- 텍스트가 없는 경우 '[텍스트 없음]'이라고 응답하세요.\n"
                        "- 이미지 내 도표나 그래프가 있으면 내용을 텍스트로 설명하세요."
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "이 이미지에서 모든 텍스트를 추출해주세요. "
                                    "원본의 레이아웃과 구조를 유지하며 마크다운 형식으로 출력해주세요.",
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{base64_image}",
                                "detail": "high",
                            },
                        },
                    ],
                },
            ],
            "max_tokens": 4096,
            "temperature": 0.1,
        }

        logger.info(f"[OCR] GPT-4o API 호출: {os.path.basename(image_path)}")
        response = httpx.post(
            OPENAI_API_URL,
            headers=headers,
            json=payload,
            timeout=60.0,
        )

        if response.status_code != 200:
            return {
                "error": f"OpenAI API 오류 (HTTP {response.status_code}): {response.text[:500]}",
            }

        result = response.json()
        extracted_text = result["choices"][0]["message"]["content"]

        return {
            "file": os.path.basename(image_path),
            "text": extracted_text,
            "model": OPENAI_MODEL,
            "tokens_used": result.get("usage", {}).get("total_tokens", 0),
        }

    except httpx.TimeoutException:
        return {"error": f"API 요청 시간 초과: {image_path}"}
    except Exception as e:
        return {"error": f"OCR 처리 오류: {str(e)}"}


def extract_text_from_directory(directory_path: str, output_path: str = None) -> dict:
    """
    디렉토리 내 모든 이미지에서 텍스트를 추출하고 파일로 저장합니다.

    Args:
        directory_path: 이미지가 있는 디렉토리 경로
        output_path: 결과를 저장할 텍스트 파일 경로 (None이면 자동 생성)

    Returns:
        처리 결과 딕셔너리
    """
    if not os.path.isdir(directory_path):
        return {"error": f"디렉토리를 찾을 수 없습니다: {directory_path}"}

    # 이미지 파일 목록 수집
    image_files = []
    for ext in SUPPORTED_EXTENSIONS:
        image_files.extend(glob.glob(os.path.join(directory_path, f"*{ext}")))
        image_files.extend(glob.glob(os.path.join(directory_path, f"*{ext.upper()}")))
    image_files = sorted(set(image_files))

    if not image_files:
        return {
            "error": f"디렉토리에 이미지 파일이 없습니다: {directory_path}",
            "supported_formats": list(SUPPORTED_EXTENSIONS),
        }

    # 출력 파일 경로 결정
    if not output_path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(directory_path, f"ocr_result_{timestamp}.txt")

    # 각 이미지 OCR 처리
    results = []
    all_texts = []
    success_count = 0
    error_count = 0

    for i, img_path in enumerate(image_files, 1):
        logger.info(f"[OCR] 처리 중 ({i}/{len(image_files)}): {os.path.basename(img_path)}")

        result = extract_text_from_image(img_path)
        results.append(result)

        if result.get("error"):
            error_count += 1
            all_texts.append(
                f"\n{'='*60}\n"
                f"📄 파일: {os.path.basename(img_path)}\n"
                f"❌ 오류: {result['error']}\n"
            )
        else:
            success_count += 1
            all_texts.append(
                f"\n{'='*60}\n"
                f"📄 파일: {result['file']}\n"
                f"{'='*60}\n\n"
                f"{result['text']}\n"
            )

    # 결과 파일 저장
    combined_text = "\n".join(all_texts)

    header = (
        f"# OCR 추출 결과\n"
        f"# 처리 일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"# 소스 디렉토리: {directory_path}\n"
        f"# 전체 파일: {len(image_files)}개 | 성공: {success_count}개 | 실패: {error_count}개\n"
        f"# OCR 엔진: OpenAI {OPENAI_MODEL}\n"
        f"{'='*60}\n"
    )

    full_content = header + combined_text

    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(full_content)

    return {
        "output_file": output_path,
        "total_images": len(image_files),
        "success_count": success_count,
        "error_count": error_count,
        "processed_files": [os.path.basename(f) for f in image_files],
        "summary": f"{len(image_files)}개 이미지 중 {success_count}개 OCR 완료, 결과 저장: {output_path}",
    }


# ─────────────────────────────────────────────────
# 모듈 단독 실행 테스트
# ─────────────────────────────────────────────────
if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) < 2:
        print("사용법: python ocr.py <이미지파일 또는 디렉토리>")
        sys.exit(1)

    target = sys.argv[1]

    if os.path.isdir(target):
        result = extract_text_from_directory(target)
    else:
        result = extract_text_from_image(target)

    print(json.dumps(result, ensure_ascii=False, indent=2))
