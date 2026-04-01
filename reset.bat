@echo off
echo [*] Stopping containers and removing volumes...
docker compose down -v
echo [*] Done. Database fully reset.
pause