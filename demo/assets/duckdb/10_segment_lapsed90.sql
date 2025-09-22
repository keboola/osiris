-- Segment: Lapsed 90 Days
-- Customers who haven't purchased in 90+ days
WITH lapsed_customers AS (
    SELECT
        r.customer_id,
        r.recency_days,
        r.frequency,
        r.monetary_value,
        r.rfm_score,
        r.customer_segment,
        u.email,
        u.consent_marketing,
        u.data_residency
    FROM rfm_analysis r
    INNER JOIN users u ON r.customer_id = u.customer_id
    WHERE r.recency_days >= :days_since_purchase  -- Parameter: 90 days
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
    -- Reactivation priority
    CASE
        WHEN monetary_value >= 1000 THEN 'High'
        WHEN monetary_value >= 500 THEN 'Medium'
        ELSE 'Low'
    END as reactivation_priority,
    -- Recommended offer type
    CASE
        WHEN recency_days >= 180 THEN 'Win-back Special'
        WHEN frequency >= 5 THEN 'Loyalty Reward'
        ELSE 'Standard Discount'
    END as offer_type,
    'lapsed90' as segment_name,
    CURRENT_TIMESTAMP as segmented_at
FROM lapsed_customers
ORDER BY monetary_value DESC