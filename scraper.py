import requests
from bs4 import BeautifulSoup
import yfinance as yf
import json
import csv
from datetime import datetime, timezone, timedelta

# Malaysia Time is UTC+8
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
    """Remove arrow symbols and clean whitespace."""
    return text.replace("▲", "").replace("▼", "").replace("+", "+").strip()

def parse_aastocks(html, source_key):
    soup = BeautifulSoup(html, 'html.parser')
    results = {}
    for table in soup.find_all('table'):
        rows = table.find_all('tr')
        for row in rows:
            cols = row.find_all(['td', 'th'])
            if len(cols) >= 8:
                index_name = cols[0].get_text(strip=True)
                for target_name, config in TARGETS.items():
                    if config["source"] == source_key and target_name in index_name:
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
    return results

def get_yfinance_data(ticker_symbol):
    try:
        ticker = yf.Ticker(ticker_symbol)
        hist = ticker.history(period="5d")
        if hist.empty:
            return None
        last = hist.iloc[-1]
        prev_close = hist.iloc[-2]['Close'] if len(hist) > 1 else last['Close']
        first_of_period = hist.iloc[0]['Close']
        
        change = last['Close'] - prev_close
        change_pct = (change / prev_close) * 100
        weekly_chg_pct = ((last['Close'] - first_of_period) / first_of_period) * 100
        
        return {
            "Last": f"{last['Close']:,.2f}",
            "Change": f"{change:+,.2f}",
            "Change %": f"{change_pct:+.2f}%",
            "Turnover": "N/A",
            "High": f"{last['High']:,.2f}",
            "Low": f"{last['Low']:,.2f}",
            "Weekly Chg %": f"{weekly_chg_pct:+.2f}%",
            "Sources": [f"https://finance.yahoo.com/quote/{ticker_symbol.replace('^', '%5E')}/"]
        }
    except Exception:
        return None

def main():
    scraped_data = {}
    used_sources = set()

    # 1. Scrape AASTOCKS
    for key, url in URLS.items():
        try:
            response = requests.get(url, headers=HEADERS, timeout=10)
            response.raise_for_status()
            parsed = parse_aastocks(response.text, key)
            scraped_data.update(parsed)
            if parsed:
                used_sources.add(url)
        except Exception as e:
            print(f"Failed to scrape {url}: {e}")

    # 2. Fallback to Yahoo Finance if data is missing or incomplete
    for target_name, config in TARGETS.items():
        if target_name not in scraped_data or scraped_data[target_name]["Last"] == "N/A":
            yf_data = get_yfinance_data(config["yf"])
            if yf_data:
                scraped_data[target_name] = yf_data
                used_sources.add(yf_data["Sources"][0])

    # 3. Ensure all targets exist with N/A fallback
    for target_name in TARGETS.keys():
        if target_name not in scraped_data:
            scraped_data[target_name] = {
                "Last": "N/A", "Change": "N/A", "Change %": "N/A",
                "Turnover": "N/A", "High": "N/A", "Low": "N/A", "Weekly Chg %": "N/A",
                "Sources": ["N/A"]
            }

    # 4. Format Output
    order = ["HSI", "HS TECH", "HS Red Chips", "HSCEI", "SSE", "S&P 500"]
    dataset_write_rows = []
    sources_list = []

    for idx in order:
        data = scraped_data[idx]
        sources_list.extend(data["Sources"])
        dataset_write_rows.append({
            "values": {
                "Data Timestamp": TIMESTAMP,
                "Index": idx,
                "Last": data["Last"],
                "Change": data["Change"],
                "Change %": data["Change %"],
                "Turnover": data["Turnover"],
                "High": data["High"],
                "Low": data["Low"],
                "Weekly Chg %": data["Weekly Chg %"],
                "Sources": ", ".join(list(dict.fromkeys(data["Sources"]))) # Deduplicate
            }
        })

    # --- NEW: SAVE TO CSV FILE ---
    csv_filename = "market_data.csv"
    fieldnames = ["Data Timestamp", "Index", "Last", "Change", "Change %", "Turnover", "High", "Low", "Weekly Chg %", "Sources"]
    
    with open(csv_filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in dataset_write_rows:
            writer.writerow(row["values"])
    
    print(f"✅ Successfully saved data to {csv_filename}")
    
    # Also print a quick summary to console for the GitHub Actions log
    print("\n--- Console Output Summary ---")
    print(f"Timestamp: {TIMESTAMP}")
    for row in dataset_write_rows:
        print(f"{row['values']['Index']}: {row['values']['Last']} ({row['values']['Change %']})")

if __name__ == "__main__":
    main()
