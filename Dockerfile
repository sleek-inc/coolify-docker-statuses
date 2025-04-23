FROM python:3.12-slim AS builder

WORKDIR /app
RUN apt-get update
RUN apt-get install curl build-essential wget -y
RUN curl https://github.com/astral-sh/rye/releases/latest/download/rye-x86_64-linux.gz -L -o /tmp/rye.gz && \
    gunzip /tmp/rye.gz && \
    mv /tmp/rye /usr/local/bin/rye && \
    chmod +x /usr/local/bin/rye
COPY . /app
RUN /usr/local/bin/rye build --wheel --clean

FROM python:3.12-slim

WORKDIR /app
EXPOSE 8080

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update
RUN apt-get install -y locales build-essential
RUN set -ex \
    && ln -s /usr/include/locale.h /usr/include/xlocale.h
RUN sed -i '/en_US.UTF-8/s/^# //g' /etc/locale.gen && \
    locale-gen
ENV LANG=en_US.UTF-8
ENV LANGUAGE=en_US:en
ENV LC_ALL=en_US.UTF-8
RUN rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
COPY --from=builder /app/dist /app/dist

RUN PYTHONDONTWRITEBYTECODE=1 uv pip install --no-cache-dir --system /app/dist/*.whl
RUN apt-get remove -y build-essential && apt-get autoremove -y

COPY pyproject.toml /app/pyproject.toml
COPY bin/run.sh /app/bin/run.sh
RUN chmod +x /app/bin/run.sh

ENTRYPOINT ["/app/bin/run.sh"]