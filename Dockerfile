FROM python:3.11.18-slim-bookworm AS deluge-telegram-build
RUN python3 -m pip install --no-cache-dir --upgrade pip==26.2.2
COPY requirements.txt .
RUN pip3 install --no-cache-dir --user --no-warn-script-location -r requirements.txt

FROM python:3.11.18-slim-bookworm
RUN python3 -m pip install --no-cache-dir --upgrade pip==26.2.2
WORKDIR /app
COPY --from=deluge-telegram-build /root/.local /root/.local

ENV PATH=/root/.local/bin:$PATH
COPY . /app
RUN python3 -m unittest discover -s tests -v

CMD ["python3", "main.py"]
