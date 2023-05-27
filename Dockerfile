FROM python:3.9-slim-buster

RUN apt-get update && \
  apt-get -y install --no-install-recommends curl make && \
  rm -rf /var/lib/apt/lists/*

ARG APP_DIR=/var/app

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev

RUN curl -sSL https://install.python-poetry.org | python3 -

ENV PATH="${HOME}/.local/bin:${PATH}"

WORKDIR $APP_DIR

COPY Makefile manage.py poetry.lock pyproject.toml $WORKDIR

RUN make install-packages opts="--no-dev"

COPY account/ /var/app/account/

CMD ["make", "uvicorn-server"]
