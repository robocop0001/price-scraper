"""
This document queries the Woolworths Products API hosted on X-Rapid-API.
For the initial release, the following products are queried:
Truss tomatoes, Calypso mangoes, Milk 3L, Wholemeal Bread, Lebanese Cucumbers
"""

import http.client
from dotenv import load_dotenv
load_dotenv()

import os

print(os.getenv('XRapidAPIKey', default='fail !!'))