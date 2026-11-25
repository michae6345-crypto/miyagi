import pandas as pd
import requests

print(pd.DataFrame(requests.get("https://example.com/forecast.json", timeout=5).json()))
