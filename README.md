# To start 
```
cp config.ini.example config.ini
# set secrets
vim config.ini
```
# Build on Raspberry Pi 4
`docker build -f Dockerfile.arm64 -t deluge-telegram .`