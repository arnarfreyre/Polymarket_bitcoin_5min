"""
Record 60 s of BTCUSDT order book + price data from Binance's WebSocket and render a real-time video.

RECORD = True  -> record a new 60 s segment, cache it, render the video, open it
RECORD = False -> open the cached video (re-renders from the cached data if the video is missing)

Data captured, as fast as Binance sends it:
  - order book: one REST snapshot, then every 100 ms diff update applied locally
    (Binance's "manage a local order book" procedure; 100 ms is the fastest full-depth stream)
  - price: the best bid / best ask of that local book, so also every 100 ms. The bookTicker stream
    (every change, ~1,000-2,000 messages a second) can't be kept up from here: the path from Binance
    stalls for 1-3 s at a time, bookTicker then falls ~10 s behind and Binance drops the connection
    (~17 s in, on 2026-09-28), while the 10-a-second depth stream rides the same stalls out.

The video runs at FPS frames per second in real time (20 fps = one frame every 50 ms). Each frame shows
the latest book and the latest price at that moment.

Video panels:
  top-left     BTC mid price + the book signal's prediction (arrow and colored dots)
  top-right    book signal over time (+1 bids thin -> expect down, -1 asks thin -> expect up)
  middle       cumulative book
  bottom-left  USD needed to move price $x
  bottom-right sensitivity curve ln(ask cost / bid cost) per $ move

Needs: pip install websocket-client requests numpy pandas matplotlib   (+ ffmpeg, or: pip install imageio-ffmpeg)
"""
import os
import sys
import json
import time
import pickle
import shutil
import subprocess
from datetime import datetime, timezone

import requests
import websocket          # pip install websocket-client
import numpy as np
import pandas as pd
from matplotlib.figure import Figure
from matplotlib.patches import Patch
from matplotlib.backends.backend_agg import FigureCanvasAgg

RECORD = True

SYMBOL = "BTCUSDT"
ORDER_BOOK_DEPTH = 100          # levels per side: 5, 10, 20, 50, 100, 500 or 1000
DURATION_S = 60                  # length of the recording and of the video
FPS = 20                         # video frames per second (plays in real time)
HERE = os.path.dirname(os.path.abspath(__file__))      # data and video are kept next to this script
DATA_FILE = os.path.join(HERE, "book_recording_ws.pkl")
VIDEO_FILE = os.path.join(HERE, "book_video.mp4")

S = SYMBOL.lower()
WS_URL = f"wss://fstream.binance.com/public/stream?streams={S}@depth@100ms"
REST_URL = "https://fapi.binance.com/fapi/v1/depth"

MOVEMENTS = np.linspace(0.1, 100, 101)   # $ moves for the cost / sensitivity curves
SIGNAL_MOVE = 10                         # the signal looks at the book within this many $ of the price
PREDICT_S = 1.0                          # how far ahead (seconds) the signal is checked against the price


# ---------------- from the notebook ----------------
def convert_to_strftime(t):
    dt = datetime.fromtimestamp(t / 1000, tz=timezone.utc)
    return dt.strftime('%Y-%m-%d %H:%M:%S.%f')


def get_cumulative_book(bids, asks):
    bid_df = pd.DataFrame(bids, columns=["prices", "amount"]).sort_values("prices", ascending=False)
    bid_df["cumulative_bids"] = bid_df["amount"].cumsum() / bid_df["amount"].sum()

    ask_df = pd.DataFrame(asks, columns=["prices", "amount"]).sort_values("prices", ascending=True)
    ask_df["cumulative_asks"] = ask_df["amount"].cumsum() / ask_df["amount"].sum()
    return bid_df, ask_df


def get_movement_df(bids, asks, movements=MOVEMENTS):
    bp, bq = bids.T
    ap, aq = asks.T
    df = pd.DataFrame({
        "move_amount": movements,
        "bid": [(bp * bq)[bp > bp.max() - m].sum() for m in movements],   # push price down $m
        "ask": [(ap * aq)[ap < ap.min() + m].sum() for m in movements],   # push price up $m
    }).set_index("move_amount")
    df["log_ratio"] = np.log(df["ask"] / df["bid"])
    return df


# ---------------- the signal ----------------
def book_signal(df, max_move=SIGNAL_MOVE):
    """One number in [-1, 1] summarising the book's sensitivity within $max_move of the price.

    It's the average imbalance (ask cost - bid cost) / (ask cost + bid cost) over the moves.
      +1 -> bids are much thinner than asks: the bid side is unstable, so we predict the price drops
      -1 -> asks are much thinner than bids: the ask side is unstable, so we predict the price rises
    """
    d = df[df.index <= max_move]
    return ((d["ask"] - d["bid"]) / (d["ask"] + d["bid"])).mean()


# ---------------- recording ----------------
def get_snapshot():
    d = requests.get(REST_URL, params={"symbol": SYMBOL, "limit": ORDER_BOOK_DEPTH}, timeout=5).json()
    bids = {float(p): float(q) for p, q in d["bids"]}
    asks = {float(p): float(q) for p, q in d["asks"]}
    return d["lastUpdateId"], bids, asks


def apply_levels(side, levels):
    for p, q in levels:
        p, q = float(p), float(q)
        if q == 0:
            side.pop(p, None)        # removing a level we don't have is normal
        else:
            side[p] = q              # quantities are absolute, not changes


def book_arrays(bids, asks, depth=ORDER_BOOK_DEPTH):
    # Keep the best `depth` levels per side, like the REST snapshot. Levels far from the price that
    # were outside the starting snapshot would otherwise only be partly known.
    b = np.array(sorted(bids.items(), reverse=True)[:depth])
    a = np.array(sorted(asks.items())[:depth])
    return b, a


def connect():
    # skip websocket-client's pure-Python UTF-8 check of every message (Binance sends valid JSON)
    return websocket.create_connection(WS_URL, timeout=10, skip_utf8_validation=True)


def record(duration=DURATION_S, path=DATA_FILE):
    ws = connect()
    last_id, bids, asks = get_snapshot()     # updates queue up in the socket while this downloads
    synced, prev_u = False, None
    books, ticks = [], []
    t_first = None                           # Binance time of the first synced book
    try:
        # stop on Binance's clock, not ours: data arriving late still fills the full duration
        while t_first is None or books[-1]["T"] - t_first < duration * 1000:
            try:
                ev = json.loads(ws.recv())["data"]
            except (websocket.WebSocketException, OSError) as e:
                # a network stall long enough to fill Binance's send buffer closes the connection:
                # reconnect and resync from a new snapshot (the book and the price are frozen over the gap)
                print(f"\nconnection lost ({e}), reconnecting")
                ws.close()
                ws = connect()
                last_id, bids, asks = get_snapshot()
                synced = False
                continue

            if ev.get("e") != "depthUpdate":
                continue

            if not synced:
                if ev["u"] < last_id:          # update is older than the snapshot: skip
                    continue
                if ev["U"] > last_id:          # snapshot is too old: take a new one
                    last_id, bids, asks = get_snapshot()
                    continue
                synced = True                  # first update that overlaps the snapshot
            elif ev["pu"] != prev_u:           # missed an update: start over from a new snapshot
                print("\nmissed an update, resyncing")
                last_id, bids, asks = get_snapshot()
                synced = False
                continue

            apply_levels(bids, ev["b"])
            apply_levels(asks, ev["a"])
            prev_u = ev["u"]

            b, a = book_arrays(bids, asks)
            books.append({"T": ev["T"], "bids": b, "asks": a})
            ticks.append((ev["T"], b[0, 0], a[0, 0]))      # the price: the book's best bid / ask
            if t_first is None:
                t_first = ev["T"]
            print(f"\rrecording: {len(books)} book updates, {(ev['T'] - t_first) / 1000:4.1f}s, "
                  f"{time.time() * 1000 - ev['E']:5.0f} ms behind", end="")
    finally:
        ws.close()
    print()

    data = {"books": books, "ticks": ticks}
    with open(path, "wb") as f:
        pickle.dump(data, f)
    return data


# ---------------- video ----------------
def render(data):
    books, ticks = data["books"], np.array(data["ticks"])

    # frame times: every 1/FPS s from the first book update to the last
    book_T = np.array([b["T"] for b in books])
    t0 = book_T[0]
    n_frames = int((book_T[-1] - t0) / 1000 * FPS) + 1
    t = np.arange(n_frames) / FPS                                         # seconds since start
    book_idx = np.searchsorted(book_T, t0 + t * 1000, side="right") - 1   # latest book at each frame

    tick_t = (ticks[:, 0] - t0) / 1000
    tick_mid = (ticks[:, 1] + ticks[:, 2]) / 2

    def price_at(ts):              # latest mid price at time(s) ts
        return tick_mid[np.clip(np.searchsorted(tick_t, ts, side="right") - 1, 0, None)]

    mid = price_at(t)

    print(f"computing book stats for {len(books)} book updates ...")
    moves = [get_movement_df(b["bids"], b["asks"]) for b in books]
    signal = np.array([book_signal(df) for df in moves])[book_idx]

    # How did the signal do? Compare it with the price change PREDICT_S seconds later.
    ok = t + PREDICT_S <= t[-1]
    change = price_at(t[ok] + PREDICT_S) - mid[ok]
    moved = change != 0
    hit_rate = np.mean(np.sign(-signal[ok][moved]) == np.sign(change[moved])) if moved.any() else np.nan
    print(f"corr(signal, price change {PREDICT_S:g}s later) = {pd.Series(signal[ok]).corr(pd.Series(change)):+.2f}"
          "   (negative = signal points the right way)")
    print(f"direction right {hit_rate:.0%} of the time the price moved ({moved.sum()} of {ok.sum()} frames)")

    # fixed axis limits so frames are comparable
    x_min = min(b["bids"][:, 0].min() for b in books)
    x_max = max(b["asks"][:, 0].max() for b in books)
    all_usd = np.concatenate([df[["bid", "ask"]].values.ravel() for df in moves])
    usd_lim = (all_usd[all_usd > 0].min(), all_usd.max() * 1.1)
    all_r = np.concatenate([df["log_ratio"].values for df in moves])
    r_max = np.nanmax(np.abs(all_r[np.isfinite(all_r)])) * 1.1
    vis = (tick_t >= 0) & (tick_t <= t[-1])
    lo, hi = tick_mid[vis].min(), tick_mid[vis].max()
    arrow_dy = max(hi - lo, 1.0) * 0.4      # arrow height in $ for signal = +-1
    arrow_dx = t[-1] * 0.06                 # arrow width in seconds (just for visibility)
    dot_every = max(1, FPS // 2)            # colored prediction dot every 0.5 s
    up, down = "tab:green", "tab:red"
    A = dict(animated=True)                 # artists that change every frame

    # ---- figure: static parts are drawn once, moving parts on top every frame ----
    fig = Figure(figsize=(16, 12), dpi=80, layout="constrained")
    canvas = FigureCanvasAgg(fig)
    ax = fig.subplot_mosaic([["price", "signal"], ["book", "book"], ["usd", "sens"]])
    title = fig.suptitle("", **A)

    p = ax["price"]
    p.plot(tick_t[vis], tick_mid[vis], color="lightgrey", lw=1)
    price_line, = p.plot([], [], color="black", lw=1, **A)
    dots = p.scatter([], [], c=[], cmap="RdYlGn", vmin=-1, vmax=1, s=14, zorder=3, **A)
    sig_text = p.text(0.02, 0.95, "", transform=p.transAxes, va="top", fontsize=12, fontweight="bold", **A)
    p.set_xlim(0, t[-1] + arrow_dx)
    p.set_ylim(lo - arrow_dy, hi + arrow_dy)
    p.ticklabel_format(axis="y", useOffset=False, style="plain")
    p.set_title(f"BTC mid price   (dots: prediction at the time, arrow: prediction for the next {PREDICT_S:g}s)")
    p.set_xlabel("Seconds")
    p.grid(alpha=0.3)

    g = ax["signal"]
    sig_line, = g.plot([], [], color="black", lw=1, **A)
    g.axhline(0, color="grey", lw=1)
    g.set_xlim(0, t[-1])
    g.set_ylim(-1, 1)
    g.set_title(f"Book signal (imbalance within ${SIGNAL_MOVE:g} of the price)")
    g.set_xlabel("Seconds")
    g.legend(handles=[Patch(color=down, alpha=0.3, label="+: bids thin → expect down"),
                      Patch(color=up, alpha=0.3, label="-: asks thin → expect up")], loc="lower left")
    g.grid(alpha=0.3)

    bk = ax["book"]
    mid_line = bk.axvline(mid[0], color="black", lw=1, **A)
    bk.set_xlim(x_min, x_max)
    bk.set_ylim(0, 1)
    bk.set_title("Cumulative book")
    bk.set_ylabel("% of orders")
    bk.legend(handles=[Patch(color="blue", label="bid"), Patch(color="red", label="ask")], loc="upper center")

    u = ax["usd"]
    usd_bid, = u.plot([], [], drawstyle="steps-post", color="blue", label="bid (push price down)", **A)
    usd_ask, = u.plot([], [], drawstyle="steps-post", color="red", label="ask (push price up)", **A)
    u.axvline(SIGNAL_MOVE, color="grey", ls="--", lw=1)
    u.set_yscale("log")
    u.set_xlim(0, MOVEMENTS[-1])
    u.set_ylim(*usd_lim)
    u.set_title("USD needed to move price   (dashed: signal range)")
    u.set_xlabel("Price move ($)")
    u.set_ylabel("USD (log)")
    u.legend(loc="lower right")
    u.grid(alpha=0.3)

    sn = ax["sens"]
    sens_line, = sn.plot([], [], drawstyle="steps-post", color="black", **A)
    sn.axhline(0, color="grey", lw=1)
    sn.axvline(SIGNAL_MOVE, color="grey", ls="--", lw=1)
    sn.set_xlim(0, MOVEMENTS[-1])
    sn.set_ylim(-r_max, r_max)
    sn.set_title("Book sensitivity: ln(ask cost / bid cost)")
    sn.set_xlabel("Price move ($)")
    sn.legend(handles=[Patch(color="red", alpha=0.3, label="ask deeper → buys move price less"),
                       Patch(color="blue", alpha=0.3, label="bid deeper → sells move price less")],
              loc="lower right")
    sn.grid(alpha=0.3)

    fixed = [title, price_line, dots, sig_text, sig_line, mid_line, usd_bid, usd_ask, sens_line]
    temp = []          # moving artists rebuilt every frame (fills, arrow)
    book_temp = []     # moving artists rebuilt when a new book update arrives
    last_book = [-1]

    def update(i):
        for a in temp:
            a.remove()
        temp.clear()
        sig = signal[i]

        # price + prediction
        past = vis & (tick_t <= t[i])
        price_line.set_data(tick_t[past], tick_mid[past])
        d = np.arange(0, i + 1, dot_every)
        dots.set_offsets(np.column_stack([t[d], mid[d]]))
        dots.set_array(-signal[d])
        if np.isfinite(sig):
            color = down if sig > 0 else up
            temp.append(p.annotate("", xy=(t[i] + arrow_dx, mid[i] - sig * arrow_dy), xytext=(t[i], mid[i]),
                                   arrowprops=dict(arrowstyle="-|>", color=color, lw=3, mutation_scale=25), **A))
            sig_text.set_text(f"signal {sig:+.2f} → predict {'down' if sig > 0 else 'up'}")
            sig_text.set_color(color)

        # signal over time
        s = signal[:i + 1]
        sig_line.set_data(t[:i + 1], s)
        temp.append(g.fill_between(t[:i + 1], s, 0, where=s > 0, color=down, alpha=0.3, **A))
        temp.append(g.fill_between(t[:i + 1], s, 0, where=s < 0, color=up, alpha=0.3, **A))

        mid_line.set_xdata([mid[i], mid[i]])
        title.set_text(f"Symbol: {SYMBOL}   Depth: {ORDER_BOOK_DEPTH}   "
                       f"Timestamp: {convert_to_strftime(t0 + t[i] * 1000)}   Mid: {mid[i]:,.1f}")

        # book panels, only when there's a new book update
        j = book_idx[i]
        if j == last_book[0]:
            return
        last_book[0] = j
        for a in book_temp:
            a.remove()
        book_temp.clear()

        bid_df, ask_df = get_cumulative_book(books[j]["bids"], books[j]["asks"])
        bid_df = bid_df.sort_values("prices")
        book_temp.append(bk.fill_between(bid_df["prices"], bid_df["cumulative_bids"], step="pre", color="blue", **A))
        book_temp.append(bk.fill_between(ask_df["prices"], ask_df["cumulative_asks"], step="post", color="red", **A))

        df = moves[j]
        usd_bid.set_data(df.index, df["bid"])
        usd_ask.set_data(df.index, df["ask"])
        r = df["log_ratio"]
        sens_line.set_data(df.index, r)
        book_temp.append(sn.fill_between(df.index, r, 0, where=r > 0, step="post", color="red", alpha=0.3, **A))
        book_temp.append(sn.fill_between(df.index, r, 0, where=r < 0, step="post", color="blue", alpha=0.3, **A))

    # lay out and draw the static background once
    update(0)
    canvas.draw()
    fig.set_layout_engine("none")
    background = canvas.copy_from_bbox(fig.bbox)
    w, h = canvas.get_width_height()

    ffmpeg = find_ffmpeg()
    path = VIDEO_FILE
    proc = subprocess.Popen([ffmpeg, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgba",
                             "-s", f"{w}x{h}", "-r", str(FPS), "-i", "-",
                             "-vcodec", "libx264", "-pix_fmt", "yuv420p", path], stdin=subprocess.PIPE)
    for i in range(n_frames):
        update(i)
        canvas.restore_region(background)
        for a in book_temp + temp + fixed:
            fig.draw_artist(a)
        proc.stdin.write(canvas.buffer_rgba())
        if i % FPS == 0 or i == n_frames - 1:
            print(f"\rrendering {path}: frame {i + 1}/{n_frames}", end="")
    proc.stdin.close()
    proc.wait()
    print()
    return path


def find_ffmpeg():
    path = shutil.which("ffmpeg")
    if path:
        return path
    try:
        import imageio_ffmpeg          # pip install imageio-ffmpeg bundles an ffmpeg binary
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        sys.exit("ffmpeg not found: install it, or run  pip install imageio-ffmpeg")


# ---------------- show ----------------
def find_video():
    return VIDEO_FILE if os.path.exists(VIDEO_FILE) else None


def show_video(path):
    print(f"opening {path}")
    if sys.platform.startswith("win"):
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.run(["open", path])
    else:
        subprocess.run(["xdg-open", path])


if __name__ == "__main__":
    if RECORD:
        path = render(record())
    else:
        path = find_video()
        if path is None:
            if not os.path.exists(DATA_FILE):
                sys.exit("No cached recording yet: set RECORD = True first.")
            with open(DATA_FILE, "rb") as f:
                path = render(pickle.load(f))
    show_video(path)