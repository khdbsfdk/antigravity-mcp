"""
Tool 5: File Utilities (파일 유틸리티)
=================================
파일 읽기, 디렉토리 목록 조회 등 파일 시스템 작업 도구입니다.
에이전트가 OCR 결과 파일을 읽거나, 디렉토리 내 파일을 탐색할 때 사용합니다.
"""

import logging
import os
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("mcp-server.file_utils")

# 최대 읽기 크기 (1MB)
MAX_READ_SIZE = 1 * 1024 * 1024


def read_text_file(file_path: str) -> dict:
    """
    텍스트 파일의 내용을 읽어 반환합니다.

    Args:
        file_path: 읽을 파일의 절대 경로

    Returns:
        파일 내용을 담은 딕셔너리
    """
    if not os.path.exists(file_path):
        return {"error": f"파일을 찾을 수 없습니다: {file_path}"}

    if not os.path.isfile(file_path):
        return {"error": f"파일이 아닙니다: {file_path}"}

    file_size = os.path.getsize(file_path)
    if file_size > MAX_READ_SIZE:
        return {
            "error": f"파일이 너무 큽니다: {file_size:,} bytes (최대 {MAX_READ_SIZE:,} bytes)",
            "file": file_path,
        }

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        line_count = content.count("\n") + 1

        return {
            "file": os.path.basename(file_path),
            "path": file_path,
            "content": content,
            "size_bytes": file_size,
            "line_count": line_count,
        }
    except UnicodeDecodeError:
        return {"error": f"텍스트 파일이 아닙니다 (바이너리 파일): {file_path}"}
    except Exception as e:
        return {"error": f"파일 읽기 오류: {str(e)}"}


def list_directory_files(directory_path: str, extension_filter: str = None) -> dict:
    """
    디렉토리 내 파일 목록을 조회합니다.

    Args:
        directory_path: 조회할 디렉토리 경로
        extension_filter: 특정 확장자만 필터링 (예: ".txt", ".jpg")

    Returns:
        파일 목록 딕셔너리
    """
    if not os.path.exists(directory_path):
        return {"error": f"디렉토리를 찾을 수 없습니다: {directory_path}"}

    if not os.path.isdir(directory_path):
        return {"error": f"디렉토리가 아닙니다: {directory_path}"}

    try:
        files = []
        dirs = []

        for entry in sorted(os.listdir(directory_path)):
            full_path = os.path.join(directory_path, entry)

            if os.path.isdir(full_path):
                dirs.append({"name": entry, "type": "directory"})
            elif os.path.isfile(full_path):
                ext = Path(entry).suffix.lower()

                if extension_filter and ext != extension_filter.lower():
                    continue

                stat = os.stat(full_path)
                files.append({
                    "name": entry,
                    "type": "file",
                    "size_bytes": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                })

        return {
            "directory": directory_path,
            "total_dirs": len(dirs),
            "total_files": len(files),
            "directories": dirs,
            "files": files,
        }
    except PermissionError:
        return {"error": f"접근 권한이 없습니다: {directory_path}"}
    except Exception as e:
        return {"error": f"디렉토리 조회 오류: {str(e)}"}


# ─────────────────────────────────────────────────
# 모듈 단독 실행 테스트
# ─────────────────────────────────────────────────
if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) < 2:
        print("사용법: python file_utils.py <파일경로 또는 디렉토리경로>")
        sys.exit(1)

    target = sys.argv[1]

    if os.path.isdir(target):
        result = list_directory_files(target)
    else:
        result = read_text_file(target)

    print(json.dumps(result, ensure_ascii=False, indent=2))
