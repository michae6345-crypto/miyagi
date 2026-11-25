# Quick start guide

This guide walks you through your first three requests.

## Make a GET request

```python
resp = tinyhttp.get("https://api.example.com/items", timeout=5)
```

## Handle errors

```python
try:
    resp.raise_for_status()
except tinyhttp.HTTPError as err:
    print("failed:", err)
```
