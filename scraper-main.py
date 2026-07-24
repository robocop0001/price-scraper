import csv
import time
import pandas as pd
import requests
import bs4 as BeautifulSoup
import json

ALDI = {
    'name': 'Aldi',
    'url': "https://api.aldi.com.au/v3/product-search-suggestion",
    'params': {
        'serviceType': 'walk-in',
        'q': None
    },
}

# browser headers to prevent a 403 forbidden
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/150.0.0.0 Safari/537.36 "
    ),
    "Accept-Language": "en-US,en-AU;q=0.9;"
}

with open('products.json', 'r') as file:
    products = json.load(file)


def send_request(store: dict) -> None:
    # if not store or product or store['url']:
    #     raise AttributeError(f"One of the following\nStore: {store}\nProduct: {product}\nURL: {store['url']} is incorrect.")

    print(f"Connecting to {store['url']}...")

    # iterate through products.json -- add homebrand into the front of the query string
    for product in products:
        store['params']['q'] = f"{store['name']} {product}"
        print(store['params']['q'])
        response = requests.get(url=store['url'], params=store['params'], headers=HEADERS)
        print(f"Verifying status: {response.status_code} and response {response.content}")

    return

def process_request(request, store=None):
    if not store:
        raise TypeError('Error in store parameter! Exiting.')
    
    return

def main():
    for product in products:
        print(product)
    send_request(ALDI)

    return None


if __name__ == "__main__":
    main()