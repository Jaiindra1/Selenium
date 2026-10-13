import unittest

from models import Product
from product_filter import filter_products


def product(name):
    return Product(name=name, product_url="https://example.com/product")


class ProductFilterTests(unittest.TestCase):
    def test_mobile_category_removes_accessories_and_other_categories(self):
        products = [product("Samsung Galaxy S24 5G Smartphone"), product("Galaxy S24 Silicone Cover"), product("HP Pavilion Laptop")]
        self.assertEqual([item.name for item in filter_products(products, "mobile")], ["Samsung Galaxy S24 5G Smartphone"])

    def test_specific_model_requires_brand_and_model(self):
        products = [product("Apple iPhone 15 128GB"), product("Apple iPhone 14 128GB"), product("iPhone 15 Case")]
        self.assertEqual([item.name for item in filter_products(products, "Apple iPhone 15")], ["Apple iPhone 15 128GB"])

    def test_laptop_category_ignores_laptop_accessories(self):
        products = [product("Lenovo IdeaPad Slim 5 Laptop"), product("Adjustable Laptop Stand"), product("Wireless Mouse")]
        self.assertEqual([item.name for item in filter_products(products, "laptops")], ["Lenovo IdeaPad Slim 5 Laptop"])


if __name__ == "__main__":
    unittest.main()
