import requests
from bs4 import BeautifulSoup
import yfinance as yf
import csv
import time
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
            if len(cols) < 4:
                continue
            
            # Search the ENTIRE row text for the target name
            row_text = " ".join([col.get_text(strip=True) for col in cols]).lower()
            
            for target_name, config in TARGETS.items():
                if config["source"] != source_key:
                    continue
                
                clean_target = target_name.replace(" ", "").lower()
                if clean_target in row_text:
                    # Find exactly which column holds the index name
                    name_col_idx = -1
                    for i, col in enumerate(cols):
                        if clean_target in col.get_text(strip=True).lower().replace(" ", ""):
                            name_col_idx = i
                            break
                    
                    if name_col_idx != -1:
                        if len(cols) >= 8: # HK/China format
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
                        else: # World format (Index name might be in col 0 or col 1)
                            results[target_name] = {
                                "Last": clean_text(cols[name_col_idx + 1].get_text(strip=True)),
                                "Change": clean_text(cols[name_col_idx + 2].get_text(strip=True)),
                                "Change %": clean_text(cols[name_col_idx + 3].get_text(strip=True)),
                                "Turnover": "N/A", "High": "N/A", "Low": "N/A", "Weekly Chg %": "N/A",
                                "Sources": [URLS[source_key]]
                            }
                        print(f"✅ AASTOCKS: Found {target_name} at {results[target_name]['Last']}")
    return results

def get_yfinance_data(ticker_symbol, target_name):
    if not ticker_symbol:
        return None
    try:
        print(f"🔄 Trying Yahoo Finance fallback for {target_name} ({ticker_symbol})...")
        time.sleep(2)
        ticker = yf.Ticker(ticker_symbol)
        hist = ticker.history(period="5d")
        if hist.empty:
            print(f"⚠️ Yahoo Finance returned empty for {ticker_symbol}")
            return None
        
        last = hist.iloc[-1]
        prev_close = hist.iloc[-2]['Close'] if len(hist) > 1 else last['Close']
        first = hist.iloc[0]['Close']
        change = last['Close'] - prev_close
        
        print(f"✅ Yahoo Finance SUCCESS: {target_name} = {last['Close']:,.2f}")
        return {
            "Last": f"{last['Close']:,.2f}",
            "Change": f"{change:+,.2f}",
            "Change %": f"{(change/prev_close)*100:+.2f}%",
            "Turnover": "N/A",
            "High": f"{last['High']:,.2f}",
            "Low": f"{last['Low']:,.2f}",
            "Weekly Chg %": f"{((last['Close']-first)/first)*100:+.2f}%",
            "Sources": [f"https://finance.yahoo.com/quote/{ticker_symbol.replace('^','%5E')}/"]
        }
    except Exception as e:
        print(f"❌ Yahoo Finance failed: {e}")
        return None

def main():
    scraped_data = {}

    # 1. Scrape AASTOCKS
    for key, url in URLS.items():
        try:
            response = requests.get(url, headers=HEADERS, timeout=10)
            response.raise_for_status()
            parsed = parse_aastocks(response.text, key)
            scraped_data.update(parsed)
        except Exception as e:
            print(f"❌ Failed to scrape {url}: {e}")

    # 2. Fallback to Yahoo Finance for anything missing or N/A
    for target_name, config in TARGETS.items():
        if target_name not in scraped_data or scraped_data[target_name]["Last"] == "N/A":
            print(f"⚠️ {target_name} missing from AASTOCKS. Triggering fallback...")
            yf_data = get_yfinance_data(config["yf"], target_name)
            if yf_data:
                scraped_data[target_name] = yf_data

    # 3. Ensure all targets exist with N/A fallback
    for target_name in TARGETS:
        scraped_data.setdefault(target_name, {
            "Last": "N/A", "Change": "N/A", "Change %": "N/A", "Turnover": "N/A",
            "High": "N/A", "Low": "N/A", "Weekly Chg %": "N/A", "Sources": ["N/A"]
        })

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
                "Sources": d["Sources"][0]
            })
    print("✅ Script finished. Saved market_data.csv")

if __name__ == "__main__":
    main()
