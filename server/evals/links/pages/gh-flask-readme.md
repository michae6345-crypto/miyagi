<div align="center"><img src="https://example.org/flask-logo.png" alt="" height="200"></div>

# Flask

[![PyPI](https://img.shields.io/pypi/v/flask)](https://pypi.org/project/flask/) [![Chat](https://img.shields.io/badge/chat-discord-blue)](https://discord.example.org)

Flask is a lightweight web application framework. It is designed to make getting started quick and easy, with the
ability to scale up to complex applications. It began as a simple wrapper around Werkzeug and Jinja and has become one
of the most popular Python web application frameworks.

Flask offers suggestions, but doesn't enforce any dependencies or project layout. It is up to the developer to choose
the tools and libraries they want to use.

## Installing

Install and update from PyPI:

```bash
pip install -U Flask
```

## A Simple Example

Save this as `app.py`:

```python
# save this as app.py
from flask import Flask

app = Flask(__name__)

@app.route("/")
def hello():
    return "Hello, World!"
```

Then run it:

```console
$ flask run
  * Running on http://127.0.0.1:5000/ (Press CTRL+C to quit)
```

## Donate

The Pallets organization develops and supports Flask and the libraries it uses. In order to grow the community of
contributors and users, and allow the maintainers to devote more time to the projects, please donate today.

## Contributing

See our detailed contributing documentation for many ways to contribute, including reporting issues, requesting
features, asking or answering questions, and making PRs.
