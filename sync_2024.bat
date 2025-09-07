@echo off
set TOKEN=ExhGuTVFhkFzTLJ-gNK7
curl -X POST "https://backend-production-aa3c.up.railway.app/api/sync?season=2024" ^
  -H "X-ADMIN-TOKEN: %TOKEN%"
echo.
pause
