FROM node:18-alpine AS static

ARG REACT_APP_BACKEND_URL
ENV REACT_APP_BACKEND_URL=$REACT_APP_BACKEND_URL

ARG COMMIT_ID
ENV REACT_APP_COMMIT_ID=$COMMIT_ID

WORKDIR /opt/eadomo

COPY . .

RUN cd web && npm ci --ignore-scripts && npm run build

FROM python:3.10-alpine as static-py

RUN apk add gcc musl-dev libffi-dev

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.txt .
RUN pip3 install -q --no-cache-dir -r requirements.txt

WORKDIR /opt/eadomo
COPY alarms ./alarms/
COPY autodiscovery ./autodiscovery/
COPY checkers ./checkers/
COPY utils ./utils/
COPY eadomo.py README.md Dockerfile_jmx_agent JMXQuery-*.jar LICENSE ./
RUN chmod 755 eadomo.py autodiscovery/autodiscovery.py

FROM python:3.10-alpine as final-image

WORKDIR /opt/eadomo

EXPOSE 5555

COPY --from=static /opt/eadomo/web/build /opt/eadomo/web/build/
COPY --from=static-py /opt /opt

ARG COMMIT_ID
ENV COMMIT_ID=$COMMIT_ID

VOLUME /etc/eadomo.yml

ENV PATH=/opt/venv/bin:/opt/eadomo:/opt/eadomo/autodiscovery:$PATH

CMD eadomo.py /etc/eadomo.yml
