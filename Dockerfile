FROM python:3.10-slim

# Create and set working directory
WORKDIR /app

# Copy Python requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy bot files
COPY . .

# Start the bot
CMD ["python", "bot.py"] 