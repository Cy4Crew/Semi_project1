@echo off
echo [*] Building and starting containers...
docker-compose down
docker-compose up -d --build
docker-compose logs -f
pause