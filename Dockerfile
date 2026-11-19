FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN python manage.py collectstatic --noinput \
    && addgroup --system --gid 10001 app \
    && adduser --system --uid 10001 --ingroup app app \
    && mkdir -p /data \
    && chown -R app:app /app /data

USER app
EXPOSE 8000
CMD ["sh", "-c", "python manage.py migrate && (python manage.py createsuperuser --noinput || true) && exec gunicorn edutrack.wsgi:application --bind 0.0.0.0:${PORT:-8000}"]
