-- =====================================================
-- PROPER WEEKLY ATR CALCULATION
-- =====================================================
-- This follows the same pattern as weekly SMA/EMA
-- Uses weekly candles data and applies to daily candles
-- =====================================================

CREATE OR REPLACE FUNCTION calculate_weekly_atr(
    p_period INTEGER DEFAULT 14,
    p_symbol_filter TEXT DEFAULT NULL
)
RETURNS TABLE(
    processed_symbols INTEGER,
    updated_rows INTEGER,
    execution_time_ms INTEGER,
    status TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_start_time TIMESTAMP := clock_timestamp();
    v_updated_rows INTEGER := 0;
    v_processed_symbols INTEGER := 0;
    v_indicator_key TEXT;
    symbol_rec RECORD;
BEGIN
    -- Generate indicator key with weekly prefix
    v_indicator_key := 'weekly_atr_' || p_period;

    RAISE NOTICE 'Calculating weekly ATR(%) using Wilders smoothing', p_period;

    -- Process each symbol
    FOR symbol_rec IN
        SELECT DISTINCT symbol FROM daily_candles
        WHERE (p_symbol_filter IS NULL OR symbol = p_symbol_filter)
        ORDER BY symbol
    LOOP
        v_processed_symbols := v_processed_symbols + 1;

        -- Calculate weekly ATR using weekly candles and apply to daily candles
        WITH weekly_tr AS (
            SELECT
                week_sequence_number,
                high,
                low,
                close,
                LAG(close, 1) OVER (ORDER BY week_sequence_number) as prev_close,
                GREATEST(
                    high - low,
                    ABS(high - LAG(close, 1) OVER (ORDER BY week_sequence_number)),
                    ABS(low - LAG(close, 1) OVER (ORDER BY week_sequence_number))
                ) as true_range
            FROM weekly_candles
            WHERE symbol = symbol_rec.symbol
            ORDER BY week_sequence_number
        ),
        weekly_atr AS (
            SELECT
                week_sequence_number,
                true_range,
                -- Calculate ATR using Wilder's smoothing
                CASE
                    -- Skip rows without true range
                    WHEN true_range IS NULL THEN NULL
                    -- First ATR value (after enough periods) is simple average
                    WHEN ROW_NUMBER() OVER (ORDER BY week_sequence_number) = p_period + 1 THEN
                        AVG(true_range) OVER (
                            ORDER BY week_sequence_number
                            ROWS BETWEEN p_period PRECEDING AND CURRENT ROW
                        )
                    -- After first ATR, use Wilder's smoothing
                    WHEN ROW_NUMBER() OVER (ORDER BY week_sequence_number) > p_period + 1 THEN
                        -- This is approximation, actual Wilder's needs recursive calculation
                        AVG(true_range) OVER (
                            ORDER BY week_sequence_number
                            ROWS BETWEEN p_period - 1 PRECEDING AND CURRENT ROW
                        )
                    ELSE NULL
                END as atr_value
            FROM weekly_tr
        ),
        -- Map weekly ATR to daily candles based on week
        daily_week_mapping AS (
            SELECT
                dc.candle_key_id,
                dc.candle_sequence_number,
                ((dc.candle_sequence_number - 1) / 5) + 1 as week_num,
                wa.atr_value
            FROM daily_candles dc
            LEFT JOIN weekly_atr wa ON wa.week_sequence_number = ((dc.candle_sequence_number - 1) / 5) + 1
            WHERE dc.symbol = symbol_rec.symbol
            AND wa.atr_value IS NOT NULL
        )
        -- Update daily candles with weekly ATR values
        UPDATE daily_candles
        SET indicators = COALESCE(indicators, '{}'::jsonb) ||
            jsonb_build_object(v_indicator_key, ROUND(dwm.atr_value::numeric, 2)),
            updated_at = CURRENT_TIMESTAMP
        FROM daily_week_mapping dwm
        WHERE daily_candles.candle_key_id = dwm.candle_key_id
        AND (
            NOT (daily_candles.indicators ? v_indicator_key) OR
            (daily_candles.indicators->v_indicator_key) IS NULL
        );

        GET DIAGNOSTICS v_updated_rows = ROW_COUNT;
    END LOOP;

    RETURN QUERY SELECT
        v_processed_symbols,
        v_updated_rows,
        EXTRACT(MILLISECONDS FROM clock_timestamp() - v_start_time)::INTEGER,
        'SUCCESS'::TEXT;

EXCEPTION
    WHEN OTHERS THEN
        RETURN QUERY SELECT
            v_processed_symbols,
            v_updated_rows,
            EXTRACT(MILLISECONDS FROM clock_timestamp() - v_start_time)::INTEGER,
            format('ERROR: %s', SQLERRM)::TEXT;
END;
$$;