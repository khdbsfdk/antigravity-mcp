# ============================================================
# Dockerfile - MCP Tools Server
# ============================================================
# 빌드:   docker build -t mcp-tools-server:latest .
# 실행:   docker run -p 8080:8080 --env-file .env mcp-tools-server:latest
# ============================================================

FROM python:3.11-slim

# 메타데이터
LABEL maintainer="mcp-team"
LABEL description="MCP Tools Server - calculator, datetime, weather"
LABEL version="1.0.0"

# 작업 디렉토리 설정
WORKDIR /app
# PYTHONPATH를 명확히 /app으로 지정 (server.tools.* 임포트 보장)
ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1

# 시스템 패키지 설치 (최소화)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Python 의존성 먼저 복사 (레이어 캐시 활용)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스 코드 복사
COPY server/ ./server/
COPY client/ ./client/

# OpenShift random UID 대응: 파일/디렉토리를 root 그룹(0) 소유로 설정하고 그룹 읽기 권한 부여
# (SCC restricted-v2: 임의 UID + root 그룹으로 실행됨)
RUN chown -R root:root /app \
    && chmod -R g=u /app

# 포트 노출 (HTTP 모드)
EXPOSE 8080

# 헬스체크
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# 실행 (HTTP 모드 - PYTHONPATH=/app 이므로 server.tools.* 임포트 정상 동작)
CMD ["python", "/app/server/server.py", "--transport", "http", "--host", "0.0.0.0", "--port", "8080"]
