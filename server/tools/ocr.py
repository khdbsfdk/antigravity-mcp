import logging
import os
import time  # 속도 제한 대응을 위해 추가
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("mcp-server.ocr")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

def extract_text_from_image(image_path: str) -> dict:
    """단일 이미지 OCR 수행"""
    if not client:
        return {"error": "GEMINI_API_KEY가 설정되지 않았습니다.", "success": False, "output_file": None}
    
    try:
        with open(image_path, "rb") as f:
            image_data = f.read()
        
        response = client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=[
                "이미지 내 모든 텍스트를 마크다운 형식으로 추출하세요.",
                types.Part.from_bytes(data=image_data, mime_type="image/jpeg")
            ]
        )
        
        return {
            "file": os.path.basename(image_path),
            "text": response.text,
            "success": True,
            "output_file": None  # 키 누락 에러 방지
        }
    except Exception as e:
        logger.error(f"OCR 실패: {str(e)}")
        return {"file": os.path.basename(image_path), "error": str(e), "success": False, "output_file": None}

def extract_text_from_directory(directory_path: str, output_path: str = "images/ocr_result.txt") -> dict:
    """디렉토리 일괄 처리 (서버가 찾는 모든 키값 포함 + 속도 제한 대응)"""
    if not os.path.isdir(directory_path):
        return {"error": "디렉토리 없음", "total_images": 0, "success_count": 0, "output_file": output_path}
    
    files = [f for f in os.listdir(directory_path) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
    results = []
    success_count = 0

    for i, filename in enumerate(files):
        # 무료 티어 429 에러 방지: 이미지 한 장당 4초씩 쉽니다 (분당 15회 제한 준수)
        if i > 0:
            logger.info("속도 제한(RPM) 준수를 위해 4초간 대기합니다...")
            time.sleep(4)
            
        res = extract_text_from_image(os.path.join(directory_path, filename))
        results.append(res)
        if res.get("success"):
            success_count += 1
    
    # 텍스트 파일 저장
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(f"# OCR 결과 (총 {len(files)}개 중 {success_count}개 성공)\n\n")
            for r in results:
                f.write(f"--- {r['file']} ---\n{r.get('text', r.get('error'))}\n\n")
    except Exception as e:
        logger.error(f"파일 저장 실패: {str(e)}")

    # 핵심: 서버 프레임워크가 찾는 'output_file', 'success_count' 키를 반드시 포함
    return {
        "status": "success",
        "total_images": len(files),
        "success_count": success_count,
        "fail_count": len(files) - success_count,
        "output_file": output_path, # 이 키가 없어서 에러가 났던 것입니다!
        "results": results
    }
