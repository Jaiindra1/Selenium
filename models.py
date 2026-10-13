"""Small data models shared by extraction, display, and PDF reporting."""

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Product:
    """One product extracted from a search-results page or product page.

    Required fields are the product name and destination URL. All other fields
    are optional because stores publish different amounts of product metadata.
    """

    name: str
    product_url: str
    price: Optional[str] = None
    original_price: Optional[str] = None
    currency: Optional[str] = None
    discount: Optional[str] = None
    rating: Optional[str] = None
    ratings_count: Optional[str] = None
    reviews_count: Optional[str] = None
    availability: Optional[str] = None
    brand: Optional[str] = None
    description: Optional[str] = None
    specifications: List[str] = field(default_factory=list)
    image_url: Optional[str] = None
    source_site: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Return a plain dictionary so results can be printed or serialized."""
        return asdict(self)
