FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY docker-entrypoint.sh /usr/local/bin/apudig-entrypoint
RUN chmod +x /usr/local/bin/apudig-entrypoint

COPY . .

EXPOSE 8000

ENTRYPOINT ["/usr/local/bin/apudig-entrypoint"]
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
