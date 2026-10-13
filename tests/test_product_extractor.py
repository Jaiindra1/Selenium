"""Small offline tests for Schema.org and generic product-card extraction."""

import unittest

from product_extractor import extract_products


class ProductExtractorTests(unittest.TestCase):
    """Check the cross-site extraction basics without opening a real website."""

    def test_extracts_schema_product_metadata(self):
        """A standard JSON-LD Product should yield name, price, and rating."""
        html = '''
        <html><head>
          <script type="application/ld+json">
          {
            "@context": "https://schema.org",
            "@type": "Product",
            "name": "Example Phone 256 GB",
            "url": "/products/example-phone",
            "brand": {"@type": "Brand", "name": "Example"},
            "offers": {"@type": "Offer", "price": "86999", "priceCurrency": "INR"},
            "aggregateRating": {"@type": "AggregateRating", "ratingValue": "4.6", "reviewCount": "2057"}
          }
          </script>
        </head><body></body></html>
        '''

        products = extract_products(html, "https://shop.example.com/search?q=phone")

        self.assertEqual(len(products), 1)
        self.assertEqual(products[0].name, "Example Phone 256 GB")
        self.assertEqual(products[0].price, "INR 86999")
        self.assertEqual(products[0].rating, "4.6")
        self.assertIn("/products/example-phone", products[0].product_url)

    def test_extracts_generic_product_card(self):
        """A simple product card with an image, title, price, and link should parse."""
        html = '''
        <html><body>
          <div class="product-card">
            <a href="/products/blue-shirt">
              <img src="/images/shirt.jpg" alt="Blue Cotton Shirt">
              <h2>Blue Cotton Shirt</h2>
            </a>
            <span class="price">₹1,299</span>
            <span>20% off</span>
            <ul><li>100% cotton</li><li>Regular fit</li></ul>
          </div>
        </body></html>
        '''

        products = extract_products(html, "https://shop.example.com/search?q=shirt")

        self.assertEqual(len(products), 1)
        self.assertEqual(products[0].name, "Blue Cotton Shirt")
        self.assertIn("1,299", products[0].price)
        self.assertEqual(products[0].product_url, "https://shop.example.com/products/blue-shirt")
        self.assertTrue(products[0].image_url.endswith("/images/shirt.jpg"))
        self.assertGreaterEqual(len(products[0].specifications), 1)


if __name__ == "__main__":
    unittest.main()
