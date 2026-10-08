FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml ./
COPY app ./app
COPY alembic.ini ./
COPY migrations ./migrations
RUN pip install --no-cache-dir .

# The app never calls pip at runtime. Removing the installer also removes the copies of
# msgpack/urllib3 vendored inside pip that vulnerability scanners flag in the image.
RUN pip uninstall -y pip setuptools wheel

# Run as an unprivileged user. The API writes nothing to disk, so no chown is needed.
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin app
USER 10001

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

