#!/usr/bin/env python3
"""
Osiris Demo Conversation Simulator
Demonstrates how Osiris would handle a Supabase to Shopify sync request
"""

import sys
import time

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.syntax import Syntax

console = Console()


def type_text(text, delay=0.02):
    """Simulate typing effect"""
    for char in text:
        print(char, end="", flush=True)
        time.sleep(delay)
    print()


def show_user_message(message):
    """Display user message with formatting"""
    console.print("\n[bold blue]👤 User:[/bold blue]")
    console.print(message)
    time.sleep(1)


def show_osiris_message(message):
    """Display Osiris response with formatting"""
    console.print("\n[bold green]🤖 Osiris:[/bold green]")
    console.print(message)
    time.sleep(1)


def show_discovery_progress():
    """Simulate database discovery with progress bar"""
    tables = ["customers", "orders", "order_items", "products", "reviews"]

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:

        task = progress.add_task("[cyan]Discovering Supabase schema...", total=len(tables))

        for table in tables:
            progress.update(task, description=f"[cyan]Analyzing table: {table}")
            time.sleep(0.5)
            progress.advance(task)

        progress.update(task, description=f"[cyan]Found tables: {', '.join(tables)}")
        time.sleep(1)

    console.print("[green]✓ Schema discovery complete![/green]")


def show_pipeline_generation():
    """Simulate pipeline generation"""
    console.print("\n[yellow]Generating YAML pipeline...[/yellow]")

    yaml_content = """metadata:
  name: supabase_to_shopify_sync
  description: Sync customer data from Supabase to Shopify
  schedule: "0 2 * * *"  # Daily at 2 AM EST
  timezone: "America/New_York"

data_quality:
  min_customers: 10
  max_data_age_days: 7

notifications:
  on_success:
    - type: webhook
      url: ${SLACK_WEBHOOK_URL}
  on_failure:
    - type: email
      to: ops@keboola.com

source:
  type: supabase
  config:
    url: ${SUPABASE_URL}
    key: ${SUPABASE_KEY}

extract:
  - name: customer_purchases
    sql: |
      WITH customer_stats AS (
        SELECT
          c.id, c.email,
          COUNT(o.id) as total_orders,
          SUM(o.total_amount) as lifetime_value,
          AVG(o.total_amount) as avg_order_value
        FROM customers c
        LEFT JOIN orders o ON c.id = o.customer_id
        WHERE o.created_at >= NOW() - INTERVAL '90 days'
        GROUP BY c.id, c.email
      )
      SELECT * FROM customer_stats

transform:
  - name: shopify_customer_metafields
    sql: |
      SELECT
        email,
        lifetime_value,
        CASE
          WHEN lifetime_value > 1000 THEN 'VIP'
          WHEN lifetime_value > 500 THEN 'Gold'
          WHEN lifetime_value > 100 THEN 'Silver'
          ELSE 'Bronze'
        END as customer_tier

load:
  - name: shopify_sync
    destination: shopify_api
    config:
      endpoint: ${SHOPIFY_STORE_URL}/admin/api/2024-01/customers"""

    time.sleep(1)
    console.print("\n[dim]─── Generated pipeline.yaml ───[/dim]\n")
    syntax = Syntax(yaml_content, "yaml", theme="ansi_light", line_numbers=True)
    console.print(syntax)


def main():
    """Run the demo conversation"""
    console.clear()
    console.print("[bold cyan]═══ Osiris Conversational Pipeline Generator ═══[/bold cyan]")
    console.print("[dim]Demo: Supabase to Shopify Sync[/dim]\n")

    # User's initial request
    user_message = """I need to sync customer and order data from my Supabase database to Shopify.
I want to calculate customer lifetime value, segment customers into tiers (VIP, Gold, Silver, Bronze),
track their engagement status, and sync this as metafields to Shopify.

Also include product performance metrics like revenue and ratings for the last 30 days,
and create marketing segments for targeted campaigns."""

    show_user_message(user_message)

    # Osiris response
    osiris_response = """I'll help you create a pipeline to sync data from Supabase to Shopify. Let me understand your requirements:

1. ✅ Extract customer purchase history and calculate lifetime metrics
2. ✅ Segment customers by value and engagement
3. ✅ Track product performance
4. ✅ Transform data into Shopify metafield format
5. ✅ Create marketing segments

First, let me discover your Supabase schema..."""

    show_osiris_message(osiris_response)

    # Show discovery progress
    show_discovery_progress()

    # Osiris analysis
    osiris_analysis = """Based on your schema, I'll generate a pipeline that:

• [bold cyan]Extracts[/bold cyan] customer stats from the last 90 days
• [bold cyan]Calculates[/bold cyan] lifetime value, order counts, and average order value
• [bold cyan]Creates[/bold cyan] customer tiers based on spending (VIP > $1000, Gold > $500, Silver > $100, Bronze)
• [bold cyan]Tracks[/bold cyan] engagement status (Active/At Risk/Churned)
• [bold cyan]Analyzes[/bold cyan] product performance metrics
• [bold cyan]Syncs[/bold cyan] to Shopify via API with proper metafield mapping
• [bold cyan]Exports[/bold cyan] segments for marketing automation

Would you like to schedule this to run daily at 2 AM EST?"""

    show_osiris_message(osiris_analysis)

    # User confirmation
    user_confirm = """Yes, and add data quality checks to ensure we have at least 10 customers and data isn't older than 7 days.
Send success notifications to Slack and failure alerts to ops@keboola.com."""

    show_user_message(user_confirm)

    # Generate pipeline
    show_pipeline_generation()

    # Final message
    osiris_final = """✅ Pipeline generated successfully!

[bold]Next steps:[/bold]
1. Review the generated `pipeline.yaml`
2. Configure your environment variables in `.env`
3. Run `osiris run pipeline.yaml` to execute
4. Or approve with 'approve' to run immediately

The pipeline will automatically:
- Run daily at 2 AM EST
- Validate data quality before processing
- Send notifications on success/failure
- Maintain audit logs of all syncs"""

    show_osiris_message(osiris_final)

    console.print(
        "\n[dim]💡 This demo shows how Osiris uses natural conversation to understand intent,[/dim]"
    )
    console.print(
        "[dim]   discovers database schemas automatically, and generates technical YAML[/dim]"
    )
    console.print("[dim]   without requiring users to know SQL or pipeline syntax.[/dim]\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[yellow]Demo interrupted by user[/yellow]")
        sys.exit(0)
