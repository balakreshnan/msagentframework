# covered_call_screener_oct3_2025.py
# Finds covered call candidates expiring on 2025-10-03
# Excludes earnings/ex-dividend events before expiry
# Dependencies: yfinance, pandas, numpy, scipy, ta

import yfinance as yf
import pandas as pd
import numpy as np
from scipy.stats import norm
import math
import datetime


# ---------------------------
# CONFIG - RELAXED FILTERS
# ---------------------------

TICKERS_SOURCE = "SP500"  # "SP500" or "CUSTOM"
CUSTOM_TICKERS = ["AAPL","MSFT","AMD","NVDA","TSLA","AMZN","META"]


MODE = "safe"  # "safe" or "aggressive"
MIN_AVG_VOLUME = 100_000  # Reduced from 200k
MIN_OPEN_INTEREST = 50    # Reduced from 100
MAX_BID_ASK_SPREAD = 0.30 # Increased from 0.20
RISK_FREE_RATE = 0.045    # Updated to current rates


# Relaxed mode settings
MODES = {
    "safe": {
        "max_delta": 0.30,      # Increased from 0.20
        "min_moneyness": 1.02,  # Reduced from 1.05
        "min_roi": 0.003        # Reduced from 0.005
    },
    "aggressive": {
        "max_delta": 0.45,      # Increased from 0.35
        "min_moneyness": 1.00,  # Reduced from 1.02
        "min_roi": 0.005        # Reduced from 0.007
    }
}

# Updated target expiry to a future date
TARGET_EXPIRY = "2025-11-15"  # Changed from past date
OUTPUT_CSV = f"covered_call_candidates_{TARGET_EXPIRY}.csv"

# ---------------------------
# Helpers
# ---------------------------

def bs_call_delta(S, K, T, r, sigma):
    if sigma <= 0 or T <= 0:
        return np.nan
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    return float(norm.cdf(d1))


def get_sp500_tickers():
    # Expanded list of liquid tickers
    return [
        "AAPL","MSFT","AMZN","GOOGL","META","NVDA","TSLA","BRK-B","JPM","JNJ",
        "V","PG","UNH","HD","MA","DIS","PYPL","ADBE","CRM","NFLX",
        "CMCSA","XOM","PFE","VZ","KO","INTC","ABT","PEP","CSCO","TMO"
    ]

# ---------------------------
# Build ticker list
# ---------------------------

if TICKERS_SOURCE == "SP500":
    TICKERS = get_sp500_tickers()
else:
    TICKERS = CUSTOM_TICKERS


results = []
target_exp_ts = pd.to_datetime(TARGET_EXPIRY).date()

# Debug counters
debug_stats = {
    'total_processed': 0,
    'no_data': 0,
    'low_volume': 0,
    'technical_filter': 0,
    'earnings_skip': 0,
    'no_options': 0,
    'no_target_expiry': 0,
    'no_calls': 0,
    'no_candidates_after_filter': 0,
    'successful': 0
}

print(f"Screening for expiry: {TARGET_EXPIRY}")
print(f"Mode: {MODE}")
print(f"Processing {len(TICKERS)} tickers...")

for ticker in TICKERS:
    try:
        debug_stats['total_processed'] += 1
        print(f"Processing {ticker}...")
        
        stock = yf.Ticker(ticker)
        hist = stock.history(period="3mo", interval="1d")
        if hist.empty or len(hist) < 20:  # Reduced from 40
            debug_stats['no_data'] += 1
            print(f"  {ticker}: Insufficient historical data")
            continue

        latest_price = hist['Close'].iloc[-1]
        avg_vol = hist['Volume'].rolling(20).mean().iloc[-1]

        # Relaxed technical analysis
        ma20 = hist['Close'].rolling(20).mean().iloc[-1] if len(hist) >= 20 else latest_price
        ma50 = hist['Close'].rolling(50).mean().iloc[-1] if len(hist) >= 50 else ma20
        
        # RSI calculation with fallback
        change = hist['Close'].diff()
        gain = change.clip(lower=0).rolling(14).mean()
        loss = -change.clip(upper=0).rolling(14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        latest_rsi = rsi.iloc[-1] if not rsi.empty else 50  # Default to neutral

        if avg_vol < MIN_AVG_VOLUME:
            debug_stats['low_volume'] += 1
            print(f"  {ticker}: Low volume ({avg_vol:,.0f} < {MIN_AVG_VOLUME:,})")
            continue

        # More relaxed technical filter
        if not (latest_price > ma20 * 0.95 and 30 <= latest_rsi <= 80):  # Relaxed RSI range
            debug_stats['technical_filter'] += 1
            print(f"  {ticker}: Failed technical filter (RSI: {latest_rsi:.1f}, Price vs MA20: {latest_price/ma20:.3f})")
            continue

        # Skip earnings check for now to get more candidates
        skip_due_to_events = False
        # Commented out earnings check
        # try:
        #     cal = stock.calendar
        #     if isinstance(cal, pd.DataFrame) and not cal.empty:
        #         for val in cal.values.flatten():
        #             try:
        #                 dt = pd.to_datetime(val).date()
        #                 if dt <= target_exp_ts:
        #                     skip_due_to_events = True
        #                     break
        #             except: continue
        # except: pass
        
        if skip_due_to_events:
            debug_stats['earnings_skip'] += 1
            print(f"  {ticker}: Skipped due to earnings/ex-div")
            continue

        try:
            options_dates = stock.options
        except:
            options_dates = []

        if not options_dates:
            debug_stats['no_options'] += 1
            print(f"  {ticker}: No options available")
            continue

        # Find closest expiry to target
        expiry_dates = [pd.to_datetime(x).date() for x in options_dates]
        
        # If exact target not found, find closest future expiry
        future_expiries = [d for d in expiry_dates if d >= target_exp_ts]
        if not future_expiries:
            debug_stats['no_target_expiry'] += 1
            print(f"  {ticker}: No suitable expiry found")
            continue
        
        closest_expiry = min(future_expiries, key=lambda x: abs((x - target_exp_ts).days))
        next_exp = [opt for opt in options_dates if pd.to_datetime(opt).date() == closest_expiry][0]
        
        opt_chain = stock.option_chain(next_exp)
        calls = opt_chain.calls
        if calls.empty:
            debug_stats['no_calls'] += 1
            print(f"  {ticker}: No call options for expiry")
            continue

        calls = calls.copy()
        calls['mid'] = (calls['bid'] + calls['ask']) / 2
        calls['moneyness'] = calls['strike'] / latest_price
        calls['premium_roi'] = calls['lastPrice'] / latest_price

        exp_date = pd.to_datetime(next_exp).date()
        days_to_exp = (exp_date - datetime.date.today()).days
        days_to_exp = max(days_to_exp, 1)
        T = days_to_exp / 365.0

        # Delta calculation with fallback
        if 'delta' not in calls.columns or calls['delta'].isnull().all():
            if 'impliedVolatility' in calls.columns:
                calls['est_delta'] = calls.apply(
                    lambda row: bs_call_delta(latest_price, row['strike'], T, RISK_FREE_RATE, 
                                            max(row.get('impliedVolativity', 0.2), 0.1))
                    if not np.isnan(row.get('impliedVolatility', np.nan)) else 0.5,
                    axis=1
                )
                calls['delta_used'] = calls.get('delta', calls['est_delta']).fillna(calls['est_delta'])
            else:
                # Rough delta estimate based on moneyness
                calls['delta_used'] = np.where(calls['moneyness'] < 1.0, 
                                             0.7 - (1.0 - calls['moneyness']) * 2, 
                                             0.3 / calls['moneyness'])
        else:
            calls['delta_used'] = calls['delta'].fillna(0.5)

        mode_cfg = MODES.get(MODE, MODES['safe'])
        
        # Apply filters progressively to see where candidates are lost
        print(f"  {ticker}: Starting with {len(calls)} calls")
        
        step1 = calls[calls['moneyness'] >= mode_cfg['min_moneyness']]
        print(f"  {ticker}: After moneyness filter: {len(step1)}")
        
        step2 = step1[step1['delta_used'] <= mode_cfg['max_delta']]
        print(f"  {ticker}: After delta filter: {len(step2)}")
        
        step3 = step2[step2['premium_roi'] >= mode_cfg['min_roi']]
        print(f"  {ticker}: After ROI filter: {len(step3)}")
        
        step4 = step3[step3['openInterest'] >= MIN_OPEN_INTEREST]
        print(f"  {ticker}: After open interest filter: {len(step4)}")
        
        # More lenient bid-ask spread filter
        valid_spreads = step4[(step4['mid'] > 0) & 
                             ((step4['ask'] - step4['bid']) / np.maximum(step4['mid'], 0.01) <= MAX_BID_ASK_SPREAD)]
        print(f"  {ticker}: After spread filter: {len(valid_spreads)}")
        
        candidates = valid_spreads
        
        if candidates.empty:
            debug_stats['no_candidates_after_filter'] += 1
            print(f"  {ticker}: No candidates after all filters")
            continue

        candidates['score'] = candidates['premium_roi'] / (candidates['delta_used'] + 1e-9)
        best = candidates.sort_values(['score','premium_roi'], ascending=False).iloc[0]

        results.append({
            'Ticker': ticker,
            'Price': round(latest_price, 2),
            'Strike': best['strike'],
            'DaysToExp': days_to_exp,
            'Premium': round(best['lastPrice'], 2),
            'Mid': round(best['mid'], 2),
            'ROI_week_pct': round(best['premium_roi'] * 100, 3),
            'Delta': round(best['delta_used'], 3) if not np.isnan(best['delta_used']) else None,
            'OpenInterest': int(best['openInterest']),
            'IV': round(best.get('impliedVolatility', np.nan), 3) if not np.isnan(best.get('impliedVolatility', np.nan)) else None,
            'Expiration': next_exp,
            'Moneyness': round(best['moneyness'], 3),
            'Score': round(best['score'], 3)
        })
        debug_stats['successful'] += 1
        print(f"  {ticker}: ✓ Added candidate (Strike: {best['strike']}, ROI: {best['premium_roi']*100:.2f}%)")
        
    except Exception as e:
        print(f"  {ticker}: Error - {e}")
        continue

# Results and debugging
results_df = pd.DataFrame(results)

print("\n" + "="*50)
print("SCREENING RESULTS")
print("="*50)
print(f"Total tickers processed: {debug_stats['total_processed']}")
print(f"No data: {debug_stats['no_data']}")
print(f"Low volume: {debug_stats['low_volume']}")
print(f"Failed technical filter: {debug_stats['technical_filter']}")
print(f"Earnings skip: {debug_stats['earnings_skip']}")
print(f"No options: {debug_stats['no_options']}")
print(f"No target expiry: {debug_stats['no_target_expiry']}")
print(f"No calls: {debug_stats['no_calls']}")
print(f"No candidates after filters: {debug_stats['no_candidates_after_filter']}")
print(f"Successful candidates: {debug_stats['successful']}")

if not results_df.empty:
    results_df = results_df.sort_values(by='ROI_week_pct', ascending=False)
    results_df.to_csv(OUTPUT_CSV, index=False)
    print(f"\n✓ Saved {len(results_df)} candidates to {OUTPUT_CSV}")
    print("\nTop candidates:")
    print(results_df.head(10).to_string(index=False))
else:
    print(f"\n❌ No candidates found with current filters.")
    print(f"Try:")
    print(f"1. Change MODE to 'aggressive'")
    print(f"2. Update TARGET_EXPIRY to a future date")
    print(f"3. Reduce MIN_OPEN_INTEREST or MIN_AVG_VOLUME")