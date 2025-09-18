-- Support Ticket Topic Extraction (Bag of Words Model)
WITH topic_keywords AS (
    SELECT
        'shipping_delay' as topic,
        ARRAY['shipping', 'delivery', 'delayed', 'late', 'tracking', 'arrived'] as keywords
    UNION ALL
    SELECT
        'payment_failure' as topic,
        ARRAY['payment', 'declined', 'failed', 'card', 'charge', 'billing'] as keywords
    UNION ALL
    SELECT
        'return_process' as topic,
        ARRAY['return', 'refund', 'exchange', 'defective', 'broken', 'wrong'] as keywords
    UNION ALL
    SELECT
        'account_access' as topic,
        ARRAY['login', 'password', 'account', 'access', 'reset', 'locked'] as keywords
    UNION ALL
    SELECT
        'promo_code' as topic,
        ARRAY['promo', 'discount', 'coupon', 'code', 'offer', 'deal'] as keywords
),
ticket_analysis AS (
    SELECT
        t.ticket_id,
        t.requester_email,
        t.subject,
        t.description,
        t.created_at,
        t.status,
        tk.topic,
        -- Simple keyword matching score
        (
            SELECT COUNT(*)
            FROM UNNEST(tk.keywords) as keyword
            WHERE LOWER(t.subject || ' ' || t.description) LIKE '%' || keyword || '%'
        ) as match_score
    FROM tickets t
    CROSS JOIN topic_keywords tk
),
ranked_topics AS (
    SELECT
        ticket_id,
        requester_email,
        subject,
        created_at,
        topic,
        match_score,
        -- Confidence based on match score
        CASE
            WHEN match_score >= 3 THEN 0.95
            WHEN match_score = 2 THEN 0.75
            WHEN match_score = 1 THEN 0.60
            ELSE 0.30
        END as confidence,
        ROW_NUMBER() OVER (PARTITION BY ticket_id ORDER BY match_score DESC) as topic_rank
    FROM ticket_analysis
    WHERE match_score > 0
)
SELECT
    ticket_id,
    requester_email,
    subject,
    created_at,
    topic as primary_topic,
    confidence as topic_confidence,
    -- Additional metadata
    CASE topic
        WHEN 'shipping_delay' THEN 'Operational'
        WHEN 'payment_failure' THEN 'Financial'
        WHEN 'return_process' THEN 'Product'
        WHEN 'account_access' THEN 'Technical'
        WHEN 'promo_code' THEN 'Marketing'
    END as topic_category
FROM ranked_topics
WHERE topic_rank = 1