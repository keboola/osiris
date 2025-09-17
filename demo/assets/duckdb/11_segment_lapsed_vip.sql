-- Segment: Lapsed VIP Customers
-- High-value customers (top 10% by monetary value) who haven't purchased in 90+ days
WITH customer_percentiles AS (
    SELECT
        customer_id,
        recency_days,
        frequency,
        monetary_value,
        rfm_score,
        PERCENT_RANK() OVER (ORDER BY monetary_value) as monetary_percentile
    FROM rfm_analysis
),
lapsed_vips AS (
    SELECT
        cp.customer_id,
        cp.recency_days,
        cp.frequency,
        cp.monetary_value,
        cp.rfm_score,
        cp.monetary_percentile,
        u.email,
        u.consent_marketing,
        u.data_residency,
        -- VIP tier classification
        CASE
            WHEN cp.monetary_percentile >= 0.95 THEN 'Platinum'
            WHEN cp.monetary_percentile >= 0.90 THEN 'Gold'
            ELSE 'Silver'
        END as vip_tier
    FROM customer_percentiles cp
    INNER JOIN users u ON cp.customer_id = u.customer_id
    WHERE cp.recency_days >= :days_since_purchase  -- Parameter: 90 days
        AND cp.monetary_percentile >= :monetary_percentile  -- Parameter: 0.90
        AND u.consent_marketing = true
        AND u.data_residency = 'EU'
)
SELECT
    customer_id,
    email,
    recency_days as days_lapsed,
    frequency as lifetime_purchases,
    monetary_value as lifetime_value,
    rfm_score,
    vip_tier,
    monetary_percentile,
    -- VIP-specific metrics
    monetary_value / frequency as avg_order_value,
    -- Personalized messaging
    CASE
        WHEN vip_tier = 'Platinum' THEN 'Exclusive Platinum Preview'
        WHEN vip_tier = 'Gold' THEN 'Gold Member Special Access'
        ELSE 'VIP Welcome Back Offer'
    END as message_theme,
    -- Risk assessment
    CASE
        WHEN recency_days >= 180 THEN 'Critical - Immediate Action'
        WHEN recency_days >= 120 THEN 'High - Priority Outreach'
        ELSE 'Medium - Standard Campaign'
    END as retention_risk,
    'lapsed_vip' as segment_name,
    CURRENT_TIMESTAMP as segmented_at
FROM lapsed_vips
ORDER BY monetary_value DESC