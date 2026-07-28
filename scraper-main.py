import csv
import json
import math
import os
import re
from collections import Counter
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

import requests
from dotenv import load_dotenv


PROJECT_DIR = Path(__file__).resolve().parent
PRODUCTS_FILE = PROJECT_DIR / 'products.json'
CSV_FILE = PROJECT_DIR / 'data.csv'
CSV_COLUMNS = [
    'store', 'item_name', 'item_price', 'item_weight_kg', 'alias',
    'similarity_score', 'similarity_rank', 'date',
]
TOP_MATCHES_PER_STORE = 2

# Explicitly locating .env is important when this module is imported by tests or
# launched from a directory other than the project directory.
load_dotenv(PROJECT_DIR / '.env')

with PRODUCTS_FILE.open('r', encoding='utf-8') as file:
    PRODUCTS = json.load(file)

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/150.0.0.0 Safari/537.36 '
    ),
    'Accept-Language': 'en-US,en-AU;q=0.9;',
}


def debug(message: str) -> None:
    """Print a diagnostic line without ever including API credentials."""
    print(f'[scraper] {message}')


def preview(value, limit: int = 240) -> str:
    """Keep diagnostics useful when an API field contains a large HTML blob."""
    text = repr(value).replace('\n', ' ')
    return text if len(text) <= limit else f'{text[:limit - 3]}...'


def _bag_of_words(text: str) -> Counter:
    """Create a lightly normalised term-frequency vector for product names."""
    normalised = str(text).lower()
    normalised = re.sub(r'(?<=\d)(?=[a-z])|(?<=[a-z])(?=\d)', ' ', normalised)
    normalised = normalised.replace('×', ' x ')
    tokens = re.findall(r'[a-z0-9]+', normalised)
    unit_aliases = {
        'litre': 'l', 'litres': 'l', 'liter': 'l', 'liters': 'l',
        'kilogram': 'kg', 'kilograms': 'kg', 'grams': 'g', 'millilitres': 'ml', 'milliliters': 'ml',
    }
    return Counter(unit_aliases.get(token, token) for token in tokens)


def cosine_similarity(left: str, right: str) -> float:
    """Return bag-of-words cosine similarity in the inclusive range 0.0–1.0."""
    left_vector = _bag_of_words(left)
    right_vector = _bag_of_words(right)
    if not left_vector or not right_vector:
        return 0.0
    dot_product = sum(count * right_vector[token] for token, count in left_vector.items())
    left_magnitude = math.sqrt(sum(count ** 2 for count in left_vector.values()))
    right_magnitude = math.sqrt(sum(count ** 2 for count in right_vector.values()))
    return round(dot_product / (left_magnitude * right_magnitude), 4)


class BaseStore:
    store_name = 'Store'
    query_key = 'query'
    endpoint = ''
    headers = HEADERS
    params = {}

    def get_request(self, query: str):
        raise NotImplementedError

    def process_request(self, payload, alias: str):
        raise NotImplementedError

    @staticmethod
    def _parse_weight(value):
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value).strip().lower()
        if not text:
            return None

        # Supports both a single size ("500g") and packs ("3 x 500g").
        match = re.search(
            r'(?:(\d+(?:\.\d+)?)\s*[x×]\s*)?'
            r'(\d+(?:\.\d+)?)\s*(kg|g|ml|l|litres|litre|liters|liter)\b',
            text,
        )
        if not match:
            return None
        multiplier = float(match.group(1) or 1)
        amount = float(match.group(2)) * multiplier
        unit = match.group(3)
        if unit in {'g', 'ml'}:
            amount /= 1000
        return round(amount, 3)

    @staticmethod
    def _parse_price(value):
        if value is None:
            return None
        if isinstance(value, dict):
            for key in ('value', 'amount', 'price', 'current', 'formattedValue'):
                if key in value and value[key] is not None:
                    return BaseStore._parse_price(value[key])
            return None
        if isinstance(value, (int, float)):
            # RapidAPI commonly returns prices as cents.  Do not divide a
            # decimal price such as 15.99.
            number = float(value)
            return round(number / 100, 2) if number >= 100 and number.is_integer() else round(number, 2)
        text = str(value).strip()
        if not text:
            return None
        if text.startswith('$'):
            text = text[1:]
        if ',' in text and '.' in text:
            text = text.replace(',', '')
        elif ',' in text:
            text = text.replace(',', '.')
        match = re.search(r'([0-9]+(?:\.[0-9]+)?)', text)
        return round(float(match.group(1)), 2) if match else None

    @staticmethod
    def _first_value(item, paths):
        """Return the first present value from a sequence of dotted paths."""
        for path in paths:
            value = item
            for key in path.split('.'):
                if not isinstance(value, dict) or key not in value:
                    break
                value = value[key]
            else:
                if value not in (None, ''):
                    return value
        return None

    def _first_parseable_value(self, item, paths, parser):
        """Try each source because a present field may still be unusable."""
        for path in paths:
            value = self._first_value(item, (path,))
            parsed = parser(value)
            if parsed is not None:
                return value, parsed
        return None, None

    @staticmethod
    def _normalise_record(store_name, item_name, item_price, item_weight_kg, alias):
        return {
            'store': store_name,
            'item_name': item_name,
            'item_price': item_price,
            'item_weight_kg': item_weight_kg,
            'alias': alias,
            'similarity_rank': None,
            'date': date.today().isoformat(),
        }

    def _products_from_payload(self, payload):
        if not isinstance(payload, dict):
            debug(f'{self.store_name}: expected a JSON object, received {type(payload).__name__}.')
            return []
        for path in ('products', 'results', 'items', 'data.products', 'data.items', 'data.results'):
            products = self._first_value(payload, (path,))
            if isinstance(products, list):
                debug(f'{self.store_name}: found {len(products)} products at payload.{path}.')
                return products
        debug(f'{self.store_name}: no product list found; top-level keys={list(payload)[:15]}.')
        return []

    def _records_from_payload(self, payload, alias: str):
        products = self._products_from_payload(payload)
        records = []
        missing_price = missing_weight = invalid_products = 0
        for index, item in enumerate(products):
            if not isinstance(item, dict):
                invalid_products += 1
                continue
            name = self._first_value(item, (
                'name', 'title', 'displayName', 'productName', 'product_name', 'englishName',
            )) or 'Unknown'
            raw_price, price = self._first_parseable_value(item, (
                'price', 'price.value', 'price.amount', 'price.formattedValue',
                'salePrice', 'salePrice.value', 'currentPrice', 'currentPrice.value',
                'current_price', 'pricePerUnit', 'unitPrice', 'pricing.price',
            ), self._parse_price)
            raw_weight, weight = self._first_parseable_value(item, (
                'weight', 'size', 'product_size', 'packageSize', 'netContent', 'unitSize', 'sellingSize',
                'name', 'title', 'displayName', 'productName', 'product_name', 'englishName', 'description',
            ), self._parse_weight)
            missing_price += price is None
            missing_weight += weight is None
            if index == 0:
                debug(
                    f'{self.store_name}: first product keys={list(item)[:20]}; '
                    f'price_source={preview(raw_price)}; weight_source={preview(raw_weight)}.'
                )
            similarity_score = cosine_similarity(alias, name)
            records.append(self._normalise_record(
                self.store_name, name, price, weight, alias,
            ))
        records.sort(key=lambda record: (-record['similarity_score'], record['item_name'].lower()))
        selected_records = records[:TOP_MATCHES_PER_STORE]
        for rank, record in enumerate(selected_records, start=1):
            record['similarity_rank'] = rank
        debug(
            f'{self.store_name}: selected {len(selected_records)} of {len(records)} candidates for {alias!r}; '
            f'missing price={missing_price}, missing weight={missing_weight}, invalid products={invalid_products}; '
            f'matches={[(record["item_name"], record["similarity_score"]) for record in selected_records]}.'
        )
        return selected_records

    def write_csv(self, rows):
        with CSV_FILE.open('w', newline='', encoding='utf-8') as file:
            writer = csv.DictWriter(file, fieldnames=CSV_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        debug(f'Wrote {len(rows)} rows to {CSV_FILE}.')


class RapidAPIStore(BaseStore):
    api_key_env = ''
    api_host_env = ''

    def __init__(self):
        self.headers = {
            'X-RapidAPI-Key': os.getenv(self.api_key_env, ''),
            'X-RapidAPI-Host': os.getenv(self.api_host_env, ''),
        }

    def get_request(self, query: str):
        return requests.get(self.endpoint, params={self.query_key: query}, headers=self.headers, timeout=30)

    def is_configured(self):
        return bool(self.headers['X-RapidAPI-Key'] and self.headers['X-RapidAPI-Host'])


class ColesStore(RapidAPIStore):
    store_name = 'Coles'
    endpoint = os.getenv('ColesAPIEndpoint', 'https://coles-product-price-api.p.rapidapi.com/coles/product-search/')
    api_key_env = 'ColesAPIKey'
    api_host_env = 'ColesAPIHost'

    def process_request(self, payload, alias: str):
        return self._records_from_payload(payload, alias)


class WoolworthsStore(RapidAPIStore):
    store_name = 'Woolworths'
    endpoint = os.getenv('WoolworthsAPIEndpoint', 'https://woolworths-products-api.p.rapidapi.com/woolworths/product-search')
    api_key_env = 'WoolworthsAPIKey'
    api_host_env = 'WoolworthsAPIHost'

    def process_request(self, payload, alias: str):
        return self._records_from_payload(payload, alias)


class AldiStore(BaseStore):
    store_name = 'Aldi'
    endpoint = 'https://api.aldi.com.au/v3/product-search-suggestion'
    query_key = 'q'

    def get_request(self, query: str):
        return requests.get(self.endpoint, params={'serviceType': 'walk-in', 'q': query}, headers=HEADERS, timeout=30)

    def process_request(self, payload, alias: str):
        return self._records_from_payload(payload, alias)


class CostcoStore(BaseStore):
    store_name = 'Costco'
    endpoint = 'https://www.costco.com.au/rest/v2/australia/products/search'
    params = {
        'fields': 'FULL', 'pageSize': 100, 'searchOption': 'au-search-bd',
        'lang': 'en_AU', 'curr': 'AUD',
    }

    def get_request(self, query: str):
        params = {**self.params, self.query_key: query}
        return requests.get(self.endpoint, params=params, headers=HEADERS, timeout=30)

    def process_request(self, payload, alias: str):
        return self._records_from_payload(payload, alias)


def run_store(store, query: str, alias: str):
    if isinstance(store, RapidAPIStore) and not store.is_configured():
        raise RuntimeError(
            f'missing {store.api_key_env} or {store.api_host_env} in {PROJECT_DIR / ".env"}; request not sent'
        )
    endpoint = urlsplit(store.endpoint)
    debug(f'{store.store_name}: requesting {endpoint.netloc}{endpoint.path} with {store.query_key}={query!r}.')
    response = store.get_request(query)
    debug(f'{store.store_name}: response status={response.status_code}, bytes={len(response.content)}, url={response.url}.')
    if not response.ok:
        raise RuntimeError(f'HTTP {response.status_code}: {response.text[:300]}')
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(f'response was not valid JSON: {response.text[:300]}') from exc
    if isinstance(payload, dict):
        debug(f'{store.store_name}: response top-level keys={list(payload)[:20]}.')
    return store.process_request(payload, alias)


def main():
    stores = [ColesStore(), WoolworthsStore(), AldiStore(), CostcoStore()]
    rows = []
    for alias in PRODUCTS:
        debug(f'Processing product alias={alias!r}.')
        for store in stores:
            try:
                # The retailer name is not part of a catalogue search term.
                records = run_store(store, alias, alias)
            except Exception as exc:
                debug(f'{store.store_name}: failed for {alias!r}: {type(exc).__name__}: {exc}')
                continue
            rows.extend(records)
    if not rows:
        debug('No records were collected; data.csv was left unchanged.')
        return
    BaseStore().write_csv(rows)
    by_store = {store.store_name: sum(row['store'] == store.store_name for row in rows) for store in stores}
    debug(f'Run complete: {len(rows)} rows. Rows by store: {by_store}.')


if __name__ == '__main__':
    main()
