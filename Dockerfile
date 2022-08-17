FROM python:3.8 as deluge-telegram-build
COPY requirements.txt .
RUN pip3 install --no-cache-dir --user --no-warn-script-location -r requirements.txt

FROM python:3.8-alpine
WORKDIR /app
COPY --from=deluge-telegram-build /root/.local /root/.local

ENV PATH=/root/.local/bin:$PATH
RUN apk update && apk upgrade --available \
    && apk add --no-cache make

COPY . /app

CMD ["python3", "main.py"]