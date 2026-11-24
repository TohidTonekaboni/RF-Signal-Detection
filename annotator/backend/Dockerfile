FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PYTHONPATH=/srv
WORKDIR /srv

# Dependencies first (cached layer). For an offline build, pass a local wheel mirror:
#   docker build --build-arg PIP_INDEX_URL=http://mirror/simple ...   (or PIP_FIND_LINKS + PIP_NO_INDEX=1)
ARG PIP_INDEX_URL
ARG PIP_FIND_LINKS
ARG PIP_NO_INDEX
COPY pyproject.toml ./
RUN python -c "import tomllib;print('\n'.join(tomllib.load(open('pyproject.toml','rb'))['project']['dependencies']))" > /tmp/req.txt \
 && pip install -r /tmp/req.txt && rm /tmp/req.txt

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app

RUN useradd --system --uid 10001 --no-create-home app
USER app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
