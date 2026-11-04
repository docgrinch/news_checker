# news-checker

Cybersecurity news from several RSS feeds: title, the first lines of each article, and a link to the full article. No API keys, no external services besides the feeds themselves.

```sh
docker build -t news-checker .
docker run -d -p 8000:8000 --name news news-checker
# open http://localhost:8000
```

Env vars: `REFRESH_MINUTES` (30), `PER_FEED` (8), `PORT` (8000).
Sources are the `FEEDS` dict at the top of `app.py`.

## Portainer

`compose.yaml` builds the image from this folder. In Portainer, go to **Stacks → Add stack → Repository**,
point it at this repo (compose path `compose.yaml`), and deploy. Portainer builds the image itself.

Using the **Web editor** instead? It can't build, so first run `docker build -t news-checker .` on the
Docker host, then paste `compose.yaml` without the `build: .` line.
