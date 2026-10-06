"""
The arrow of `feature 3.1.1 visualize.py` scored in finer signal buckets, on long recordings (30 min .. a week).

RECORD = True  -> record RECORD_MIN (30) minutes of the BTCUSDT perp book into CHUNK_DIR, one file per CHUNK_MIN
                  minutes (a crash or a dead network costs one file, not the whole run), then score every file in
                  CHUNK_DIR and plot to PLOT_FILE. Each run adds its files, so repeated runs build up to a week.
                  Ctrl-C ends the recording early (the file being written is lost) and scores the ones saved.
RECORD = False -> score and plot every file in CHUNK_DIR again

Why record: there is no free history of this book deep enough for the signal. It needs the ~70 levels within $10
of the price every 100 ms; Binance's archive (data.binance.vision bookDepth) has one row per 30 s in bands of
+-0.2 % (~$170). Each file has the visualize script's format ({"books", "ticks"}), so `feature 3.1.1 accuracy.py`
can score any one of them too. Storage: ~2 MB a minute (~2.8 GB a day).

To run it in the background, from the project root (caffeinate keeps the Mac awake; the plot opens at the end):
  nohup caffeinate -is .venv/bin/python -u "notebooks/model bitcoin/Fragmentation, Price Formation, and Cross-Impact in Bitcoin Markets/3.1.1 video/feature 3.1.1 accuracy buckets.py" > book_record.log 2>&1 &

The buckets, at each horizon h of HORIZONS_MS (scored as in `feature 3.1.1 accuracy.py`, whose functions this uses):
  |signal| in steps of 0.1   share of arrows that were right, among the updates where the mid moved within h
  signal in steps of 0.1     mean $ the mid moved over h (0 when it didn't move): a falling line means both the
                             sign and the strength of the signal carry information
The 95 % intervals resample whole blocks of h + 5 s (every bucket of a block together), since consecutive updates
are far from independent. Chance: the same signal shifted in time by >= h + 10 s (N_SHIFTS circular shifts),
bucketed and scored against the same prices. A * in the printed tables marks a bucket outside its chance band.
"""
import os
import sys
import time
import pickle
import warnings
import importlib.util
from glob import glob
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("accuracy", os.path.join(HERE, "feature 3.1.1 accuracy.py"))
acc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(acc)              # the 5-minute scoring: outcome(), horizon labels, colours
viz = acc.viz                              # the recorder and the signal: the same arrow as the video

RECORD = True

RECORD_MIN = 30                            # length of a recording
CHUNK_MIN = 5                              # minutes per file
MIN_CHUNK_S = 30                           # no file shorter than this at the end of a recording
CHUNK_DIR = os.path.join(HERE, "book_chunks")
PLOT_FILE = os.path.join(HERE, "signal_accuracy_buckets.png")

HORIZONS_MS = [100, 500, 1000, 5000, 10_000, 30_000]      # one panel each
STRENGTH_BINS = np.linspace(0, 1, 11)                     # |signal| buckets for the accuracy
SIGNED_BINS = np.linspace(-1, 1, 21)                      # signal buckets for the mean move
MOVES = viz.MOVEMENTS[viz.MOVEMENTS <= viz.SIGNAL_MOVE]   # the $ moves viz.book_signal averages over
N_BOOT = 1000
N_SHIFTS = 200                                            # time shifts for the chance level


# ---------------- recording ----------------
def log(msg):
    print(f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%SZ}  {msg}", flush=True)


def record(minutes):
    os.makedirs(CHUNK_DIR, exist_ok=True)
    end = time.time() + minutes * 60
    log(f"recording {minutes:g} min into {CHUNK_DIR}")
    try:
        while (left := end - time.time()) > MIN_CHUNK_S:
            path = os.path.join(CHUNK_DIR, datetime.now(timezone.utc).strftime("book_%Y%m%d_%H%M%S.pkl"))
            try:
                data = viz.record(min(CHUNK_MIN * 60, left), path)
                log(f"saved {os.path.basename(path)}: {len(data['books'])} book updates")
            except Exception as e:         # network down, Binance refusing, ...: start a new file
                print()
                log(f"file lost ({e!r}), retrying in 10 s")
                time.sleep(10)
    except KeyboardInterrupt:
        print()
        log("stopped early: scoring the files saved so far")


# ---------------- data ----------------
def side(books, key, pad):
    """Prices and $ notional of one side of each book, best level first, padded to the deepest book with
    price `pad` and $0."""
    n = max(len(b[key]) for b in books)
    px, usd = np.full((len(books), n), pad), np.zeros((len(books), n))
    for i, b in enumerate(books):
        lv = b[key]
        px[i, :len(lv)], usd[i, :len(lv)] = lv[:, 0], lv[:, 0] * lv[:, 1]
    return px, usd


def book_stats(books):
    """Time, mid, spread and viz.book_signal of each book, vectorised (book_signal one book at a time takes ~1 ms,
    14 min for a day). The comparisons are viz.get_movement_df's, so the signal is the same."""
    bp, bu = side(books, "bids", -np.inf)
    ap, au = side(books, "asks", np.inf)
    bid = (bu[:, :, None] * (bp[:, :, None] > bp[:, :1, None] - MOVES)).sum(1)   # $ to push the price down each move
    ask = (au[:, :, None] * (ap[:, :, None] < ap[:, :1, None] + MOVES)).sum(1)   # ... and up
    T = np.array([b["T"] for b in books], dtype=float)
    return T, (bp[:, 0] + ap[:, 0]) / 2, ap[:, 0] - bp[:, 0], ((ask - bid) / (ask + bid)).mean(1)


def load(paths):
    parts = []
    for i, p in enumerate(paths):
        with open(p, "rb") as f:
            books = pickle.load(f)["books"]
        if books:
            parts.append(book_stats(books))
        print(f"\rcomputing the signal: {i + 1}/{len(paths)} files", end="")
    print()
    T, mid, spread, signal = (np.concatenate(x) for x in zip(*parts))
    o = np.argsort(T, kind="stable")
    return T[o], mid[o], spread[o], signal[o]


# ---------------- statistics ----------------
def bucket_of(x, bins):
    return np.digitize(x, bins[1:-1])                     # 0 .. len(bins) - 2, the top edge in the last bucket


def ratio_by_bucket(blk, bucket, num, den, k, rng):
    """sum(num) / sum(den) in each of k buckets, its 95 % interval from resampling whole blocks with replacement
    (every bucket of a block together), and sum(den). One entry per scored update."""
    _, b = np.unique(blk, return_inverse=True)            # the blocks with scored updates, as 0 .. nb - 1
    nb = b.max() + 1
    N = np.bincount(b * k + bucket, weights=num, minlength=nb * k).reshape(nb, k)
    D = np.bincount(b * k + bucket, weights=den, minlength=nb * k).reshape(nb, k)
    boot = np.empty((N_BOOT, k))
    with np.errstate(invalid="ignore", divide="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)   # buckets empty in a draw, or in all of them
        for r in range(N_BOOT):
            w = np.bincount(rng.integers(0, nb, nb), minlength=nb)       # how often each block is drawn
            boot[r] = (w @ N) / (w @ D)
        lo, hi = np.nanpercentile(boot, [2.5, 97.5], axis=0)
        return N.sum(0) / D.sum(0), lo, hi, D.sum(0)


def chance(signal, ok, change, h, rate):
    """Middle 95 %, over N_SHIFTS circular shifts of the signal by >= h + 10 s, of the accuracy per |signal| bucket
    and of the mean move per signal bucket."""
    k1, k2 = len(STRENGTH_BINS) - 1, len(SIGNED_BINS) - 1
    m = int(np.ceil((h / 1000 + 10) * rate))
    if len(signal) - 2 * m < 20:                          # the recording is too short for this horizon
        return np.full((2, k1), np.nan), np.full((2, k2), np.nan)
    moved = ok & (np.abs(change) > acc.EPS)
    up = np.sign(change[moved])
    accs, moves = [], []
    with np.errstate(invalid="ignore", divide="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        for s in np.unique(np.linspace(m, len(signal) - m, N_SHIFTS).astype(int)):
            a = np.roll(signal, s)
            sb = bucket_of(np.abs(a[moved]), STRENGTH_BINS)
            right = (up == -np.sign(a[moved])).astype(float)
            accs.append(np.bincount(sb, weights=right, minlength=k1) / np.bincount(sb, minlength=k1))
            db = bucket_of(a[ok], SIGNED_BINS)
            moves.append(np.bincount(db, weights=change[ok], minlength=k2) / np.bincount(db, minlength=k2))
        return np.nanpercentile(accs, [2.5, 97.5], axis=0), np.nanpercentile(moves, [2.5, 97.5], axis=0)


def score(T, mid, signal, rng):
    rate = 1000 / np.median(np.diff(T))                   # book updates a second (runs may be hours apart)
    arrow = -np.sign(signal)                              # +1 up, -1 down, as the video draws it
    sb, db = bucket_of(np.abs(signal), STRENGTH_BINS), bucket_of(signal, SIGNED_BINS)
    k1, k2 = len(STRENGTH_BINS) - 1, len(SIGNED_BINS) - 1
    overall, strength, signed, skipped = {}, [], [], []
    for h in HORIZONS_MS:
        ok, change, moved, hit = acc.outcome(T, mid, arrow, h)
        blk = ((T - T[0]) // (h + 5000)).astype(np.int64)[ok]
        if len(np.unique(blk)) < acc.MIN_BLOCKS or moved.sum() == 0:
            skipped.append(h)
            continue
        (c_lo, c_hi), (m_lo, m_hi) = chance(signal, ok, change, h, rate)

        est, lo, hi, n = ratio_by_bucket(blk, np.zeros(ok.sum(), int), hit[ok], moved[ok], 1, rng)
        overall[h] = (est[0], lo[0], hi[0], n[0], ok.sum())

        est, lo, hi, n = ratio_by_bucket(blk, sb[ok], hit[ok], moved[ok], k1, rng)
        few = n < acc.MIN_MOVED
        strength.append(pd.DataFrame({
            "horizon_ms": h, "bucket": np.arange(k1), "moved": n, "accuracy": np.where(few, np.nan, est),
            "lo": np.where(few, np.nan, lo), "hi": np.where(few, np.nan, hi), "chance_lo": c_lo, "chance_hi": c_hi}))

        est, lo, hi, n = ratio_by_bucket(blk, db[ok], change[ok], np.ones(ok.sum()), k2, rng)
        few = n < acc.MIN_MOVED
        signed.append(pd.DataFrame({
            "horizon_ms": h, "bucket": np.arange(k2), "updates": n, "move": np.where(few, np.nan, est),
            "lo": np.where(few, np.nan, lo), "hi": np.where(few, np.nan, hi), "chance_lo": m_lo, "chance_hi": m_hi}))
    if skipped:
        print(f"left out (fewer than {acc.MIN_BLOCKS} blocks of h + 5 s in the recording): "
              + ", ".join(acc.horizon_label(h) for h in skipped))
    if not overall:
        sys.exit("The recording is too short to score any horizon.")
    return overall, pd.concat(strength), pd.concat(signed)


# ---------------- output ----------------
def strength_label(b):
    return f"{STRENGTH_BINS[b]:.1f}-{STRENGTH_BINS[b + 1]:.1f}"


def signed_label(b):
    return f"{SIGNED_BINS[b]:+.1f} to {SIGNED_BINS[b + 1]:+.1f}"


def print_table(df, cell, label, heading):
    df = df.assign(cell=[cell(r) for r in df.itertuples()])
    t = df.pivot(index="bucket", columns="horizon_ms", values="cell")
    t.index = [label(b) for b in t.index]
    t.columns = [acc.horizon_label(h) for h in t.columns]
    print(f"\n{heading}\n{t.to_string()}")


def print_tables(overall, strength, signed):
    pct = lambda v: f"{v:.0%}" if np.isfinite(v) else "-"
    usd = lambda v: f"{v:+.2f}" if np.isfinite(v) else "-"
    star = lambda r, v: "*" if v < r.chance_lo or v > r.chance_hi else " "

    print("\nArrow right, of all updates where the mid moved [95 %]:")
    for h, (e, lo, hi, n, scored) in overall.items():
        print(f"  {acc.horizon_label(h):>6} ahead: {pct(e)} [{pct(lo)}, {pct(hi)}]   ({n:,.0f} moved of {scored:,} scored)")
    print_table(strength, lambda r: f"{pct(r.accuracy)} [{pct(r.lo)}, {pct(r.hi)}]{star(r, r.accuracy)}",
                strength_label, "Arrow right by |signal| [95 %]   (* outside chance)")
    print_table(strength, lambda r: f"{r.moved:,.0f}", strength_label, "Updates where the mid moved, by |signal|")
    print_table(signed, lambda r: f"{usd(r.move)} [{usd(r.lo)}, {usd(r.hi)}]{star(r, r.move)}",
                signed_label, "Mean $ the mid moved, by signal [95 %]   (* outside chance)")


def plot(overall, strength, signed, spread, title, path):
    hs = list(overall)
    cols = 3
    rows = -(-len(hs) // cols)
    fig = Figure(figsize=(15, 9 * rows), dpi=90, layout="constrained")
    FigureCanvasAgg(fig)
    fig.suptitle(title, fontsize=13)
    top, bottom = fig.subfigures(2, 1)
    top.suptitle("How often the arrow is right, by |signal|  (of the updates where the mid moved)", fontsize=12)
    bottom.suptitle("Mean \\$ the mid moved, by signal  (- asks thin: arrow up,  + bids thin: arrow down;  "
                    f"mean bid-ask spread \\${spread:.2f})", fontsize=12)
    ax1 = top.subplots(rows, cols, sharey=True, squeeze=False).ravel()
    ax2 = bottom.subplots(rows, cols, squeeze=False).ravel()
    x1 = (STRENGTH_BINS[:-1] + STRENGTH_BINS[1:]) / 2
    x2 = (SIGNED_BINS[:-1] + SIGNED_BINS[1:]) / 2

    for a, h in zip(ax1, hs):
        s = strength[strength["horizon_ms"] == h]
        a.fill_between(x1, s["chance_lo"], s["chance_hi"], color=acc.GREY, alpha=0.3, lw=0,
                       label="chance: the same signal shifted in time (middle 95 %)")
        a.vlines(x1, s["lo"], s["hi"], color=acc.BLUE, lw=2, alpha=0.4, label="95 % interval (block bootstrap)")
        a.plot(x1, s["accuracy"], color=acc.BLUE, lw=2, marker="o", ms=6, label="arrow right")
        a.axhline(0.5, color=acc.INK, lw=1, ls="--")
        a.set_xlim(0, 1)
        a.set_ylim(0, 1)
        a.yaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
        a.set_xlabel("|signal|")
        e, lo, hi = overall[h][:3]
        acc.style(a, f"{acc.horizon_label(h)} ahead: {e:.0%} right overall [{lo:.0%}, {hi:.0%}]")

    for a, h in zip(ax2, hs):
        s = signed[signed["horizon_ms"] == h]
        a.fill_between(x2, s["chance_lo"], s["chance_hi"], color=acc.GREY, alpha=0.3, lw=0,
                       label="chance (middle 95 %)")
        a.vlines(x2, s["lo"], s["hi"], color=acc.BLUE, lw=2, alpha=0.4, label="95 % interval (block bootstrap)")
        a.plot(x2, s["move"], color=acc.BLUE, lw=2, marker="o", ms=5, label="mean \\$ the mid moved")
        a.axhline(0, color=acc.INK, lw=1)
        a.axvline(0, color=acc.INK, lw=1, ls=":")
        a.set_xlim(-1, 1)
        a.set_xlabel("signal")
        acc.style(a, f"{acc.horizon_label(h)} ahead")

    for axes, ylabel in ((ax1, "Direction right"), (ax2, "\\$ over the horizon")):
        for a in axes[::cols]:
            a.set_ylabel(ylabel)
        for a in axes[len(hs):]:
            a.set_visible(False)
        axes[0].legend(loc="lower left" if axes is ax1 else "upper right", frameon=False, fontsize=9)
    fig.savefig(path)
    return path


if __name__ == "__main__":
    if RECORD:
        record(RECORD_MIN)
    paths = sorted(glob(os.path.join(CHUNK_DIR, "book_*.pkl")))
    if not paths:
        sys.exit(f"No recordings in {CHUNK_DIR} yet: set RECORD = True first.")

    T, mid, spread, signal = load(paths)
    overall, strength, signed = score(T, mid, signal, np.random.default_rng(0))
    print_tables(overall, strength, signed)

    dt = np.diff(T)
    hours = dt[dt <= acc.GAP_MS].sum() / 3.6e6            # recorded time, without the pauses between runs
    when = lambda t: datetime.fromtimestamp(t / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
    title = (f"{viz.SYMBOL} book signal (imbalance within \\${viz.SIGNAL_MOVE:g} of the price) by bucket: "
             f"{hours:.1f} h in {len(paths)} files, {when(T[0])} to {when(T[-1])} UTC, {len(T):,} book updates")
    viz.show_video(plot(overall, strength, signed, spread.mean(), title, PLOT_FILE))
