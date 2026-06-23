FROM python:3.11-slim

WORKDIR /app

COPY api/requirements.txt ./api/requirements.txt

RUN pip install --no-cache-dir torch==2.2.1 --index-url https://download.pytorch.org/whl/cpu

RUN pip install --no-cache-dir --timeout 300 -r api/requirements.txt

RUN python -m spacy download en_core_web_sm || \
    pip install --no-cache-dir https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.7.1/en_core_web_sm-3.7.1-py3-none-any.whl
COPY api/ ./api/

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]