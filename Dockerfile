FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code and assets
COPY . .

# Expose standard application port
EXPOSE 8000

ENV PORT=8000
CMD ["python", "app.py"]
