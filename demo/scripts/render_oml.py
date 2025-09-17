"""
OML (Osiris Markup Language) Generator
Generates valid OML v0.1.0 pipeline definitions
"""

import yaml
from datetime import datetime
from typing import Dict, Any

def generate_oml(run_id: str) -> str:
    """Generate OML pipeline definition."""
    oml = {
        "oml_version": "0.1.0",
        "name": "multi_source_activation_pipeline",
        "description": "Reactivate lapsed customers with identity resolution and segmentation",
        "metadata": {
            "run_id": run_id,
            "generated_at": datetime.now().isoformat(),
            "eu_data_zone": True,
            "consent_required": True
        },
        "steps": [
            # Extraction steps
            {
                "id": "extract_supabase_users",
                "component": "supabase.extractor",
                "mode": "read",
                "config": {
                    "connection": "@supabase.prod",
                    "query": "SELECT * FROM users WHERE updated_at >= '2024-01-01'",
                    "pii_columns": ["email", "phone"]
                }
            },
            {
                "id": "extract_stripe_charges",
                "component": "stripe.extractor",
                "mode": "read",
                "config": {
                    "connection": "@stripe.prod",
                    "object": "charges",
                    "filters": {"created": {"gte": 1704067200}},
                    "pii_columns": ["customer_email"]
                }
            },
            {
                "id": "extract_mixpanel_events",
                "component": "mixpanel.extractor",
                "mode": "read",
                "config": {
                    "connection": "@mixpanel.prod",
                    "event_names": ["purchase", "add_to_cart", "page_view"],
                    "from_date": "2024-01-01",
                    "schema_version": "2.1"  # Note: schema drift detected
                }
            },
            {
                "id": "extract_shopify_orders",
                "component": "shopify.extractor",
                "mode": "read",
                "config": {
                    "connection": "@shopify.prod",
                    "resource": "orders",
                    "status": "any",
                    "limit": 250,
                    "pii_columns": ["customer_email", "shipping_address"]
                }
            },
            {
                "id": "extract_zendesk_tickets",
                "component": "zendesk.extractor",
                "mode": "read",
                "config": {
                    "connection": "@zendesk.support",
                    "type": "ticket",
                    "status": ["closed", "solved"],
                    "pii_columns": ["requester_email"]
                }
            },

            # Identity Resolution
            {
                "id": "identity_resolution",
                "component": "duckdb.transformer",
                "mode": "transform",
                "config": {
                    "sql": """
                    WITH identity_graph AS (
                        -- Deterministic matching on email
                        SELECT DISTINCT
                            email as match_key,
                            customer_id,
                            'deterministic' as match_type,
                            0.99 as confidence
                        FROM unified_customers
                        WHERE email IS NOT NULL

                        UNION ALL

                        -- Probabilistic matching on name + address
                        SELECT DISTINCT
                            MD5(CONCAT(last_name, postal_code)) as match_key,
                            customer_id,
                            'probabilistic' as match_type,
                            0.85 as confidence
                        FROM unified_customers
                        WHERE last_name IS NOT NULL
                    )
                    SELECT * FROM identity_graph
                    """
                },
                "inputs": ["extract_supabase_users", "extract_stripe_charges",
                           "extract_shopify_orders"]
            },

            # Feature Engineering
            {
                "id": "compute_rfm",
                "component": "duckdb.transformer",
                "mode": "transform",
                "config": {
                    "sql_file": "assets/duckdb/01_rfm.sql",
                    "params": {
                        "recency_days": 90,
                        "frequency_min": 2,
                        "monetary_percentile": 0.75
                    }
                },
                "inputs": ["identity_resolution", "extract_stripe_charges"]
            },
            {
                "id": "compute_churn_score",
                "component": "duckdb.transformer",
                "mode": "transform",
                "config": {
                    "sql_file": "assets/duckdb/02_churn_score.sql"
                },
                "inputs": ["compute_rfm", "extract_mixpanel_events"]
            },
            {
                "id": "extract_topics",
                "component": "duckdb.transformer",
                "mode": "transform",
                "config": {
                    "sql_file": "assets/duckdb/03_topics_from_tickets.sql",
                    "topic_model": "bag_of_words_v1"
                },
                "inputs": ["extract_zendesk_tickets"]
            },

            # Segmentation
            {
                "id": "segment_lapsed90",
                "component": "duckdb.transformer",
                "mode": "transform",
                "config": {
                    "sql_file": "assets/duckdb/10_segment_lapsed90.sql",
                    "params": {"days_since_purchase": 90}
                },
                "inputs": ["compute_rfm"]
            },
            {
                "id": "segment_lapsed_vip",
                "component": "duckdb.transformer",
                "mode": "transform",
                "config": {
                    "sql_file": "assets/duckdb/11_segment_lapsed_vip.sql",
                    "params": {
                        "days_since_purchase": 90,
                        "monetary_percentile": 0.90
                    }
                },
                "inputs": ["compute_rfm"]
            },
            {
                "id": "segment_churnrisk_high",
                "component": "duckdb.transformer",
                "mode": "transform",
                "config": {
                    "sql_file": "assets/duckdb/12_segment_churnrisk_high.sql",
                    "params": {"churn_threshold": 0.75}
                },
                "inputs": ["compute_churn_score"]
            },

            # Data Quality
            {
                "id": "dq_validation",
                "component": "duckdb.transformer",
                "mode": "transform",
                "config": {
                    "rules": [
                        {
                            "name": "null_ratio",
                            "sql": "SELECT AVG(CASE WHEN email IS NULL THEN 1 ELSE 0 END) as null_ratio FROM {table}",
                            "threshold": 0.02
                        },
                        {
                            "name": "uniqueness",
                            "sql": "SELECT COUNT(*) - COUNT(DISTINCT order_id) as duplicates FROM orders",
                            "threshold": 0
                        },
                        {
                            "name": "business_check",
                            "sql": "SELECT SUM(order_total) >= SUM(payment_total) * 0.9 as valid FROM reconciliation",
                            "expected": True
                        }
                    ]
                },
                "inputs": ["segment_lapsed90", "segment_lapsed_vip", "segment_churnrisk_high"]
            },

            # Privacy & Consent
            {
                "id": "apply_consent_filter",
                "component": "duckdb.transformer",
                "mode": "transform",
                "config": {
                    "sql": """
                    SELECT * FROM customers
                    WHERE consent_marketing = TRUE
                    AND consent_updated_at >= CURRENT_DATE - INTERVAL '365 days'
                    AND data_residency = 'EU'
                    """
                },
                "inputs": ["dq_validation"]
            },

            # Activation
            {
                "id": "activate_google_ads",
                "component": "google_ads.writer",
                "mode": "write",
                "config": {
                    "connection": "@google_ads.prod",
                    "customer_id": "123-456-7890",
                    "audience_list_id": "aud_8c9e5f2a",
                    "holdout_percentage": 10,
                    "frequency_cap": {"impressions": 3, "time_unit": "week"}
                },
                "inputs": ["apply_consent_filter"]
            },
            {
                "id": "activate_esp",
                "component": "esp.writer",
                "mode": "write",
                "config": {
                    "connection": "@esp.marketing",
                    "list_id": "list_vip_reactivation",
                    "template_id": "tmpl_winback_2024",
                    "holdout_percentage": 10,
                    "send_time_optimization": True
                },
                "inputs": ["apply_consent_filter"]
            },

            # Publish
            {
                "id": "publish_to_iceberg",
                "component": "iceberg.publisher",
                "mode": "write",
                "config": {
                    "catalog": "data_lake",
                    "namespace": "activation",
                    "tables": ["segments", "features", "activation_log"],
                    "partition_by": ["date", "segment_id"],
                    "commit_message": f"Activation pipeline run {run_id}"
                },
                "inputs": ["activate_google_ads", "activate_esp"]
            }
        ],

        # Data Quality Rules (referenced by dq_validation step)
        "quality": {
            "global_rules": {
                "max_null_percentage": 2.0,
                "require_unique_keys": True,
                "schema_evolution": "strict_compatible"
            },
            "warnings": [
                {
                    "step": "extract_mixpanel_events",
                    "type": "schema_drift",
                    "message": "New field detected: utm_campaign (non-breaking)"
                }
            ]
        },

        # Privacy Configuration
        "privacy": {
            "pii_masking": {
                "enabled": True,
                "patterns": ["email", "phone", "ssn", "credit_card"]
            },
            "consent": {
                "required": True,
                "default": "opt_out",
                "refresh_days": 365
            },
            "data_residency": {
                "regions": ["EU"],
                "enforce": True
            }
        }
    }

    return yaml.dump(oml, default_flow_style=False, sort_keys=False, width=120)