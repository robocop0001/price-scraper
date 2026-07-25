import importlib.util
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / 'scraper-main.py'
SPEC = importlib.util.spec_from_file_location('scraper_main', MODULE_PATH)
scraper = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(scraper)


class StoreParserTests(unittest.TestCase):
    def test_costco_parser_converts_price_and_weight(self):
        payload = {
            'products': [
                {
                    'name': 'Kirkland Signature Full Cream Milk 3L',
                    'price': {'value': 1599},
                    'weight': '3kg',
                }
            ]
        }

        records = scraper.CostcoStore().process_request(payload, alias='full cream milk 3 litres')

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['store'], 'Costco')
        self.assertEqual(records[0]['item_name'], 'Kirkland Signature Full Cream Milk 3L')
        self.assertEqual(records[0]['item_price'], 15.99)
        self.assertEqual(records[0]['item_weight_kg'], 3.0)
        self.assertEqual(records[0]['alias'], 'full cream milk 3 litres')

    def test_coles_and_woolworths_parsers_handle_different_payloads(self):
        coles = scraper.ColesStore().process_request(
            {'products': [{'name': 'Kraft Singles', 'price': {'value': 499}, 'weight': '200g'}]},
            alias='kraft singles',
        )
        woolworths = scraper.WoolworthsStore().process_request(
            {'products': [{'name': 'Kraft Singles', 'price': '$3.99', 'weight': '250g'}]},
            alias='kraft singles',
        )

        self.assertEqual(coles[0]['item_price'], 4.99)
        self.assertEqual(coles[0]['item_weight_kg'], 0.2)
        self.assertEqual(woolworths[0]['item_price'], 3.99)
        self.assertEqual(woolworths[0]['item_weight_kg'], 0.25)

    def test_parser_supports_nested_results_and_product_name_weight_fallback(self):
        records = scraper.CostcoStore().process_request(
            {
                'data': {
                    'results': [
                        {
                            'displayName': 'Example Coffee 3 x 500g',
                            'salePrice': {'formattedValue': '$18.50'},
                        }
                    ]
                }
            },
            alias='coffee',
        )

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['item_price'], 18.50)
        self.assertEqual(records[0]['item_weight_kg'], 1.5)

    def test_price_parser_does_not_treat_decimal_dollars_as_cents(self):
        self.assertEqual(scraper.BaseStore._parse_price(15.99), 15.99)
        self.assertEqual(scraper.BaseStore._parse_price(1599), 15.99)

    def test_parser_tries_later_fields_when_the_first_price_field_is_empty(self):
        records = scraper.CostcoStore().process_request(
            {
                'products': [
                    {
                        'name': 'Example yoghurt 1kg',
                        'price': {'value': None},
                        'salePrice': {'value': 799},
                    }
                ]
            },
            alias='yoghurt',
        )

        self.assertEqual(records[0]['item_price'], 7.99)
        self.assertEqual(records[0]['item_weight_kg'], 1.0)

    def test_parser_handles_the_live_rapidapi_snake_case_fields(self):
        records = scraper.ColesStore().process_request(
            {
                'results': [
                    {
                        'product_name': 'Milk 3L',
                        'current_price': '$4.50',
                        'product_size': '3L',
                    }
                ]
            },
            alias='milk',
        )

        self.assertEqual(records[0]['item_name'], 'Milk 3L')
        self.assertEqual(records[0]['item_price'], 4.50)
        self.assertEqual(records[0]['item_weight_kg'], 3.0)


if __name__ == '__main__':
    unittest.main()
