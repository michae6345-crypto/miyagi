# tasky

A tiny to-do list for the terminal, written as a teaching project. Everything lives in one file, `tasky.py`, so you
can read the whole program in five minutes and build it yourself from this README.

## Build it yourself

### 1. Store tasks

Tasks are a list of dictionaries, saved as JSON next to the script:

```python
# tasky.py
import json
from pathlib import Path

DB = Path("tasks.json")

def load():
    return json.loads(DB.read_text()) if DB.exists() else []

def save(tasks):
    DB.write_text(json.dumps(tasks, indent=2))
```

### 2. Add and list

```python
def add(text):
    tasks = load()
    tasks.append({"text": text, "done": False})
    save(tasks)

def show():
    for i, t in enumerate(load(), 1):
        mark = "x" if t["done"] else " "
        print(f"{i}. [{mark}] {t['text']}")
```

### 3. Mark a task done

```python
def done(n):
    tasks = load()
    tasks[n - 1]["done"] = True
    save(tasks)
```

### 4. The command line

```python
import sys

if __name__ == "__main__":
    cmd, *rest = sys.argv[1:] or ["show"]
    if cmd == "add":
        add(" ".join(rest))
    elif cmd == "done":
        done(int(rest[0]))
    show()
```

### 5. Try it

```console
$ python3 tasky.py add "water the plants"
1. [ ] water the plants
$ python3 tasky.py done 1
1. [x] water the plants
```

## License

MIT. Copy it, change it, teach with it.
