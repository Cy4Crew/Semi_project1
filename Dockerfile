FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# 🔥 먼저 시스템 라이브러리 설치
RUN apt-get update && apt-get install -y \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libxcomposite1 libxdamage1 libxrandr2 libgbm1 \
    libasound2 libpangocairo-1.0-0 libpango-1.0-0 \
    libgtk-3-0

# 🔥 그 다음 playwright 브라우저 설치
RUN playwright install chromium

COPY . .

CMD ["python", "run.py", "all"]