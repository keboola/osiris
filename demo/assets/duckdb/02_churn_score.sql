-- Churn Score Prediction Model (Simplified)
WITH user_activity AS (
    SELECT
        u.user_id,
        u.customer_id,
        COUNT(DISTINCT e.event_id) as total_events,
        COUNT(DISTINCT CASE WHEN e.event_name = 'purchase' THEN e.event_id END) as purchase_events,
        COUNT(DISTINCT DATE(e.timestamp)) as active_days,
        DATEDIFF('day', MAX(e.timestamp), CURRENT_DATE) as days_since_last_activity,
        AVG(CASE WHEN e.event_name = 'purchase' THEN 1 ELSE 0 END) as purchase_rate
    FROM users u
    LEFT JOIN events e ON u.user_id = e.user_id
    WHERE e.timestamp >= CURRENT_DATE - INTERVAL '180 days'
    GROUP BY u.user_id, u.customer_id
),
engagement_metrics AS (
    SELECT
        user_id,
        customer_id,
        total_events,
        purchase_events,
        active_days,
        days_since_last_activity,
        purchase_rate,
        -- Engagement score components
        CASE
            WHEN days_since_last_activity <= 7 THEN 5
            WHEN days_since_last_activity <= 30 THEN 4
            WHEN days_since_last_activity <= 60 THEN 3
            WHEN days_since_last_activity <= 90 THEN 2
            ELSE 1
        END as recency_score,
        CASE
            WHEN active_days >= 20 THEN 5
            WHEN active_days >= 15 THEN 4
            WHEN active_days >= 10 THEN 3
            WHEN active_days >= 5 THEN 2
            ELSE 1
        END as activity_score
    FROM user_activity
)
SELECT
    user_id,
    customer_id,
    total_events,
    purchase_events,
    active_days,
    days_since_last_activity,
    recency_score,
    activity_score,
    -- Calculate churn probability (0-1 scale)
    CASE
        WHEN days_since_last_activity > 90 THEN 0.95
        WHEN days_since_last_activity > 60 AND purchase_events = 0 THEN 0.85
        WHEN days_since_last_activity > 30 AND activity_score <= 2 THEN 0.75
        WHEN recency_score <= 2 AND activity_score <= 2 THEN 0.65
        WHEN purchase_rate < 0.1 AND active_days < 5 THEN 0.55
        ELSE 0.25
    END as churn_probability,
    -- Churn risk category
    CASE
        WHEN days_since_last_activity > 90 THEN 'Critical'
        WHEN days_since_last_activity > 60 AND purchase_events = 0 THEN 'High'
        WHEN days_since_last_activity > 30 AND activity_score <= 2 THEN 'Medium'
        ELSE 'Low'
    END as churn_risk_level
FROM engagement_metrics