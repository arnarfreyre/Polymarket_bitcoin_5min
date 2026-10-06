"""
How often is the arrow in `feature 3.1.1 visualize.py` right, and how far ahead does it see?

RECORD = True  -> record DURATION_S (5 min) of the BTCUSDT order book with the visualize script's recorder,
                  cache it in DATA_FILE, score the arrow and plot to PLOT_FILE (both next to this script)
RECORD = False -> score and plot the cached DATA_FILE again (any recording of the visualize script works,
                  e.g. its 1-minute book_recording_ws.pkl)

The arrow: at every book update (~10 a second) the book signal (visualize.book_signal, the same function the
video uses) predicts the mid price's direction: up when the signal is < 0 (asks thin), down when > 0 (bids
thin). For each horizon h it is scored against the mid h later:
  accuracy   share of arrows that were right, among the updates where the mid moved within h
  moved      share of updates where the mid moved at all within h (at short horizons it mostly doesn't)
  travel     mean $ the mid moved in the arrow's direction, over all updates (0 when it didn't move),
             next to the book's mean bid-ask spread (about what it costs to cross it)

Uncertainty: consecutive updates are far from independent (the signal keeps its sign for seconds and the
h-long windows overlap), so the 95 % intervals are a circular block bootstrap with blocks of h + 5 s. A binomial
interval on the raw counts would be many times too narrow. Five minutes holds ~60 such blocks at the shortest
horizons but only ~4 at 60 s, so expect wide bands there; a horizon with fewer than MIN_BLOCKS blocks of scored
updates is left out (a 1-minute recording stops at 10 s).
Chance level: the same signal shifted in time by at least h + 10 s (circularly) and scored against the same
prices. That keeps the signal's persistence and up / down balance and the price's drift, so a signal that
happens to point up during a rally doesn't look skilful. The grey bands are the middle 95 % of those shifts.
Momentum baseline: "the mid keeps going the way it last moved". The thin side of the book is often the side
the price just moved toward, so the arrow could be momentum in disguise. The test of what the book adds is
the arrow's accuracy on the updates where it points against the last move.

The price is the book's mid (its top matched Binance's REST bookTicker 31 of 31 times on 2026-09-28). The book
updates every 100-105 ms, so 100 ms is the shortest horizon and means the next update (the lookup allows
SLACK_MS for that jitter). The book also reaches us ~10-60 ms after Binance's timestamp, so the start of each
horizon is gone before you could act on it.

Needs what the visualize script needs.
"""
import os
import sys
import pickle
import importlib.util
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("visualize", os.path.join(HERE, "feature 3.1.1 visualize.py"))
viz = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(viz)              # the recorder and the signal: the same arrow as the video

RECORD = True

DURATION_S = 300                           # 5 minutes
DATA_FILE = os.path.join(HERE, "book_recording_5min.pkl")
PLOT_FILE = os.path.join(HERE, "signal_accuracy.png")

HORIZONS_MS = [100, 200, 300, 500, 1000, 2000, 3000, 5000, 10_000, 20_000, 30_000, 60_000]
STRENGTH_BINS = [0, 0.25, 0.5, 0.75, 1.0]  # |signal| buckets
WINDOW_S = 30                              # accuracy per window of the recording ...
WINDOW_HORIZONS_MS = [500, 2000, 10_000]   # ... at these horizons
MIN_MOVED = 20                             # fewer moved updates than this in a bucket / window: not plotted
MIN_BLOCKS = 3                             # a horizon needs this many independent blocks of scored updates
N_BOOT = 1000
SLACK_MS = 10       # book updates are 100-105 ms apart: "h later" is the book standing at h + 10 ms
GAP_MS = 1000       # a longer pause between book updates is a reconnect: windows across it are dropped
EPS = 1e-9          # mids are multiples of $0.05: anything smaller is float noise

BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
STRENGTH_COLORS = ["#86b6ef", "#3987e5", "#1c5cab", "#0d366b"]    # one hue, light -> dark = weak -> strong
GREY, INK = "#9a9994", "#52514e"


# ---------------- data ----------------
def load_book(data):
    books = data["books"]
    T = np.array([b["T"] for b in books], dtype=float)
    bid = np.array([b["bids"][0, 0] for b in books])
    ask = np.array([b["asks"][0, 0] for b in books])
    print(f"computing the signal for {len(books)} book updates ...")
    signal = np.array([viz.book_signal(viz.get_movement_df(b["bids"], b["asks"])) for b in books])
    return T, (bid + ask) / 2, ask - bid, signal


def outcome(T, mid, arrow, h):
    """For every update: whether it can be scored at horizon h, the mid's change over h, whether it moved and
    whether the arrow got the direction right."""
    j = np.searchsorted(T, T + h + SLACK_MS, side="right") - 1   # the book standing h later
    gaps = np.r_[0, np.cumsum(np.diff(T) > GAP_MS)]              # reconnect gaps before each update
    ok = (j + 1 < len(T)) & (arrow != 0)                         # the recording goes on past it ...
    ok &= gaps[np.minimum(j + 1, len(T) - 1)] == gaps            # ... with no gap in between
    change = np.where(ok, mid[j] - mid, 0.0)
    moved = ok & (np.abs(change) > EPS)
    hit = moved & (np.sign(change) == arrow)
    return ok, change, moved, hit


# ---------------- statistics ----------------
def block_ci(num, den, block, rng):
    """95 % circular block bootstrap interval of sum(num) / sum(den); num and den per scored update, in time
    order. Circular (blocks wrap around the end) so the first and last updates are drawn as often as the rest."""
    n = len(num)
    block = max(1, min(block, n))
    cn = np.r_[0, np.cumsum(np.r_[num, num[:block - 1]])]
    cd = np.r_[0, np.cumsum(np.r_[den, den[:block - 1]])]
    starts = rng.integers(0, n, size=(N_BOOT, -(-n // block)))
    with np.errstate(invalid="ignore", divide="ignore"):
        stat = (cn[starts + block] - cn[starts]).sum(1) / (cd[starts + block] - cd[starts]).sum(1)
    return np.nanpercentile(stat, [2.5, 97.5]) if np.isfinite(stat).any() else (np.nan, np.nan)


def chance_band(arrow, ok, change, min_shift, step):
    """Middle 95 % of the accuracy and the travel of the arrow shifted in time by >= min_shift updates."""
    shifts = np.arange(min_shift, len(arrow) - min_shift + 1, step)
    if len(shifts) < 20:                                   # the recording is too short for this horizon
        return (np.nan, np.nan), (np.nan, np.nan)
    acc, travel = [], []
    moved = ok & (np.abs(change) > EPS)
    for s in shifts:
        a = np.roll(arrow, s)
        m = moved & (a != 0)
        acc.append(np.mean(np.sign(change[m]) == a[m]))
        travel.append(np.mean((a * change)[ok & (a != 0)]))
    return np.percentile(acc, [2.5, 97.5]), np.percentile(travel, [2.5, 97.5])


def score(T, mid, signal, rng):
    arrow = -np.sign(signal)                               # +1 up, -1 down, as the video draws it
    rate = (len(T) - 1) / ((T[-1] - T[0]) / 1000)          # book updates a second
    step = np.r_[0, np.diff(mid)]
    last = pd.Series(np.where(np.abs(step) > EPS, np.sign(step), np.nan)).ffill().fillna(0).to_numpy()
    bucket = np.digitize(np.abs(signal), STRENGTH_BINS[1:-1])
    rows, strength, skipped = [], [], []
    for h in HORIZONS_MS:
        ok, change, moved, hit = outcome(T, mid, arrow, h)
        block = int(np.ceil((h / 1000 + 5) * rate))
        if ok.sum() < MIN_BLOCKS * block or moved.sum() == 0:
            skipped.append(h)
            continue
        travel = arrow * change                            # 0 where not scored
        with_last = moved & (last != 0)                    # the mid had moved before: momentum has a call
        against = with_last & (last != arrow)              # the arrow points against the last move
        enough = against.sum() >= MIN_MOVED
        (c_lo, c_hi), (ct_lo, ct_hi) = chance_band(arrow, ok, change, int(np.ceil((h / 1000 + 10) * rate)),
                                                   max(1, round(rate)))
        rows.append({
            "horizon_ms": h, "updates": ok.sum(), "moved": moved.sum() / ok.sum(),
            "accuracy": hit.sum() / moved.sum(),
            **dict(zip(["acc_lo", "acc_hi"], block_ci(hit[ok], moved[ok], block, rng))),
            "chance_lo": c_lo, "chance_hi": c_hi,
            "travel": travel[ok].mean(),
            **dict(zip(["travel_lo", "travel_hi"], block_ci(travel[ok], ok[ok], block, rng))),
            "chance_travel_lo": ct_lo, "chance_travel_hi": ct_hi,
            "abs_move": np.abs(change[ok]).mean(),
            "last_move": np.mean(np.sign(change[with_last]) == last[with_last]),
            "against_n": against.sum(),
            "against_acc": hit[against].sum() / against.sum() if enough else np.nan,
            **dict(zip(["against_lo", "against_hi"],
                       block_ci((hit & against)[ok], against[ok], block, rng) if enough else (np.nan, np.nan))),
        })
        for b in range(len(STRENGTH_BINS) - 1):
            m, hb = moved & (bucket == b), hit & (bucket == b)
            enough = m.sum() >= MIN_MOVED
            lo, hi = block_ci(hb[ok], m[ok], block, rng) if enough else (np.nan, np.nan)
            strength.append({"horizon_ms": h, "bucket": b, "moved": m.sum(),
                             "accuracy": hb.sum() / m.sum() if enough else np.nan, "lo": lo, "hi": hi})
    if skipped:
        print(f"left out (fewer than {MIN_BLOCKS} independent blocks in the recording): "
              + ", ".join(horizon_label(h) for h in skipped))
    return pd.DataFrame(rows), pd.DataFrame(strength)


def by_window(T, mid, signal):
    """Accuracy in each WINDOW_S-long stretch of the recording (by the update's time), per horizon."""
    arrow = -np.sign(signal)
    t = (T - T[0]) / 1000
    edges = np.r_[np.arange(0, t[-1], WINDOW_S), t[-1]]    # the last window ends with the recording
    w = np.minimum(np.digitize(t, edges) - 1, len(edges) - 2)
    out = {}
    for h in WINDOW_HORIZONS_MS:
        ok, change, moved, hit = outcome(T, mid, arrow, h)
        m = np.bincount(w[moved], minlength=len(edges) - 1)
        c = np.bincount(w[hit], minlength=len(edges) - 1)
        with np.errstate(invalid="ignore", divide="ignore"):
            out[h] = np.where(m >= MIN_MOVED, c / m, np.nan)
    return edges, out


# ---------------- output ----------------
def horizon_label(ms):
    return f"{ms:g} ms" if ms < 1000 else f"{ms / 1000:g} s"


def print_table(res):
    f = lambda v: f"{v:.0%}" if np.isfinite(v) else "-"
    d = lambda v: f"{v:+.3f}" if np.isfinite(v) else "-"
    table = pd.DataFrame({
        "horizon": res["horizon_ms"].map(horizon_label),
        "updates": res["updates"],
        "moved": res["moved"].map(f),
        "accuracy": res["accuracy"].map(f),
        "95 %": [f"[{f(a)}, {f(b)}]" for a, b in zip(res["acc_lo"], res["acc_hi"])],
        "chance": [f"[{f(a)}, {f(b)}]" for a, b in zip(res["chance_lo"], res["chance_hi"])],
        "last move": res["last_move"].map(f),
        "against it [95 %] (n)": [f"{f(v)} [{f(a)}, {f(b)}] ({n})" for v, a, b, n in
                                  zip(res["against_acc"], res["against_lo"], res["against_hi"], res["against_n"])],
        "travel $": res["travel"].map(d),
        "95 % ": [f"[{d(a)}, {d(b)}]" for a, b in zip(res["travel_lo"], res["travel_hi"])],
        "chance ": [f"[{d(a)}, {d(b)}]" for a, b in zip(res["chance_travel_lo"], res["chance_travel_hi"])],
        "mean |move| $": res["abs_move"].map(lambda v: f"{v:.3f}"),
    })
    print(table.to_string(index=False))


def style(a, title, horizons=None):
    a.set_title(title, loc="left", fontsize=11)
    a.grid(alpha=0.25)
    a.spines[["top", "right"]].set_visible(False)
    a.tick_params(colors=INK)
    if horizons is not None:                               # log x axis over the scored horizons
        a.set_xscale("log")
        a.set_xticks(horizons / 1000, [horizon_label(h) for h in horizons], fontsize=8, rotation=45)
        a.minorticks_off()
        a.set_xlim(horizons.min() / 1000 / 1.25, horizons.max() / 1000 * 1.25)
        a.set_xlabel("Horizon")


def plot(res, strength, edges, windows, spread, title, path):
    fig = Figure(figsize=(14, 15), dpi=90, layout="constrained")
    FigureCanvasAgg(fig)
    ax = fig.subplot_mosaic([["acc", "acc"], ["strength", "travel"], ["moved", "time"]])
    fig.suptitle(title, fontsize=13)
    hs = res["horizon_ms"].to_numpy()
    x = hs / 1000

    a = ax["acc"]
    a.fill_between(x, res["chance_lo"], res["chance_hi"], color=GREY, alpha=0.3, lw=0,
                   label="chance: the same signal shifted in time (middle 95 %)")
    a.fill_between(x, res["acc_lo"], res["acc_hi"], color=BLUE, alpha=0.2, lw=0, label="95 % interval (block bootstrap)")
    a.plot(x, res["accuracy"], color=BLUE, lw=2, marker="o", ms=6, label="arrow right (of the updates where the mid moved)")
    a.plot(x, res["last_move"], color=ORANGE, lw=1.5, ls="--", marker="s", ms=5,
           label="momentum baseline: the direction of the last mid move")
    a.fill_between(x, res["against_lo"], res["against_hi"], color=AQUA, alpha=0.15, lw=0)
    a.plot(x, res["against_acc"], color=AQUA, lw=2, marker="^", ms=6,
           label="arrow right when it points against the last move (what the book adds; band: 95 %)")
    a.axhline(0.5, color=INK, lw=1, ls="--")
    for xi, yi in zip(x, res["accuracy"]):
        a.annotate(f"{yi:.0%}", (xi, yi), xytext=(0, 8), textcoords="offset points", ha="center", fontsize=8, color=INK)
    a.set_ylim(0, 1.06)                    # room for the labels above 100 %
    a.yaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    a.set_ylabel("Direction right")
    a.legend(loc="lower left", frameon=False)
    style(a, "How often the arrow points the way the mid then moves", hs)

    a = ax["strength"]
    for b, color in enumerate(STRENGTH_COLORS):
        s = strength[strength["bucket"] == b]
        xs = s["horizon_ms"] / 1000 * 10 ** ((b - 1.5) * 0.025)          # nudge the buckets apart
        a.vlines(xs, s["lo"], s["hi"], color=color, lw=1.5, alpha=0.7)
        a.plot(xs, s["accuracy"], color=color, lw=2, marker="o", ms=5,
               label=f"|signal| {STRENGTH_BINS[b]:.2f}-{STRENGTH_BINS[b + 1]:.2f}")
    a.axhline(0.5, color=INK, lw=1, ls="--")
    a.set_ylim(0, 1)
    a.yaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    a.set_ylabel("Direction right")
    a.legend(loc="lower left", frameon=False, title="signal strength", fontsize=9)
    style(a, "Stronger signal, better arrow?  (bars: 95 %)", hs)

    a = ax["travel"]
    a.fill_between(x, res["chance_travel_lo"], res["chance_travel_hi"], color=GREY, alpha=0.3, lw=0, label="chance (middle 95 %)")
    a.fill_between(x, res["travel_lo"], res["travel_hi"], color=BLUE, alpha=0.2, lw=0, label="95 % interval")
    a.plot(x, res["travel"], color=BLUE, lw=2, marker="o", ms=5, label="mean \\$ the mid moved the arrow's way")
    a.axhline(0, color=INK, lw=1)
    a.axhline(spread, color=ORANGE, lw=1.5, ls="--", label=f"mean bid-ask spread \\${spread:.2f}")
    a.set_yscale("symlog", linthresh=0.1)
    ticks = [-100, -10, -1, -0.1, 0, 0.1, 1, 10, 100]
    a.set_yticks(ticks, [f"{v:+g}" if v else "0" for v in ticks])
    a.set_ylim(*np.clip(a.get_ylim(), -100, 100))
    a.set_ylabel("\\$ per update (log scale beyond ±\\$0.1)")
    a.legend(loc="upper left", frameon=False, fontsize=9)
    style(a, "How far the mid travels the arrow's way", hs)

    a = ax["moved"]
    a.plot(x, res["moved"], color=BLUE, lw=2, marker="o", ms=5)
    a.set_ylim(0, 1.05)
    a.yaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    a.set_ylabel("Share of updates")
    style(a, "Share of updates where the mid moved at all (the ones accuracy counts)", hs)

    a = ax["time"]
    mids = (edges[:-1] + edges[1:]) / 2
    for h, color in zip(WINDOW_HORIZONS_MS, [BLUE, ORANGE, AQUA]):
        a.plot(mids, windows[h], color=color, lw=2, marker="o", ms=6, label=f"{horizon_label(h)} ahead")
    a.axhline(0.5, color=INK, lw=1, ls="--")
    a.set_ylim(0, 1)
    a.set_xlim(0, edges[-1])
    a.yaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    a.set_xlabel("Seconds into the recording")
    a.set_ylabel("Direction right")
    a.legend(loc="lower left", frameon=False)
    style(a, f"Accuracy in each {WINDOW_S} s of the recording")

    fig.savefig(path)
    return path


if __name__ == "__main__":
    if RECORD:
        data = viz.record(DURATION_S, DATA_FILE)
    else:
        if not os.path.exists(DATA_FILE):
            sys.exit(f"No recording {DATA_FILE} yet: set RECORD = True first.")
        with open(DATA_FILE, "rb") as f:
            data = pickle.load(f)

    T, mid, spread, signal = load_book(data)
    res, strength = score(T, mid, signal, np.random.default_rng(0))
    edges, windows = by_window(T, mid, signal)
    print_table(res)

    start = datetime.fromtimestamp(T[0] / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    title = (f"{viz.SYMBOL} book signal (imbalance within \\${viz.SIGNAL_MOVE:g} of the price): "
             f"{(T[-1] - T[0]) / 60_000:.1f} min from {start}, {len(T)} book updates")
    viz.show_video(plot(res, strength, edges, windows, spread.mean(), title, PLOT_FILE))
