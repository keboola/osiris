-- Segment: High Churn Risk Customers
-- Active customers with high probability of churning
WITH churn_analysis AS (
    SELECT
        cs.customer_id,
        cs.churn_probability,
        cs.churn_risk_level,
        cs.days_since_last_activity,
        cs.total_events,
        cs.purchase_events,
        r.frequency,
        r.monetary_value,
        r.customer_segment,
        u.email,
        u.consent_marketing,
        u.data_residency
    FROM churn_scores cs
    INNER JOIN rfm_analysis r ON cs.customer_id = r.customer_id
    INNER JOIN users u ON cs.customer_id = u.customer_id
    WHERE cs.churn_probability >= :churn_threshold  -- Parameter: 0.75
        AND cs.days_since_last_activity < 90  -- Still active but at risk
        AND u.consent_marketing = true
        AND u.data_residency = 'EU'
),
ticket_insights AS (
    SELECT
        customer_id,
        COUNT(DISTINCT ticket_id) as support_tickets,
        MAX(primary_topic) as last_issue_topic,
        AVG(topic_confidence) as avg_confidence
    FROM ticket_topics
    GROUP BY customer_id
)
SELECT
    ca.customer_id,
    ca.email,
    ca.churn_probability,
    ca.churn_risk_level,
    ca.days_since_last_activity,
    ca.frequency as lifetime_purchases,
    ca.monetary_value as lifetime_value,
    ti.support_tickets,
    ti.last_issue_topic,
    -- Intervention strategy
    CASE
        WHEN ti.last_issue_topic = 'shipping_delay' THEN 'Free Express Shipping'
        WHEN ti.last_issue_topic = 'payment_failure' THEN 'Payment Support + Discount'
        WHEN ti.last_issue_topic = 'return_process' THEN 'Extended Return Window'
        WHEN ca.purchase_events = 0 THEN 'First Purchase Incentive'
        ELSE 'Retention Discount'
    END as intervention_type,
    -- Urgency level
    CASE
        WHEN ca.churn_probability >= 0.90 THEN 'Immediate'
        WHEN ca.churn_probability >= 0.80 THEN 'Within 48 hours'
        ELSE 'Within 1 week'
    END as contact_urgency,
    -- Recommended channel
    CASE
        WHEN ca.monetary_value >= 1000 THEN 'Personal Email + Call'
        WHEN ti.support_tickets >= 2 THEN 'Priority Support Email'
        ELSE 'Automated Campaign'
    END as contact_channel,
    'churnrisk_high' as segment_name,
    CURRENT_TIMESTAMP as segmented_at
FROM churn_analysis ca
LEFT JOIN ticket_insights ti ON ca.customer_id = ti.customer_id
ORDER BY ca.churn_probability DESC, ca.monetary_value DESC