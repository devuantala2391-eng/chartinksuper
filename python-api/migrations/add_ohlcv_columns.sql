-- Migration: Add weekly and monthly OHLCV columns to daily_candles table
-- Date: 2025-08-29
-- Purpose: Move OHLCV data from JSONB indicators to dedicated columns for better performance

-- Add weekly OHLCV columns
ALTER TABLE daily_candles 
ADD COLUMN IF NOT EXISTS weekly_open DECIMAL(20,6) DEFAULT NULL,
ADD COLUMN IF NOT EXISTS weekly_high DECIMAL(20,6) DEFAULT NULL,
ADD COLUMN IF NOT EXISTS weekly_low DECIMAL(20,6) DEFAULT NULL,
ADD COLUMN IF NOT EXISTS weekly_close DECIMAL(20,6) DEFAULT NULL,
ADD COLUMN IF NOT EXISTS weekly_volume BIGINT DEFAULT NULL;

-- Add monthly OHLCV columns  
ALTER TABLE daily_candles 
ADD COLUMN IF NOT EXISTS monthly_open DECIMAL(20,6) DEFAULT NULL,
ADD COLUMN IF NOT EXISTS monthly_high DECIMAL(20,6) DEFAULT NULL,
ADD COLUMN IF NOT EXISTS monthly_low DECIMAL(20,6) DEFAULT NULL,
ADD COLUMN IF NOT EXISTS monthly_close DECIMAL(20,6) DEFAULT NULL,
ADD COLUMN IF NOT EXISTS monthly_volume BIGINT DEFAULT NULL;

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_daily_candles_weekly_high ON daily_candles(weekly_high) WHERE weekly_high IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_daily_candles_weekly_low ON daily_candles(weekly_low) WHERE weekly_low IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_daily_candles_weekly_volume ON daily_candles(weekly_volume) WHERE weekly_volume IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_daily_candles_monthly_high ON daily_candles(monthly_high) WHERE monthly_high IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_daily_candles_monthly_low ON daily_candles(monthly_low) WHERE monthly_low IS NOT NULL;  
CREATE INDEX IF NOT EXISTS idx_daily_candles_monthly_volume ON daily_candles(monthly_volume) WHERE monthly_volume IS NOT NULL;

-- Add comments for documentation
COMMENT ON COLUMN daily_candles.weekly_open IS 'Weekly opening price (first trading day of the week)';
COMMENT ON COLUMN daily_candles.weekly_high IS 'Weekly high price (maximum from week start to current day)';
COMMENT ON COLUMN daily_candles.weekly_low IS 'Weekly low price (minimum from week start to current day)';
COMMENT ON COLUMN daily_candles.weekly_close IS 'Weekly closing price (current day closing price)';
COMMENT ON COLUMN daily_candles.weekly_volume IS 'Weekly cumulative volume (sum from week start to current day)';
COMMENT ON COLUMN daily_candles.monthly_open IS 'Monthly opening price (first trading day of the month)';
COMMENT ON COLUMN daily_candles.monthly_high IS 'Monthly high price (maximum from month start to current day)';
COMMENT ON COLUMN daily_candles.monthly_low IS 'Monthly low price (minimum from month start to current day)';
COMMENT ON COLUMN daily_candles.monthly_close IS 'Monthly closing price (current day closing price)';
COMMENT ON COLUMN daily_candles.monthly_volume IS 'Monthly cumulative volume (sum from month start to current day)';