FROM python:3.12-slim-bullseye AS build
WORKDIR /dubois

RUN pip3 install --no-cache-dir --upgrade pip

FROM python:3.12-slim-bullseye
WORKDIR /dubois

ARG VCS_REF=
ARG VERSION_TAG=

ENV DUBOIS_ENV=docker

LABEL org.label-schema.name="DuBois" \
      org.label-schema.version=$VERSION_TAG

COPY . /src
RUN pip3 install --no-cache-dir /src

WORKDIR /dubois

ENTRYPOINT ["dubois"]
