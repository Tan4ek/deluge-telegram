# To start 
```
cp config.ini.example config.ini
# set secrets
vim config.ini
```
# Build on Raspberry Pi 4
`docker build -f Dockerfile.arm64 -t deluge-telegram .`

# Run in Docker
`touch /home/user/db.sqlite3`

`docker run --name deluge-telegram -v '/home/user/db.sqlite3:/app/db.sqlite3' -d deluge-telegram`