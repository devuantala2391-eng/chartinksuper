-- Fixed daily SuperTrend function
CREATE OR REPLACE FUNCTION calculate_daily_supertrend_for_symbol(
    p_symbol TEXT,
    p_period INTEGER,
    p_multiplier NUMERIC,
    p_force_recalculate BOOLEAN DEFAULT FALSE
)
RETURNS TABLE(
    updated_rows INTEGER,
    execution_time_ms INTEGER,
    status TEXT,
    indicator_key TEXT,
    direction_key TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_start_time TIMESTAMP := clock_timestamp();
    v_updated_rows INTEGER := 0;
    v_indicator_key TEXT;
    v_direction_key TEXT;
    v_atr_key TEXT;
    rec RECORD;
    v_final_upper NUMERIC := NULL;
    v_final_lower NUMERIC := NULL;
    v_trend INTEGER := NULL;
BEGIN
    -- Generate indicator keys
    v_indicator_key := 'daily_supertrend_' || p_period || '_' || format_decimal_param(p_multiplier);
    v_direction_key := v_indicator_key || '_direction';
    v_atr_key := 'daily_atr_' || p_period;

    -- Process candles sequentially with CORRECTED SuperTrend algorithm
    FOR rec IN
        SELECT
            candle_key_id,
            candle_sequence_number,
            high,
            low,
            close,
            (indicators->v_atr_key)::numeric as atr
        FROM daily_candles
        WHERE symbol = p_symbol
        AND indicators ? v_atr_key
        AND (indicators->v_atr_key) IS NOT NULL
        ORDER BY candle_sequence_number
    LOOP
        DECLARE
            v_hl2 NUMERIC := (rec.high + rec.low) / 2.0;
            v_basic_upper NUMERIC := v_hl2 + (p_multiplier * rec.atr);
            v_basic_lower NUMERIC := v_hl2 - (p_multiplier * rec.atr);
            v_supertrend NUMERIC;
            v_direction INTEGER;
        BEGIN
            -- CORRECTED BAND PERSISTENCE RULES
            IF v_final_upper IS NULL THEN
                -- First candle
                v_final_upper := v_basic_upper;
                v_final_lower := v_basic_lower;
            ELSE
                -- CORRECTED BAND PERSISTENCE LOGIC
                IF v_trend IS NULL OR v_trend = 0 THEN
                    -- Downtrend: Upper band can only decrease or stay same
                    IF v_basic_upper < v_final_upper THEN
                        v_final_upper := v_basic_upper;
                    END IF;
                    -- Lower band resets to current basic lower
                    v_final_lower := v_basic_lower;
                ELSE
                    -- Uptrend: Lower band can only increase or stay same
                    IF v_basic_lower > v_final_lower THEN
                        v_final_lower := v_basic_lower;
                    END IF;
                    -- Upper band resets to current basic upper
                    v_final_upper := v_basic_upper;
                END IF;
            END IF;

            -- CORRECTED TREND DETERMINATION
            IF v_trend IS NULL THEN
                -- Initial trend: downtrend if close <= upper band
                v_direction := CASE WHEN rec.close <= v_final_upper THEN 0 ELSE 1 END;
            ELSE
                -- Trend change logic
                IF v_trend = 1 THEN -- Previous uptrend
                    IF rec.close <= v_final_lower THEN
                        v_direction := 0; -- Switch to downtrend
                    ELSE
                        v_direction := 1; -- Continue uptrend
                    END IF;
                ELSE -- Previous downtrend (v_trend = 0)
                    IF rec.close >= v_final_upper THEN
                        v_direction := 1; -- Switch to uptrend
                    ELSE
                        v_direction := 0; -- Continue downtrend
                    END IF;
                END IF;
            END IF;

            -- SuperTrend value based on trend direction
            IF v_direction = 1 THEN
                v_supertrend := ROUND(v_final_lower, 2); -- Uptrend: use lower band
            ELSE
                v_supertrend := ROUND(v_final_upper, 2); -- Downtrend: use upper band
            END IF;

            -- Update the candle with SuperTrend values
            UPDATE daily_candles
            SET indicators = COALESCE(indicators, '{}'::jsonb) ||
                jsonb_build_object(
                    v_indicator_key, v_supertrend,
                    v_direction_key, v_direction
                ),
                updated_at = CURRENT_TIMESTAMP
            WHERE candle_key_id = rec.candle_key_id;

            v_updated_rows := v_updated_rows + 1;
            v_trend := v_direction;
        END;
    END LOOP;

    RETURN QUERY SELECT
        v_updated_rows,
        EXTRACT(MILLISECONDS FROM clock_timestamp() - v_start_time)::INTEGER,
        'SUCCESS'::TEXT,
        v_indicator_key,
        v_direction_key;

EXCEPTION
    WHEN OTHERS THEN
        RETURN QUERY SELECT
            0,
            EXTRACT(MILLISECONDS FROM clock_timestamp() - v_start_time)::INTEGER,
            ('ERROR: ' || SQLERRM)::TEXT,
            v_indicator_key,
            v_direction_key;
END;
$$;