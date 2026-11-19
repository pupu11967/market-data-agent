import requests
from bs4 import BeautifulSoup
import yfinance as yf
import csv
import time
import json
from datetime import datetime, timezone, timedelta

MYT = timezone(timedelta(hours=8))
TIMESTAMP = datetime.now(MYT).strftime("%Y/%m/%d %H:%M MYT")

TARGETS = {
    "HSI": {"source": "hk", "yf": None},
    "HS TECH": {"source": "hk", "yf": None},
    "HS Red Chips": {"source": "hk", "yf": None},
    "HSCEI": {"source": "hk", "yf": None},
    "SSE": {"source": "china", "yf": "000001.SS"},
    "S&P 500": {"source": "world", "yf": "^GSPC"}
}

URLS = {
    "hk": "https://www.aastocks.com/en/stocks/market/index/hk-index.aspx",
    "china": "https://www.aastocks.com/en/stocks/market/index/china-index.aspx",
    "world": "https://www.aastocks.com/en/stocks/market/index/world-index.aspx"
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def clean_text(text):
    return text.replace("▲", "").replace("▼", "").replace("+", "+").strip()

def parse_aastocks(html, source_key):
    soup = BeautifulSoup(html, 'html.parser')
    results = {}
    for table in soup.find_all('table'):
        for row in table.find_all('tr'):
            cols = row.find_all(['td', 'th'])
            for i, col in enumerate(cols):
                col_text = col.get_text(strip=True)
                clean_col = col_text.replace(" ", "").lower()
                for target_name, config in TARGETS.items():
                    if config["source"] != source_key:
                        continue
                    clean_target = target_name.replace(" ", "").lower()
                    if clean_col == clean_target:
                        if source_key in ["hk", "china"] and len(cols) >= 8:
                            results[target_name] = {
                                "Last": clean_text(cols[1].get_text(strip=True)),
                                "Change": clean_text(cols[2].get_text(strip=True)),
                                "Change %": clean_text(cols[3].get_text(strip=True)),
                                "Turnover": clean_text(cols[4].get_text(strip=True)),
                                "High": clean_text(cols[5].get_text(strip=True)),
                                "Low": clean_text(cols[6].get_text(strip=True)),
                                "Weekly Chg %": clean_text(cols[7].get_text(strip=True)),
                                "Sources": [URLS[source_key]]
                            }
                        elif source_key == "world" and len(cols) >= 5:
                            results[target_name] = {
                                "Last": clean_text(cols[i + 1].get_text(strip=True)),
                                "Change": clean_text(cols[i + 2].get_text(strip=True)),
                                "Change %": clean_text(cols[i + 3].get_text(strip=True)),
                                "Turnover": "N/A", "High": "N/A", "Low": "N/A", "Weekly Chg %": "N/A",
                                "Sources": [URLS[source_key]]
                            }
                        print(f"✅ AASTOCKS: Found {target_name} -> Last: {results[target_name]['Last']}")
    return results

def get_yfinance_data(ticker_symbol, target_name):
    if not ticker_symbol:
        return None
    
    # Try primary ticker, fallback to SPY (S&P 500 ETF) if ^GSPC is blocked
    tickers_to_try = [ticker_symbol]
    if ticker_symbol == "^GSPC":
        tickers_to_try.append("SPY")
        
    for ticker_sym in tickers_to_try:
        try:
            print(f"🔄 Trying yfinance for {target_name} using {ticker_sym}...")
            time.sleep(2)
            ticker = yf.Ticker(ticker_sym)
            hist = ticker.history(period="5d")
            
            if hist.empty:
                print(f"⚠️ yfinance returned empty for {ticker_sym}")
                continue
            
            last = hist.iloc[-1]
            prev_close = hist.iloc[-2]['Close'] if len(hist) > 1 else last['Close']
            first = hist.iloc[0]['Close']
            change = last['Close'] - prev_close
            
            print(f"✅ yfinance SUCCESS: {target_name} = {last['Close']:,.2f} (via {ticker_sym})")
            return {
                "Last": f"{last['Close']:,.2f}",
                "Change": f"{change:+,.2f}",
                "Change %": f"{(change/prev_close)*100:+.2f}%",
                "Turnover": "N/A",
                "High": f"{last['High']:,.2f}",
                "Low": f"{last['Low']:,.2f}",
                "Weekly Chg %": f"{((last['Close']-first)/first)*100:+.2f}%",
                "Sources": [f"https://finance.yahoo.com/quote/{ticker_sym.replace('^','%5E')}/"]
            }
        except Exception as e:
            print(f"❌ yfinance failed for {ticker_sym}: {e}")
            continue
            
    # FALLBACK 2: Direct Yahoo Finance JSON API (Almost never blocked)
    try:
        print(f"🔄 Trying direct Yahoo Finance API for {target_name}...")
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker_symbol}"
        response = requests.get(url, headers=HEADERS, timeout=10)
        data = response.json()
        result = data['chart']['result'][0]
        meta = result['meta']
        current_price = meta['regularMarketPrice']
        previous_close = meta['previousClose']
        change = current_price - previous_close
        change_pct = (change / previous_close) * 100
        
        print(f"✅ Direct Yahoo API SUCCESS: {target_name} = {current_price:,.2f}")
        return {
            "Last": f"{current_price:,.2f}",
            "Change": f"{change:+,.2f}",
            "Change %": f"{change_pct:+.2f}%",
            "Turnover": "N/A",
            "High": f"{meta['regularMarketDayHigh']:,.2f}",
            "Low": f"{meta['regularMarketDayLow']:,.2f}",
            "Weekly Chg %": "N/A",
            "Sources": [f"https://finance.yahoo.com/quote/{ticker_symbol.replace('^','%5E')}/"]
        }
    except Exception as e:
        print(f"❌ Direct Yahoo API failed: {e}")
        
    return None

def main():
    print("🚀 STARTING SCRIPT...")
    scraped_data = {}

    # 1. Scrape AASTOCKS
    for key, url in URLS.items():
        try:
            print(f"🌐 Fetching {url}...")
            response = requests.get(url, headers=HEADERS, timeout=10)
            response.raise_for_status()
            parsed = parse_aastocks(response.text, key)
            scraped_data.update(parsed)
            if not parsed and key == "world":
                print("⚠️ WARNING: AASTOCKS World page returned NO data. Possible block or HTML change.")
        except Exception as e:
            print(f"❌ Failed to scrape {url}: {e}")

    # 2. Fallback to Yahoo Finance for anything missing or blank
    for target_name, config in TARGETS.items():
        current_data = scraped_data.get(target_name, {})
        print(f"🔍 DEBUG: {target_name} current_data = {current_data}")
        if not current_data or current_data.get("Last") == "N/A" or current_data.get("Last") == "":
            print(f"⚠️ {target_name} is missing or blank. Triggering fallbacks...")
            yf_data = get_yfinance_data(config["yf"], target_name)
            if yf_data:
                scraped_data[target_name] = yf_data
                print(f"✅ DEBUG: Successfully updated {target_name}")
            else:
                print(f"❌ DEBUG: ALL FALLBACKS FAILED for {target_name}")

    # 3. Ensure all targets exist with N/A fallback
    for target_name in TARGETS:
        if target_name not in scraped_data:
            scraped_data[target_name] = {
                "Last": "N/A", "Change": "N/A", "Change %": "N/A", "Turnover": "N/A",
                "High": "N/A", "Low": "N/A", "Weekly Chg %": "N/A", "Sources": ["N/A"]
            }

    # 🔍 FINAL CHECK
    print(f"🔍 FINAL CHECK: S&P 500 data before saving: {scraped_data.get('S&P 500')}")

    # 4. Save to CSV
    order = ["HSI", "HS TECH", "HS Red Chips", "HSCEI", "SSE", "S&P 500"]
    fieldnames = ["Data Timestamp", "Index", "Last", "Change", "Change %", "Turnover", "High", "Low", "Weekly Chg %", "Sources"]

    with open("market_data.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for idx in order:
            d = scraped_data[idx]
            writer.writerow({
                "Data Timestamp": TIMESTAMP, "Index": idx, "Last": d["Last"],
                "Change": d["Change"], "Change %": d["Change %"], "Turnover": d["Turnover"],
                "High": d["High"], "Low": d["Low"], "Weekly Chg %": d["Weekly Chg %"],
                "Sources": d["Sources"][0] if isinstance(d["Sources"], list) else d["Sources"]
            })
    print("✅ Script finished. Saved market_data.csv")

if __name__ == "__main__":
    main()
