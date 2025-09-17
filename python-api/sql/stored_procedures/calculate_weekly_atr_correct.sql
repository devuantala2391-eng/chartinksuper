-- =====================================================
-- WEEKLY ATR CALCULATION - FOLLOWING SMA/EMA PATTERN
-- =====================================================
-- Uses the same approach as weekly SMA/EMA
-- Relies on weekly_candle_key_id for joins
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
    week_rec RECORD;
    v_prev_atr NUMERIC := NULL;
    v_current_atr NUMERIC;
    v_tr_sum NUMERIC := 0;
    v_tr_count INTEGER := 0;
    v_true_range NUMERIC;
    v_week_atr_map JSONB;
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
        v_prev_atr := NULL;
        v_tr_sum := 0;
        v_tr_count := 0;
        v_week_atr_map := '{}'::jsonb;

        -- First, calculate ATR for each week using weekly candles
        FOR week_rec IN
            SELECT
                weekly_candle_key_id,
                week_sequence_number,
                high,
                low,
                close,
                LAG(close, 1) OVER (ORDER BY week_sequence_number) as prev_close
            FROM weekly_candles
            WHERE symbol = symbol_rec.symbol
            ORDER BY week_sequence_number
        LOOP
            -- Skip first week (no previous close)
            IF week_rec.prev_close IS NULL THEN
                CONTINUE;
            END IF;

            -- Calculate True Range for this week
            v_true_range := GREATEST(
                week_rec.high - week_rec.low,
                ABS(week_rec.high - week_rec.prev_close),
                ABS(week_rec.low - week_rec.prev_close)
            );

            v_tr_count := v_tr_count + 1;

            IF v_tr_count <= p_period THEN
                -- Accumulate for initial SMA
                v_tr_sum := v_tr_sum + v_true_range;

                IF v_tr_count = p_period THEN
                    -- Calculate first ATR as simple average
                    v_current_atr := v_tr_sum / p_period;
                    v_prev_atr := v_current_atr;
                    -- Store in map
                    v_week_atr_map := v_week_atr_map || jsonb_build_object(week_rec.weekly_candle_key_id, v_current_atr);
                END IF;
            ELSE
                -- Use Wilder's RMA: ATR = ((n-1) * Previous_ATR + TR) / n
                v_current_atr := ((p_period - 1) * v_prev_atr + v_true_range) / p_period;
                v_prev_atr := v_current_atr;
                -- Store in map
                v_week_atr_map := v_week_atr_map || jsonb_build_object(week_rec.weekly_candle_key_id, v_current_atr);
            END IF;
        END LOOP;

        -- Now update daily candles with their corresponding weekly ATR
        -- For sliding window: daily candles in partial weeks use current partial week's OHLC
        WITH daily_with_week_atr AS (
            SELECT
                dc.candle_key_id,
                dc.candle_sequence_number,
                dc.weekly_candle_key_id,
                -- Get ATR value from our calculated map
                (v_week_atr_map->>dc.weekly_candle_key_id)::numeric as week_atr,
                -- Check if this is end of week (every 5th candle)
                CASE WHEN dc.candle_sequence_number % 5 = 4 THEN true ELSE false END as is_week_end,
                -- Get week's partial high/low/close for sliding window
                dc.weekly_high,
                dc.weekly_low,
                dc.weekly_close
            FROM daily_candles dc
            WHERE dc.symbol = symbol_rec.symbol
            AND dc.weekly_candle_key_id IS NOT NULL
        )
        UPDATE daily_candles
        SET indicators = COALESCE(indicators, '{}'::jsonb) ||
            jsonb_build_object(v_indicator_key,
                CASE
                    WHEN dwa.week_atr IS NOT NULL THEN ROUND(dwa.week_atr::numeric, 2)
                    ELSE NULL
                END
            ),
            updated_at = CURRENT_TIMESTAMP
        FROM daily_with_week_atr dwa
        WHERE daily_candles.candle_key_id = dwa.candle_key_id
        AND dwa.week_atr IS NOT NULL
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