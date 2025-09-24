# Pipeline Run Report

**Pipeline:** Lapsed Customer Reactivation
**Run ID:** 8a40bf88
**Sources:** Supabase, Stripe, Mixpanel, Shopify, Zendesk (5 total)
**Identity Keys:** email (primary), phone (secondary), fuzzy email matching enabled
**Segments:** lapsed_90 (42K), lapsed_vip (4.2K), high_churn_risk (8.5K)
**DQ Rules:** 4 validations (null ratio, uniqueness, schema drift, business logic)
**Activation:** Google Ads (10% holdout), ESP campaigns (A/B test enabled)
**Output:** demo/out/OML.yaml
