-- =====================================================
-- CRON ALL INDICATORS CALCULATION ORCHESTRATOR
-- =====================================================
-- Master function that calculates all indicators in dependency order
-- Optimized for cron job efficiency - updates only latest candles
-- Handles dependencies (ATR before SuperTrend, etc.)
-- =====================================================

-- =====================================================
-- CRON ALL INDICATORS FOR SINGLE SYMBOL
-- =====================================================
CREATE OR REPLACE FUNCTION cron_calculate_all_indicators_for_symbol(
    p_symbol TEXT,
    p_timeframe TEXT DEFAULT 'daily'
)
RETURNS TABLE(
    indicator_name TEXT,
    indicator_key TEXT,
    updated_rows INTEGER,
    execution_time_ms INTEGER,
    status TEXT,
    indicator_value TEXT,
    warning_message TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_start_time TIMESTAMP := clock_timestamp();
    v_total_time INTEGER := 0;
    rec RECORD;
    v_active_indicators RECORD;
    v_parameters JSONB;
    v_period INTEGER;
    v_multiplier NUMERIC;
    v_timeframes TEXT[];
    v_indicator_timeframes JSONB;
BEGIN
    RAISE NOTICE 'Processing all cron indicators for symbol: % [%]', p_symbol, p_timeframe;

    -- Get active indicators from indicator_registry table (specific to the requested timeframe)
    FOR v_active_indicators IN
        SELECT
            CASE
                WHEN LOWER(config_data->>'name') = 'bollingerbands' THEN 'bollinger_bands'
                WHEN LOWER(config_data->>'name') = 'rsi' THEN 'rsi'
                WHEN LOWER(config_data->>'name') = 'atr' THEN 'atr'
                WHEN LOWER(config_data->>'name') = 'ema' THEN 'ema'
                WHEN LOWER(config_data->>'name') = 'sma' THEN 'sma'
                WHEN LOWER(config_data->>'name') = 'supertrend' THEN 'supertrend'
                WHEN LOWER(config_data->>'name') = 'percentagechange' THEN 'percentage_change'
                ELSE LOWER(config_data->>'name')
            END as ind_name,
            config_data->'params' as parameters,
            jsonb_build_array(config_data->>'timeframe') as timeframes
        FROM indicator_registry ir
        WHERE config_data->>'timeframe' = p_timeframe
        ORDER BY CASE
            WHEN LOWER(config_data->>'name') = 'atr' THEN 1        -- ATR first (dependency for SuperTrend)
            WHEN LOWER(config_data->>'name') = 'rsi' THEN 2        -- RSI
            WHEN LOWER(config_data->>'name') = 'ema' THEN 3        -- EMA
            WHEN LOWER(config_data->>'name') = 'sma' THEN 4        -- SMA
            WHEN LOWER(config_data->>'name') = 'bollingerbands' THEN 5  -- Bollinger Bands
            WHEN LOWER(config_data->>'name') = 'supertrend' THEN 6 -- SuperTrend (requires ATR)
            WHEN LOWER(config_data->>'name') = 'percentagechange' THEN 7  -- Percentage Change
            ELSE 99
        END, config_data->>'name', config_data->'params'
    LOOP
        -- Parse parameters
        v_parameters := COALESCE(v_active_indicators.parameters::JSONB, '{}'::JSONB);
        v_period := COALESCE((v_parameters ->> 'period')::INTEGER,
                           CASE
                               WHEN v_active_indicators.ind_name = 'rsi' THEN 14
                               WHEN v_active_indicators.ind_name = 'atr' THEN 14
                               WHEN v_active_indicators.ind_name = 'ema' THEN 20
                               WHEN v_active_indicators.ind_name = 'sma' THEN 20
                               WHEN v_active_indicators.ind_name = 'bollinger_bands' THEN 20
                               WHEN v_active_indicators.ind_name = 'supertrend' THEN 10
                               ELSE 14
                           END);
        v_multiplier := COALESCE((v_parameters ->> 'multiplier')::NUMERIC, 2.0);

        -- Parse timeframes
        v_indicator_timeframes := COALESCE(v_active_indicators.timeframes::JSONB, '["daily"]'::JSONB);

        -- Check if this timeframe is enabled for this indicator
        IF NOT (v_indicator_timeframes ? p_timeframe) THEN
            CONTINUE;
        END IF;

        -- Calculate indicator based on type
        IF v_active_indicators.ind_name = 'rsi' THEN
            FOR rec IN
                SELECT * FROM cron_calculate_rsi_for_symbol(p_symbol, p_timeframe, v_period)
            LOOP
                RETURN QUERY SELECT 'RSI',
                                   rec.indicator_key,
                                   rec.updated_rows,
                                   rec.execution_time_ms,
                                   rec.status,
                                   COALESCE(rec.rsi_value::TEXT, 'NULL'),
                                   rec.warning_message;
                v_total_time := v_total_time + rec.execution_time_ms;
            END LOOP;

        ELSIF v_active_indicators.ind_name = 'atr' THEN
            FOR rec IN
                SELECT * FROM cron_calculate_atr_for_symbol(p_symbol, p_timeframe, v_period)
            LOOP
                RETURN QUERY SELECT 'ATR',
                                   rec.indicator_key,
                                   rec.updated_rows,
                                   rec.execution_time_ms,
                                   rec.status,
                                   COALESCE(rec.atr_value::TEXT, 'NULL'),
                                   rec.warning_message;
                v_total_time := v_total_time + rec.execution_time_ms;
            END LOOP;

        ELSIF v_active_indicators.ind_name = 'ema' THEN
            FOR rec IN
                SELECT * FROM cron_calculate_ema_for_symbol(p_symbol, p_timeframe, v_period)
            LOOP
                RETURN QUERY SELECT 'EMA',
                                   rec.indicator_key,
                                   rec.updated_rows,
                                   rec.execution_time_ms,
                                   rec.status,
                                   COALESCE(rec.ema_value::TEXT, 'NULL'),
                                   rec.warning_message;
                v_total_time := v_total_time + rec.execution_time_ms;
            END LOOP;

        ELSIF v_active_indicators.ind_name = 'sma' THEN
            FOR rec IN
                SELECT * FROM cron_calculate_sma_for_symbol(p_symbol, p_timeframe, v_period)
            LOOP
                RETURN QUERY SELECT 'SMA',
                                   rec.indicator_key,
                                   rec.updated_rows,
                                   rec.execution_time_ms,
                                   rec.status,
                                   COALESCE(rec.sma_value::TEXT, 'NULL'),
                                   rec.warning_message;
                v_total_time := v_total_time + rec.execution_time_ms;
            END LOOP;

        ELSIF v_active_indicators.ind_name = 'bollinger_bands' THEN
            FOR rec IN
                SELECT * FROM cron_calculate_bollinger_bands_for_symbol(p_symbol, p_timeframe, v_period, v_multiplier)
            LOOP
                RETURN QUERY SELECT 'Bollinger Bands',
                                   rec.indicator_key,
                                   rec.updated_rows,
                                   rec.execution_time_ms,
                                   rec.status,
                                   COALESCE(rec.bb_value::TEXT, 'NULL'),
                                   rec.warning_message;
                v_total_time := v_total_time + rec.execution_time_ms;
            END LOOP;

        ELSIF v_active_indicators.ind_name = 'supertrend' THEN
            FOR rec IN
                SELECT * FROM cron_calculate_supertrend_for_symbol(p_symbol, p_timeframe, v_period, v_multiplier)
            LOOP
                RETURN QUERY SELECT 'SuperTrend',
                                   rec.indicator_key,
                                   rec.updated_rows,
                                   rec.execution_time_ms,
                                   rec.status,
                                   COALESCE(rec.supertrend_value::TEXT, 'NULL'),
                                   rec.warning_message;
                v_total_time := v_total_time + rec.execution_time_ms;
            END LOOP;

        ELSIF v_active_indicators.ind_name = 'percentage_change' THEN
            FOR rec IN
                SELECT * FROM cron_calculate_percentage_change_for_symbol(p_symbol, p_timeframe)
            LOOP
                RETURN QUERY SELECT 'Percentage Change',
                                   rec.indicator_key,
                                   rec.updated_rows,
                                   rec.execution_time_ms,
                                   rec.status,
                                   COALESCE(rec.percentage_value::TEXT, 'NULL'),
                                   rec.warning_message;
                v_total_time := v_total_time + rec.execution_time_ms;
            END LOOP;

        END IF;
    END LOOP;

    -- Return summary
    RETURN QUERY SELECT 'SUMMARY',
                       'total_execution_time',
                       0,
                       v_total_time,
                       'COMPLETED',
                       'Total time: ' || v_total_time || 'ms',
                       NULL::TEXT;
END;
$$;

-- =====================================================
-- CRON ALL INDICATORS FOR ALL SYMBOLS (BATCH)
-- =====================================================
CREATE OR REPLACE FUNCTION cron_calculate_all_indicators_batch(
    p_symbols TEXT[] DEFAULT NULL,
    p_timeframes TEXT[] DEFAULT ARRAY['daily']
)
RETURNS TABLE(
    symbol TEXT,
    timeframe TEXT,
    indicator_name TEXT,
    indicator_key TEXT,
    updated_rows INTEGER,
    execution_time_ms INTEGER,
    status TEXT,
    indicator_value TEXT,
    warning_message TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_symbol TEXT;
    v_timeframe TEXT;
    v_symbols TEXT[];
    rec RECORD;
    v_start_time TIMESTAMP := clock_timestamp();
    v_total_symbols INTEGER := 0;
    v_processed_symbols INTEGER := 0;
BEGIN
    -- Get symbols to process
    IF p_symbols IS NULL THEN
        SELECT array_agg(DISTINCT daily_candles.symbol ORDER BY daily_candles.symbol)
        INTO v_symbols
        FROM daily_candles;
    ELSE
        v_symbols := p_symbols;
    END IF;

    v_total_symbols := array_length(v_symbols, 1);
    RAISE NOTICE 'Starting cron indicator calculation for % symbols across % timeframes',
                 v_total_symbols, array_length(p_timeframes, 1);

    -- Process each symbol and timeframe combination
    FOREACH v_symbol IN ARRAY v_symbols
    LOOP
        FOREACH v_timeframe IN ARRAY p_timeframes
        LOOP
            FOR rec IN
                SELECT * FROM cron_calculate_all_indicators_for_symbol(v_symbol, v_timeframe)
            LOOP
                RETURN QUERY SELECT v_symbol,
                                   v_timeframe,
                                   rec.indicator_name,
                                   rec.indicator_key,
                                   rec.updated_rows,
                                   rec.execution_time_ms,
                                   rec.status,
                                   rec.indicator_value,
                                   rec.warning_message;
            END LOOP;
        END LOOP;

        v_processed_symbols := v_processed_symbols + 1;

        -- Log progress every 50 symbols
        IF v_processed_symbols % 50 = 0 THEN
            RAISE NOTICE 'Processed % / % symbols',
                         v_processed_symbols, v_total_symbols;
        END IF;
    END LOOP;

    -- Final summary
    RAISE NOTICE 'Completed cron indicator calculation for % symbols in %ms',
                 v_total_symbols,
                 EXTRACT(MILLISECONDS FROM clock_timestamp() - v_start_time)::INTEGER;
END;
$$;