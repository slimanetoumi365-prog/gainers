import requests
import time
import datetime
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from datetime import timezone, timedelta

# --- Configuration ---
# WARNING: REPLACE WITH YOUR NEW TOKEN
TELEGRAM_BOT_TOKEN = '8833328238:AAHD-03Tz7r2kCYxmHn4k62IGwafuv3tyjk'
TELEGRAM_CHAT_ID = '1692583809'

ALERTED_FILE = "alerted_coins_3.json"
PC_ALERT = 1.99

RAW_SYMBOLS = """
0G 1000CAT 1000CHEEMS 1000SATS 1INCH 1MBABYDOGE 2Z AAVE ACE ACH ACM ACT ACX ADA ADX AEVO AGLD AIGENSYN AI AIXBT ALCX ALGO ALICE ALLO ALPINE ALT AMP ANIME ANKR APE API3 APT ARB ARDR ARKM ARK ARPA AR ASR ASTER ASTR ATM ATOM AT AUCTION AUDIO A AVA AVAX AVNT AWE AXL AXS BABY BANANAS31 BANANA BAND BANK BARD BAR BAT BB BCH BEAMX BEL BERA BICO BIGTIME BIO BLUR BMT BNB BNSOL BNT BOME BONK BREV BROCCOLI714 C98 CAKE CATI CELO CELR CETUS CFG CFX CGPT CHIP CHR CHZ CITY CKB COMP COOKIE COTI COW CRV CTK CTSI C CVC CVX CYBER DASH DCR DEXE DGB DIA DODO DOGE DOGS DOLO DOT DUSK DYDX DYM EDEN EDU EGLD EIGEN ENA ENJ ENSO ENS EPIC ERA ESP ETC EUL FET FF FIDA FIL FLOKI FLOW FLUX FOGO FORM FRAX FTT F GALA GAS GENIUS GIGGLE GLMR GLM GMT GMX GNO GNS GPS GRT GTC GUN G HAEDAL HBAR HEI HEMI HFT HIVE HMSTR HOLO HOME HOT HUMA HYPER ICP ICX ID ILV IMX INIT INJ IOST IOTA IOTX IO IQ JASMY JOE JST JTO JUP JUV KAIA KAITO KAT KAVA KERNEL KGST KITE KMNO KNC KSM LA LAYER LAZIO LDO LINEA LINK LISTA LPT LQTY LSK LTC LUMIA LUNA LUNC MAGIC MANA MANTA MANTRA MASK MAV MBL MEGA MEME METIS MET ME MINA MIRA MITO MMT MORPHO MOVE MOVR MTL MUBARAK NEAR NEIRO NEO NEWT NEXO NFP NIGHT NIL NMR NOM NOT NXPC OGN OG ONDO ONE ONG ONT OPEN OPG OPN OP ORCA ORDI OSMO PARTI PENDLE PENGU PEOPLE PEPE PHA PIVX PIXEL PLUME PNUT POL POLYX POND PORTAL PORTO POWR PROM PROVE PSG PUMP PUNDIX PYR PYTH QI QKC QNT QTUM QUICK RAD RARE RAY RE RED RENDER REQ RESOLV REZ RIF RLC ROBO RONIN ROSE RPL RSR RUNE RVN SAGA SAHARA SAND SANTOS SAPIEN SCRT SCR SC SEI SENT SFP SHELL SHIB SIGN SKL SKY SLP SNX SOL SOLV SOMI SOPH SPELL SPK SSV STEEM STG STORJ STO STRAX STRK STX SUI SUN SUPER S SUSHI SXT SYN SYRUP TAO TFUEL THETA THE TIA TKO TLM TNSR TON TOWNS TRB TREE TRUMP TRX TST TURBO TURTLE T TUT TWT UMA UNI USUAL U VANA VANRY VELODROME VET VIC VIRTUAL VTHO WAL WAXP WCT WIF WIN WLD WLFI WOO W XAI XEC XLM XNO XPL XRP XTZ XVG XVS YB YFI YGG ZAMA ZBT ZEC ZEN ZIL ZKC ZKP ZK ZRO ZRX
"""

SYMBOLS = [s.strip() + "USDT" for s in RAW_SYMBOLS.split() if s.strip()]

session = requests.Session()
adapter = HTTPAdapter(
    pool_connections=50,
    pool_maxsize=50,
    max_retries=Retry(total=2, backoff_factor=0.1)
)
session.mount("https://", adapter)

# Morocco Timezone (GMT+1)
MOROCCO_TZ = timezone(timedelta(hours=1))

def load_json(path):
    if os.path.exists(path):
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f)

def format_number(num):
    if num >= 1_000_000:
        return f"{num / 1_000_000:.1f}M"
    elif num >= 1_000:
        return f"{num / 1_000:.1f}K"
    return f"{num:.0f}"

def send_telegram_alert(msg: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": msg}
    try:
        session.post(url, json=payload, timeout=10)
        print("[OK] Alert sent to Telegram")
    except Exception as e:
        print(f"[ERROR] Telegram error: {e}")

def get_binance_server_time() -> int:
    response = session.get("https://api.binance.com/api/v3/time")
    response.raise_for_status()
    return response.json()["serverTime"]

def seconds_until_next_15min() -> float:
    server_time_ms = get_binance_server_time()
    now = datetime.datetime.fromtimestamp(server_time_ms / 1000, tz=timezone.utc)
    next_minute = ((now.minute // 15) + 1) * 15
    if next_minute >= 60:
        target = now.replace(minute=0, second=2, microsecond=0) + datetime.timedelta(hours=1)
    else:
        target = now.replace(minute=next_minute, second=2, microsecond=0)
    return (target - now).total_seconds()

def calculate_rsi(closes, period=14):
    if len(closes) < period + 1:
        return None
    deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]
    
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))

def get_24hr_tickers():
    """Fetches all 24h tickers in one request to get volume and daily change."""
    try:
        resp = session.get("https://api.binance.com/api/v3/ticker/24hr", timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return {
            item['symbol']: {
                'vol': float(item['quoteVolume']), 
                'pc': float(item['priceChangePercent'])
            } 
            for item in data
        }
    except Exception as e:
        print(f"[WARN] Error fetching 24hr tickers: {e}")
        return {}

def scan_symbol(sym: str):
    try:
        resp = session.get(
            "https://api.binance.com/api/v3/klines",
            params={"symbol": sym, "interval": "15m", "limit": 20},
            timeout=5
        )
        resp.raise_for_status()
        data = resp.json()
        if len(data) < 16:
            return None

        closed = data[:-1]
        volumes = [float(c[5]) for c in closed]
        closes = [float(c[4]) for c in closed]

        count = 1
        for i in range(len(volumes) - 1, 0, -1):
            if volumes[i] > volumes[i - 1]:
                count += 1
            else:
                break

        if count != 3:
            return None

        streak = closed[-count:]
        last = closed[-1]
        prev = closed[-2]

        vol_ratio = volumes[-1] / volumes[-2] if volumes[-2] > 0 else 0
        streak_ratio = volumes[-1] / volumes[-count] if volumes[-count] > 0 else 0

        close_p = float(last[4])
        prev_close = float(prev[4])
        pc = ((close_p - prev_close) / prev_close) * 100

        if pc < PC_ALERT:
            return None

        green_count = sum(1 for c in streak if float(c[4]) >= float(c[1]))
        rsi = calculate_rsi(closes, period=14)

        return {
            "sym": sym.replace("USDT", ""),
            "close": close_p,
            "pc": pc,
            "vol_ratio": vol_ratio,
            "streak_ratio": streak_ratio,
            "green_count": green_count,
            "rsi": rsi,
        }
    except Exception:
        return None

def main():
    print("[START] Exact-3 Streak Scanner (15min) initialized...")
    alerted = load_json(ALERTED_FILE)
    prev_scan_syms = set()

    while True:
        try:
            secs = seconds_until_next_15min()
            now_str = datetime.datetime.now(MOROCCO_TZ).strftime('%H:%M:%S')
            print(f"[{now_str}] Sleeping {secs:.0f}s until next 15min candle...")
            time.sleep(secs)

            now_ts = time.time()
            time_str = datetime.datetime.now(MOROCCO_TZ).strftime('%H:%M')
            t0 = time.time()
            print(f"\n[SCAN] Scanning {len(SYMBOLS)} coins...")

            tickers_24h = get_24hr_tickers()
            results = []

            with ThreadPoolExecutor(max_workers=50) as executor:
                futures = {executor.submit(scan_symbol, sym): sym for sym in SYMBOLS}
                for future in as_completed(futures):
                    result = future.result()
                    if result:
                        sym = result["sym"]
                        full_sym = sym + "USDT"
                        
                        sym_data = tickers_24h.get(full_sym)
                        if not sym_data:
                            continue

                        vol_24h = sym_data['vol']
                        day_pc = sym_data['pc']

                        # --- STRICT FILTERING RULES ---
                        
                        # Rule 1: day_pc must be between +1.00% and +6.00%
                        if not (1.0 <= day_pc <= 6.0):
                            continue

                        # Rule 2: vol_ratio must be strictly > 2.5
                        if result['vol_ratio'] <= 2.5:
                            continue

                        # Rule 3: RSI must be between 45 and 65
                        rsi = result['rsi']
                        if rsi is None or not (45.0 <= rsi <= 65.0):
                            continue

                        # --- END STRICT FILTERING ---

                        last_alerted_ts = alerted.get(sym, {}).get("ts", 0)
                        
                        if sym in prev_scan_syms:
                            alerted[sym] = {"ts": now_ts}
                            continue

                        if now_ts - last_alerted_ts < 2 * 3600:
                            continue

                        result["vol_24h"] = vol_24h
                        result["day_pc"] = day_pc
                        results.append(result)
                        alerted[sym] = {"ts": now_ts}

            print(f"[DONE] Scan completed in {time.time() - t0:.1f}s")
            prev_scan_syms = {r["sym"] for r in results}

            if results:
                results.sort(key=lambda x: x["vol_24h"], reverse=True)
                
                lines = [f"BUY SIGNAL - {time_str} (GMT+1)\n"]
                for c in results:
                    lines.append(
                        f"Symbol: {c['sym']}\n"
                        f"Price: {c['close']}\n"
                        f"15m Change: {c['pc']:+.2f}%\n"
                        f"24h Change: {c['day_pc']:+.2f}%\n"
                        f"24h Volume: {format_number(c['vol_24h'])}\n"
                        f"Vol Ratio: {c['vol_ratio']:.1f}x\n"
                        f"RSI (14): {c['rsi']:.1f}\n"
                        f"Green Candles: {c['green_count']}/3\n"
                        f"{'-' * 25}"
                    )

                send_telegram_alert("\n".join(lines))
                print("\n".join(lines))

            save_json(ALERTED_FILE, alerted)

        except KeyboardInterrupt:
            print("\n[STOP] Scanner stopped by user.")
            break
        except Exception as e:
            print(f"[ERROR] Main loop error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
