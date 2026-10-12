FROM python:3.11-slim
WORKDIR /app
COPY web/requirements.txt /app/web/requirements.txt
RUN pip install --no-cache-dir -r web/requirements.txt
COPY src /app/src
COPY utils /app/utils
COPY web /app/web
RUN useradd --create-home appuser
USER appuser
EXPOSE 8765
CMD ["python", "-m", "web.server", "--host", "0.0.0.0", "--port", "8765"]
