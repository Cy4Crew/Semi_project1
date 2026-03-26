@echo off
echo [*] Building and starting containers...
docker compose up -d
docker-compose logs -f
pause
