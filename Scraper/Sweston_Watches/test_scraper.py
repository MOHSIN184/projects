import unittest

from scraper import description_details, money


class ScraperTests(unittest.TestCase):
    def test_extracts_list_features_and_warranty(self):
        html = "<ul><li>Movement: Quartz</li><li>Water Resistant</li></ul><p>1-Year International Warranty</p>"
        warranty, features, description = description_details(html, "default")
        self.assertIn("1-Year", warranty)
        self.assertEqual(features, ["Movement: Quartz", "Water Resistant"])
        self.assertIn("Quartz", description)

    def test_default_warranty(self):
        warranty, _, _ = description_details("<p>Stainless steel watch</p>", "1 Year International Warranty")
        self.assertEqual(warranty, "1 Year International Warranty")

    def test_money(self):
        self.assertEqual(money("11999.00"), "PKR 11,999.00")


if __name__ == "__main__":
    unittest.main()
