# Sideline MCP server. Build for App Runner with:
#   docker build --platform linux/amd64 -t sideline .
# (--platform matters on Apple Silicon: App Runner runs amd64.)
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    SIDELINE_HOST=0.0.0.0 \
    SIDELINE_PORT=8765

WORKDIR /app
COPY requirements.txt .
# cryptography is for RS256 token verification (SIDELINE_AUTH=required).
RUN pip install --no-cache-dir -r requirements.txt cryptography

COPY sideline ./sideline
COPY data ./data
COPY simulator ./simulator
COPY run.py .

# The server holds no state that matters on disk; run unprivileged.
RUN useradd --system --no-create-home sideline
USER sideline

EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=3s CMD \
  python -c "import urllib.request,os;urllib.request.urlopen('http://127.0.0.1:%s/health'%os.environ.get('SIDELINE_PORT','8765'),timeout=2)"

CMD ["python", "run.py"]
