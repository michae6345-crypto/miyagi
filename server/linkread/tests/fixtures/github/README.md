<!-- badges -->
[![CI](https://github.com/acme-labs/tinyhttp/actions/workflows/ci.yml/badge.svg)](https://github.com/acme-labs/tinyhttp/actions) [![PyPI](https://img.shields.io/pypi/v/tinyhttp.svg)](https://pypi.org/project/tinyhttp/)

<p align="center">
  <img src="docs/logo.png" alt="tinyhttp logo" width="200">
</p>

# tinyhttp

**tinyhttp** is a small, friendly HTTP client for Python. It sends requests, follows redirects
and decodes JSON, with an API you can learn in five minutes.

![Screenshot of a request](docs/screenshot.png)

## Installation

Install it from PyPI:

```bash
pip install tinyhttp
```

## Quick start

1. Import the client.
2. Send a request.
3. Read the JSON.

```python
import tinyhttp

resp = tinyhttp.get("https://api.example.com/items")
print(resp.status, resp.json()[0]["name"])
```

### Sending data

    tinyhttp.post(url, json={"name": "lamp"})

| Method | What it does |
|--------|--------------|
| `get`  | Reads a resource |
| `post` | Creates one |

## Documentation

See the [docs folder](docs/) and the [quick start guide][qs].

[qs]: docs/quickstart.md

## License

MIT
