FROM python:3.10-slim

# Create and set working directory
WORKDIR /app

# Copy Python requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy bot files
COPY . .

# Set environment variable to indicate this is a worker
ENV IS_WORKER=true

# Start the bot
ENTRYPOINT ["python", "bot.py"] 