# Shopify Orders API Documentation

## Overview
The Shopify Orders API provides access to order data from your Shopify store.

## Endpoints

### GET /orders
Retrieve a list of orders

**Parameters:**
- `status`: Filter by order status (any, open, closed, cancelled)
- `created_at_min`: Show orders created after date
- `created_at_max`: Show orders created before date
- `limit`: Number of results (default: 50, max: 250)
- `fields`: Comma-separated list of fields to include

**Response Fields:**
- `order_id`: Unique identifier
- `customer_id`: Customer identifier
- `customer_email`: Customer email address
- `total`: Order total amount
- `currency`: Currency code
- `created_at`: Order creation timestamp
- `shipping_status`: Current shipping status
- `line_items`: Array of order items

## Example Usage

```python
import shopify

shop = shopify.Shop.current()
orders = shopify.Order.find(status="any", limit=100)

for order in orders:
    print(f"Order {order.id}: ${order.total_price}")
```