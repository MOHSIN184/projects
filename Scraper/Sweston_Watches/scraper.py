"""Scrape every watch in a Shopify collection to CSV and JSON."""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


DEFAULT_COLLECTION = "https://en-pk.svestonwatches.com/collections/best-sellers"
WARRANTY_RE = re.compile(
    r"\b(?:\d+|one|two|three)\s*[- ]?(?:year|month)s?\b.{0,45}\b(?:international\s+)?warranty\b"
    r"|\b(?:international\s+)?warranty\b.{0,45}\b(?:\d+|one|two|three)\s*[- ]?(?:year|month)s?\b",
    re.IGNORECASE,
)


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip(" \t\r\n:-|•")


def price_value(value: int | float | str | None) -> Decimal | None:
    """Shopify's products.json returns prices in major currency units."""
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def money(value: int | float | str | Decimal | None) -> str:
    amount = price_value(value)
    if amount is None:
        return ""
    return f"PKR {amount:,.2f}"


def description_details(html: str, default_warranty: str) -> tuple[str, list[str], str]:
    """Return warranty, feature strings, and plain-text description."""
    soup = BeautifulSoup(html or "", "html.parser")
    text = clean(soup.get_text(" ", strip=True))

    warranty = default_warranty
    match = WARRANTY_RE.search(text)
    if match:
        warranty = clean(match.group(0))

    features: list[str] = []
    for element in soup.select("li, tr"):
        value = clean(element.get_text(" ", strip=True))
        if value and value.casefold() not in {x.casefold() for x in features}:
            features.append(value)

    # Many Shopify themes use a sequence of paragraphs instead of a list/table.
    if not features:
        labels = re.compile(
            r"^(case|dial|strap|band|movement|glass|water|display|gender|material|"
            r"diameter|width|length|weight|closure|function|feature)s?\b",
            re.IGNORECASE,
        )
        for element in soup.select("p, div"):
            value = clean(element.get_text(" ", strip=True))
            if value and len(value) <= 180 and labels.search(value):
                if value.casefold() not in {x.casefold() for x in features}:
                    features.append(value)

    return warranty, features, text


def get_json(session: requests.Session, url: str, retries: int, delay: float) -> dict:
    error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            response = session.get(url, timeout=30)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            error = exc
            if attempt < retries:
                time.sleep(delay * (2**attempt))
    raise RuntimeError(f"Could not download {url}: {error}") from error


def scrape_collection(
    collection_url: str, delay: float = 0.25, retries: int = 3, default_warranty: str = "1 Year International Warranty"
) -> list[dict]:
    parsed = urlparse(collection_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Collection URL must be a valid http(s) URL")
    base_collection = collection_url.split("?", 1)[0].rstrip("/")
    endpoint = f"{base_collection}/products.json"
    origin = f"{parsed.scheme}://{parsed.netloc}"
    session = requests.Session()
    session.headers.update({"User-Agent": "WatchCatalogScraper/1.0 (+educational data export)"})

    products: list[dict] = []
    page = 1
    while True:
        payload = get_json(session, f"{endpoint}?limit=250&page={page}", retries, delay)
        batch = payload.get("products", [])
        if not batch:
            break
        products.extend(batch)
        print(f"Downloaded page {page}: {len(batch)} products ({len(products)} total)")
        if len(batch) < 250:
            break
        page += 1
        time.sleep(delay)

    rows: list[dict] = []
    for product in products:
        variants = product.get("variants") or []
        prices = [p for v in variants if (p := price_value(v.get("price"))) is not None]
        compare_prices = [p for v in variants if (p := price_value(v.get("compare_at_price"))) is not None]
        warranty, features, description = description_details(product.get("body_html", ""), default_warranty)
        handle = product.get("handle", "")
        rows.append(
            {
                "id": product.get("id"),
                "name": product.get("title", ""),
                "price": money(min(prices) if prices else None),
                "price_min_pkr": (float(min(prices)) if prices else None),
                "price_max_pkr": (float(max(prices)) if prices else None),
                "compare_at_price": money(max(compare_prices) if compare_prices else None),
                "warranty": warranty,
                "features": features,
                "description": description,
                "product_type": product.get("product_type", ""),
                "vendor": product.get("vendor", ""),
                "tags": product.get("tags", []),
                "available": any(v.get("available", False) for v in variants),
                "variants": variants,
                "images": [image.get("src") for image in product.get("images", []) if image.get("src")],
                "url": urljoin(origin, f"/products/{handle}"),
                "published_at": product.get("published_at", ""),
                "updated_at": product.get("updated_at", ""),
            }
        )
    return rows


def save(rows: list[dict], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "watches.json"
    csv_path = output_dir / "watches.csv"
    json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    columns = [
        "id", "name", "price", "price_min_pkr", "price_max_pkr", "compare_at_price",
        "warranty", "features", "description", "product_type", "vendor", "tags",
        "available", "variants", "images", "url", "published_at", "updated_at",
    ]
    with csv_path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            flat = dict(row)
            flat["features"] = " | ".join(row["features"])
            flat["tags"] = " | ".join(row["tags"])
            flat["images"] = " | ".join(row["images"])
            flat["variants"] = json.dumps(row["variants"], ensure_ascii=False)
            writer.writerow(flat)
    print(f"Saved {len(rows)} watches to {json_path} and {csv_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape all watches from a Shopify collection.")
    parser.add_argument("url", nargs="?", default=DEFAULT_COLLECTION, help="Shopify collection URL")
    parser.add_argument("-o", "--output", type=Path, default=Path("output"), help="Output directory")
    parser.add_argument("--delay", type=float, default=0.25, help="Delay between catalog pages")
    parser.add_argument("--retries", type=int, default=3, help="Retries after a failed request")
    args = parser.parse_args()
    save(scrape_collection(args.url, max(args.delay, 0), max(args.retries, 0)), args.output)


if __name__ == "__main__":
    main()
