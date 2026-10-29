FROM python:3.11.18-slim-bookworm AS deluge-telegram-build
COPY requirements.txt .
RUN pip3 install --no-cache-dir --user --no-warn-script-location -r requirements.txt

FROM python:3.11.18-slim-bookworm
WORKDIR /app
COPY --from=deluge-telegram-build /root/.local /root/.local

ENV PATH=/root/.local/bin:$PATH
COPY . /app
RUN python3 -m unittest discover -s tests -v

CMD ["python3", "main.py"]
