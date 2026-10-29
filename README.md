# Security/runtime requirements

Rebuild the image to pick up Python 3.11.18 and the corrected certifi trust
bundle after the October 2026 eMudhra incident. Both stages now use Debian;
copying packages between the old Debian builder and Alpine runtime is avoided.
Both stages update pip to 26.2.2. The image build runs offline runtime/TLS
checks before publishing.

Python 3.11 preserves the legacy Telegram API's `imghdr` and this project's
`distutils` imports. APScheduler 3.6.3 still requires `pkg_resources`, so
setuptools is temporarily pinned to 81.0.0. Its remaining Windows legacy wheel
installation and macOS source-distribution advisories are not exercised by
this Linux runtime. A later Telegram/APScheduler migration is still needed;
do not use this environment to build or publish untrusted packages.

This update protects Telegram HTTPS trust. The existing deluge-client 1.9.0
does not authenticate the Deluge RPC server certificate, so keep RPC on a
trusted network or authenticated tunnel. The Telegram library's bundled
urllib3 copy is outside the package-version audit.

# To start 
```
cp config.ini.example config.ini
# set secrets
vim config.ini
```
# Build on Raspberry Pi 4
```
cp ./Dockerfile ./Dockerfile.arm64 && sed -i 's/FROM python:/FROM arm64v8\/python:/' ./Dockerfile.arm64
docker build -f Dockerfile.arm64 -t deluge-telegram .
```

# Run in Docker
`touch /home/user/db.sqlite3`

`docker run --name deluge-telegram -v '/home/user/db.sqlite3:/app/db.sqlite3' -d --restart unless-stopped --rm deluge-telegram`
