FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py config.py question_bank.py utils.py api_docs.md logo.png ./
COPY static/ ./static/
COPY templates/index.html ./templates/index.html

EXPOSE 5000
# JSON persistence and in-memory state require a single worker process.
CMD ["gunicorn", "--workers", "1", "--threads", "4", "--bind", "0.0.0.0:5000", "--limit-request-line", "16380", "app:app"]
