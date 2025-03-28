FROM python:3.10-slim

# Install Java for Lavalink
RUN apt-get update && \
    apt-get install -y openjdk-17-jre-headless && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Create and set working directory
WORKDIR /app

# Copy Lavalink files
COPY Lavalink.jar .
COPY application.yml .

# Copy Python requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy bot files
COPY . .

# Start both Lavalink and the bot
CMD java -jar Lavalink.jar & python bot.py 