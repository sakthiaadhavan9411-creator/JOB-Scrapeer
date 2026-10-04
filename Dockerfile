FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --create-home --uid 10001 alerts
COPY hiring_alerts ./hiring_alerts
COPY config.yaml .
RUN mkdir /app/state && chown alerts:alerts /app/state
USER alerts
VOLUME ["/app/state"]
ENTRYPOINT ["python", "-m", "hiring_alerts"]
CMD ["loop", "--interval", "900"]
