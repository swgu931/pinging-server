import sys
import csv
import math
import datetime
import numpy as np


def load_rtts(filename):
    """
    Load round-trip times from a ping log written by ping3.py.

    The current format is a CSV with a "seq,timestamp,rtt_ms" header; rows with
    a blank rtt_ms (timeouts) are skipped. The legacy format (one RTT float per
    line, no header) is still supported as a fallback.

    Returns "(timestamps, rtts)" where "timestamps" is a list of ISO-8601
    strings (empty if the file has none) and "rtts" is a list of floats (ms).
    """
    with open(filename, newline='') as f:
        rows = list(csv.reader(f))
    timestamps, rtts = [], []
    if not rows:
        return timestamps, rtts

    header = [c.strip().lower() for c in rows[0]]
    if 'rtt_ms' in header:
        idx_rtt = header.index('rtt_ms')
        idx_ts = header.index('timestamp') if 'timestamp' in header else None
        for row in rows[1:]:
            if len(row) <= idx_rtt:
                continue
            value = row[idx_rtt].strip()
            if value == '':
                continue  # timeout -> no RTT
            rtts.append(float(value))
            if idx_ts is not None and len(row) > idx_ts:
                timestamps.append(row[idx_ts].strip())
    else:
        # Legacy format: one RTT float per line.
        for row in rows:
            if row and row[0].strip():
                try:
                    rtts.append(float(row[0]))
                except ValueError:
                    pass
    return timestamps, rtts


def print_statistical_data(delay_array):
    print('count: ', len(delay_array))
    print('mean: ', np.mean(delay_array))
    print('var: ', np.var(delay_array))
    print('std: ', np.std(delay_array))
    print('min: ', np.min(delay_array))
    print('max: ', np.max(delay_array))


def _stats_text(delay_array):
    """Return a multi-line summary of the RTT statistics for annotation."""
    arr = np.asarray(delay_array, dtype=float)
    return (
        'n    = {:d}\n'
        'mean = {:.4g} ms\n'
        'std  = {:.4g} ms\n'
        'var  = {:.4g} ms$^2$\n'
        'min  = {:.4g} ms\n'
        'max  = {:.4g} ms'
    ).format(len(arr), arr.mean(), arr.std(), arr.var(), arr.min(), arr.max())


def _annotate_stats(plt, delay_array, loc='upper right'):
    """Draw the statistics summary as a boxed text annotation inside the axes."""
    ax = plt.gca()
    x, ha = (0.97, 'right') if 'right' in loc else (0.03, 'left')
    y, va = (0.97, 'top') if 'upper' in loc else (0.03, 'bottom')
    ax.text(x, y, _stats_text(delay_array), transform=ax.transAxes,
            ha=ha, va=va, family='monospace', fontsize=9,
            bbox=dict(boxstyle='round', facecolor='white',
                      edgecolor='gray', alpha=0.8))


def _finish(plt, savepath):
    """Save the current figure if a path is given, then try to show it.

    Showing is a no-op on non-interactive backends (e.g. Agg on a headless
    machine), so saving is what makes the plot usable there.
    """
    plt.tight_layout()
    if savepath:
        plt.savefig(savepath, dpi=150, bbox_inches='tight')
        print('saved:', savepath)
    plt.show()


def plot_timewise(delay_array, timestamps=None, savepath=None):
    import matplotlib.pyplot as plt

    plt.figure()
    if timestamps and len(timestamps) == len(delay_array):
        xs = [datetime.datetime.fromisoformat(t) for t in timestamps]
        plt.plot(xs, delay_array, marker='.', linestyle='-')
        plt.gcf().autofmt_xdate()
        plt.xlabel('time')
    else:
        plt.plot(delay_array, marker='.', linestyle='-')
        plt.xlabel('sample #')
    # Mean reference line + stats annotation.
    mean = float(np.mean(delay_array))
    plt.axhline(mean, color='gray', linestyle='--', linewidth=1)
    plt.ylabel('RTT (ms)')
    plt.title('Ping RTT over time')
    _annotate_stats(plt, delay_array, loc='upper right')
    _finish(plt, savepath)


def plot_normal_dist(delay_array, savepath=None):
    import matplotlib.pyplot as plt
    import scipy.stats as stats
    import seaborn as sns
    from matplotlib.patches import Patch
    from matplotlib.lines import Line2D

    delay_array = np.asarray(delay_array, dtype=float)

    plt.figure()
    # Red = empirical distribution of the measured RTTs (histogram + KDE), on a
    # density scale so the fitted normal curve overlays correctly. seaborn's
    # distplot was removed in 0.14, so use histplot; fall back for old seaborn.
    if hasattr(sns, 'histplot'):
        sns.histplot(delay_array, color='red', stat='density', kde=True)
    else:  # pragma: no cover - legacy seaborn
        sns.distplot(delay_array, color='red')

    # Blue = normal distribution fitted from the sample mean and variance.
    mu = delay_array.mean()
    sigma = math.sqrt(delay_array.var())
    if sigma > 0:
        x = np.linspace(mu - 3 * sigma, mu + 3 * sigma, max(len(delay_array), 100))
        plt.plot(x, stats.norm.pdf(x, mu, sigma), color='blue')

    # Mean reference line + stats annotation.
    plt.axvline(mu, color='gray', linestyle='--', linewidth=1)
    plt.xlabel('RTT (ms)')
    plt.ylabel('density')
    plt.title('RTT distribution vs. fitted normal')

    # Spell out what each colour means.
    legend_handles = [
        Patch(facecolor='red', alpha=0.5,
              label='Observed RTT (histogram + KDE)'),
        Line2D([0], [0], color='blue',
               label='Fitted normal N(mu={:.3g}, sigma={:.3g})'.format(mu, sigma)),
        Line2D([0], [0], color='gray', linestyle='--', label='mean'),
    ]
    plt.legend(handles=legend_handles, loc='upper left', fontsize=8)

    _annotate_stats(plt, delay_array, loc='upper right')
    _finish(plt, savepath)


if __name__ == '__main__':

    # Accept an explicit filename ("python3 plot_from_file.py ping100.csv"),
    # otherwise prompt for it.
    if len(sys.argv) > 1:
        filename = sys.argv[1]
    else:
        filename = input("Please input the filename to plot (e.g. ping100.csv) : ").strip()
    print('filename: ', filename)

    timestamps, delay_array = load_rtts(filename)
    if not delay_array:
        print('No RTT samples found in {}.'.format(filename))
        sys.exit(1)

    print_statistical_data(delay_array)

    # Save alongside the input file, e.g. ping20.csv -> ping20_timeseries.png
    base = filename.rsplit('.', 1)[0]
    plot_timewise(delay_array, timestamps, base + '_timeseries.png')
    plot_normal_dist(delay_array, base + '_dist.png')
