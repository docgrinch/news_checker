FROM debian:trixie-slim
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-feedparser ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY app.py test_app.py ./
RUN python3 -m unittest test_app
USER nobody
EXPOSE 8000
CMD ["python3", "app.py"]
