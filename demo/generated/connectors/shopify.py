"""
Auto-generated Shopify connector
Generated from Context7 documentation
"""

from typing import Dict, Any
import pandas as pd

class ShopifyExtractor:
    def __init__(self, config: Dict[str, Any]):
        self.config = config

    def extract(self) -> pd.DataFrame:
        """Extract orders from Shopify."""
        # Simulated extraction
        return pd.DataFrame({
            "order_id": range(1000, 1100),
            "customer_id": range(100, 200),
            "total": [99.99] * 100,
            "created_at": ["2024-01-01"] * 100
        })
