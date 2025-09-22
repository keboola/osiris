-- RFM (Recency, Frequency, Monetary) Score Calculation
WITH customer_metrics AS (
    SELECT
        customer_id,
        DATEDIFF('day', MAX(created_at), CURRENT_DATE) as recency_days,
        COUNT(DISTINCT order_id) as frequency,
        SUM(total) as monetary_value,
        AVG(total) as avg_order_value
    FROM orders
    WHERE status != 'cancelled'
    GROUP BY customer_id
),
rfm_scores AS (
    SELECT
        customer_id,
        recency_days,
        frequency,
        monetary_value,
        -- Recency score (1-5, 5 is best/most recent)
        NTILE(5) OVER (ORDER BY recency_days DESC) as R,
        -- Frequency score (1-5, 5 is best/most frequent)
        NTILE(5) OVER (ORDER BY frequency) as F,
        -- Monetary score (1-5, 5 is best/highest value)
        NTILE(5) OVER (ORDER BY monetary_value) as M
    FROM customer_metrics
)
SELECT
    customer_id,
    recency_days,
    frequency,
    monetary_value,
    R,
    F,
    M,
    CONCAT(R, F, M) as rfm_segment,
    -- Combined RFM score
    (R + F + M) / 3.0 as rfm_score,
    -- Segment classification
    CASE
        WHEN R >= 4 AND F >= 4 AND M >= 4 THEN 'Champions'
        WHEN R >= 3 AND F >= 3 AND M >= 4 THEN 'Loyal Customers'
        WHEN R >= 4 AND F <= 2 THEN 'New Customers'
        WHEN R <= 2 AND F >= 3 AND M >= 3 THEN 'At Risk'
        WHEN R <= 2 AND F <= 2 THEN 'Lost'
        ELSE 'Regular'
    END as customer_segment
FROM rfm_scores