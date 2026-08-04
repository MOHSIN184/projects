# Sveston watch scraper

Scrapes every product in the supplied Shopify collection, following catalog pagination automatically. It creates:

- `output/watches.csv` for Excel or Google Sheets
- `output/watches.json` with complete variants, tags, images, description, availability, and timestamps

Both outputs include the requested name, price, warranty, and features. Warranty defaults to the store-wide **1 Year International Warranty** when a product description does not repeat it.

## Setup and run

```powershell
python -m pip install -r requirements.txt
python scraper.py
```

To scrape another Shopify collection or choose another output directory:

```powershell
python scraper.py "https://example.com/collections/watches" --output my-results
```

The scraper uses Shopify's public collection catalog endpoint and retries temporary network failures. Please run it at a considerate frequency and comply with the site's terms and applicable law.
