FROM python:3.11-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \ 
    PYTHONPATH=/app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    poppler-utils \
 && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml /app/pyproject.toml
RUN pip install --no-cache-dir -U pip \
 && pip install --no-cache-dir -e .

RUN python -m pip install --no-cache-dir "pypdf>=4.0.0" \
 && python -c "import pypdf; print('pypdf_build_ok', pypdf.__version__)"

COPY app /app/app
COPY tests /app/tests

EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]

