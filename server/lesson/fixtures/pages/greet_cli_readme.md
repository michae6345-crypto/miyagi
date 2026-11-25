# greet-cli

[![CI](https://example.com/badge.svg)](https://example.com/ci) ![coverage](https://example.com/cov.svg)

A tiny command-line greeter, written to show how a Python script grows into a small CLI.
<p align="center"><img src="docs/logo.png" alt="logo"></p>

## Installing

Make a virtual environment, then install the one dependency:

```bash
python3 -m venv .venv
pip install click
```

## Your first greeting

Create `greet.py` with a function that builds the message:

```python
def greeting(name):
    return f"Hello, {name}!"
```

## Make it a command

Wrap it in a [click](https://click.palletsprojects.com) command so the name comes from the terminal:

```python
import click

@click.command()
@click.argument("name")
def main(name):
    click.echo(greeting(name))

if __name__ == "__main__":
    main()
```

```console
$ python3 greet.py Ada
Hello, Ada!
```

## Make it a command

(A second heading with the same words, to check GitHub's -1 anchors.)

## Contributing

Pull requests are welcome. # not a heading: inside a paragraph

```python
# a comment in code, never a heading
print("tests")
```
