FROM python:3.11-slim

# Без буферизации, иначе `docker compose logs -f` показывает вывод с задержкой
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Сначала зависимости — лучше кешируется
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py ./

# Секреты и состояние подключаются как volume в docker-compose (папка /app/data)
CMD ["python", "main.py", "--loop"]
