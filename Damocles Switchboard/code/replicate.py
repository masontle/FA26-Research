"""Python translation of Sun (2024), Damocles's Switchboard.

The script expects the unzipped Harvard Dataverse replication package under
data/author_replication_data (or pass --data-dir). Large source files are read
in chunks where practical. Outputs are written to results/.

The R replication uses PanelMatch, fixest, and proprietary/preprocessed source
data. The routines below port the model specifications and use Python
implementations; see README.md for methodological differences that should be
kept in mind when comparing exact coefficients.
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import re
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PAT_ALL = {"211111", "221112", "324110", "325110", "331312", "334413", "454111", "517110", "517210", "518210", "519130", "524113", "541612"}
PAT_HIGH = {"454111", "517110", "518210", "519130", "524113", "541612"}
NAICS_ALT = {"454111", "454112", "511110", "511120", "511130", "511140", "511191", "511199", "515112", "517110", "517210", "517919", "519130", "541511", "561422"}
PATENT_CLASSES = {"702", "703", "700", "706", "715", "707", "710", "717", "709", "704", "341", "705", "701"}
YEARS = set(range(2011, 2021))
STANDARD_QUARTER_ENDS = ["03-31", "06-30", "09-30", "12-31"]
# Bump when read_firm_data changes so stale parquet caches are rebuilt.
PANEL_VERSION = 2
# Days an exchange rate may be carried forward to a quarter-end without a quote
# (weekends and holidays). The H.10 file only has business days.
FX_TOLERANCE_DAYS = 7
EVENT_LAGS = 10
EVENT_LEADS = range(0, 11)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def files_under(root: Path, name: str) -> list[Path]:
    found = [p for p in root.rglob(name) if p.is_file() and "__MACOSX" not in p.parts]
    if not found:
        raise FileNotFoundError(f"Could not find {name} under {root}")
    return found


def one_file(root: Path, name: str) -> Path:
    found = files_under(root, name)
    if len(found) > 1:
        raise ValueError(f"Expected one {name}; found {len(found)}: {found}")
    return found[0]


def one_dir(root: Path, name: str) -> Path:
    found = sorted({p.resolve() for p in root.rglob(name) if p.is_dir() and "__MACOSX" not in p.parts})
    if not found:
        raise FileNotFoundError(f"Could not find {name} directory under {root}")
    if len(found) > 1:
        raise ValueError(f"Expected one {name} directory; found {len(found)}: {found}")
    return found[0]


def clean_naics(s: pd.Series) -> pd.Series:
    """NAICS as strings with genuine missing values kept missing (not 'nan')."""
    out = s.astype("string").str.replace(r"\.0$", "", regex=True).str.strip()
    return out.mask(out.isin(["", "nan", "NaN", "<NA>", "None"]))


# ---------------------------------------------------------------------------
# Firm data
# ---------------------------------------------------------------------------

def read_fx(root: Path) -> pd.DataFrame:
    fx = pd.read_csv(one_file(root, "exchange_rates.csv"), low_memory=False)
    fx_date = fx.iloc[:, 0].astype(str)

    def col(fragment: str) -> pd.Series:
        norm = lambda s: re.sub(r"[^A-Z]", "", s.upper())
        c = next((x for x in fx.columns if norm(fragment) in norm(x)), None)
        if c is None:
            raise KeyError(f"Exchange rate column containing {fragment!r} not found")
        return pd.to_numeric(fx[c], errors="coerce")

    # Rows 0-4 are H.10 header metadata (R: forex[6:12073, ]).
    out = pd.DataFrame({"date": pd.to_datetime(fx_date, errors="coerce"),
                        "ca": col("CANADA"), "cn": col("CHINA"),
                        "sg": col("SINGAPORE"), "hk": col("HONG KONG")}).iloc[5:12073]
    return out.dropna(subset=["date"]).sort_values("date", kind="mergesort")


def attach_fx(d: pd.DataFrame, fx: pd.DataFrame, exact: bool) -> pd.DataFrame:
    """Attach exchange rates to firm-quarters.

    exact=True reproduces the R script (inner join on the exact date), which
    silently drops every quarter-end falling on a weekend because the H.10
    series has business days only. The default instead uses each currency's
    most recent quote within FX_TOLERANCE_DAYS.
    """
    if exact:
        return d.merge(fx, on="date", how="inner")
    out = d.dropna(subset=["date"]).sort_values("date", kind="mergesort")
    for c in ["ca", "cn", "sg", "hk"]:
        rates = fx[["date", c]].dropna()
        out = pd.merge_asof(out, rates, on="date", direction="backward",
                            tolerance=pd.Timedelta(days=FX_TOLERANCE_DAYS))
    return out


def read_firm_data(root: Path, fx_exact: bool = False) -> pd.DataFrame:
    """Convert Compustat extracts to a currency-adjusted firm-period panel.

    Returns every post-1999 Chinese and US observation. `std_quarter` flags
    the four calendar quarter-ends used by the matching analysis; the DDD
    models use all dates, as in the R script.
    """
    fx = read_fx(root)
    parts = []
    for filename, country in (("ss.csv", "CHN"), ("hk8719.csv", "HK"), ("na.csv", "USA")):
        logging.info("Reading %s", filename)
        needed = ["gvkey", "loc", "naics", "datadate", "curcdq", "revtq", "atq", "ltq", "cheq", "cstkq", "lseq", "seqq"]
        d = pd.read_csv(one_file(root, filename), usecols=needed, low_memory=False)
        d["date"] = pd.to_datetime(d["datadate"].astype(str), format="%Y%m%d", errors="coerce")
        d = attach_fx(d, fx, fx_exact)
        rate = {"CHN": "cn", "USA": "ca", "HK": None}[country]
        cur = d["curcdq"].astype(str)

        def usd(var: str) -> pd.Series:
            v = pd.to_numeric(d[var], errors="coerce")
            if country == "HK":
                divisor = np.select([cur.eq("CNY"), cur.eq("HKD")], [d.cn, d.hk], default=d.sg)
                return pd.Series(np.where(cur.eq("USD"), v, v / divisor), index=d.index)
            return pd.Series(np.where(cur.eq("USD"), v, v / d[rate]), index=d.index)

        q = pd.DataFrame({"date": d.date, "gvkey": d.gvkey.astype(str),
                          "loc": d["loc"].astype(str), "naics": clean_naics(d.naics),
                          "rev": usd("revtq"), "at": usd("atq"), "lt": usd("ltq"),
                          "che": usd("cheq"), "cstk": usd("cstkq"), "lse": usd("lseq"), "seq": usd("seqq")})
        parts.append(q)
    # Same stacking order as R: rbind(china, hongkong, namerica).
    d = pd.concat(parts, ignore_index=True)
    d = d.loc[(d.date > "1999-12-31") & d["loc"].isin(["CHN", "USA"])]
    d = d.drop_duplicates(["date", "gvkey"]).copy()
    d["std_quarter"] = d.date.dt.strftime("%m-%d").isin(STANDARD_QUARTER_ENDS)
    for c in ["rev", "at", "lt", "che", "cstk", "lse", "seq"]:
        d.loc[d[c] < 0, c] = np.nan
    d["logrev"] = np.log(d.rev + .01)
    d["logat"] = np.log(d["at"] + .01)
    d["loglt"] = np.log(d["lt"] + .01)
    d["logrev_panel"] = np.log(d.rev + .001)
    d["logat_panel"] = np.log(d["at"] + .001)
    d["loglt_panel"] = np.log(d["lt"] + .001)
    d["logche"] = np.log(d.che + .01)
    d["logcstk"] = np.log(d.cstk + .01)
    d["logseq"] = np.log(d.seq + .01)
    d["loglse"] = np.log(d.lse + .01)
    d["year"] = d.date.dt.year.astype(str)
    d["post"] = (d.date > "2014-05-31").astype(int)
    d["treat"] = d.naics.isin(PAT_ALL).astype(int)
    d["treat_high"] = d.naics.isin(PAT_HIGH).astype(int)
    d["treat_alt"] = d.naics.isin(NAICS_ALT).astype(int)
    return d


def load_firm_panel(data_dir: Path, results_dir: Path, fx_exact: bool, rebuild: bool) -> pd.DataFrame:
    cache = results_dir / "firm_panel_prepared.parquet"
    stamp_path = results_dir / "firm_panel_prepared.json"
    stamp = {"panel_version": PANEL_VERSION, "fx_exact": fx_exact,
             "data_dir": str(data_dir.resolve())}
    if not rebuild and cache.exists() and stamp_path.exists():
        try:
            if json.loads(stamp_path.read_text(encoding="utf-8")) == stamp:
                logging.info("Using prepared firm panel cache %s", cache)
                return pd.read_parquet(cache)
        except (OSError, ValueError):
            pass
    logging.info("Building firm panel (cache missing or stale)")
    firm = read_firm_data(data_dir, fx_exact)
    firm.to_parquet(cache, index=False)
    stamp_path.write_text(json.dumps(stamp, indent=2), encoding="utf-8")
    return firm


def china_matching_panel(d: pd.DataFrame) -> pd.DataFrame:
    """R's `ctrim`: Chinese firms, standard quarter-ends, 2010-12-31 trimmed."""
    cn = d.loc[(d["loc"] == "CHN") & d.std_quarter & (d.date != "2010-12-31")].copy()
    cn["q"] = cn.date.dt.to_period("Q")
    return cn


def model_ddd(d: pd.DataFrame, out: Path) -> None:
    import statsmodels.formula.api as smf
    # R's DDD sample (dnew) uses every reporting date, not only calendar
    # quarter-ends, and drops missing NAICS.
    d = d.loc[(d.date > "2010-12-31") & d.naics.notna()].copy()
    d["china"] = (d["loc"] == "CHN").astype(int)
    rows = []
    for uptake in ["treat", "treat_high", "treat_alt"]:
        for saturated in [False, True]:
            rhs = f"{uptake} * china * post"
            if saturated:
                rhs += " + logat + loglt"
            cols = ["logrev", uptake, "china", "post", "year", "naics"] + (["logat", "loglt"] if saturated else [])
            sample = d.replace([np.inf, -np.inf], np.nan).dropna(subset=cols)
            model = smf.ols("logrev ~ " + rhs + " + C(year)", data=sample).fit(
                cov_type="cluster", cov_kwds={"groups": sample.naics.astype(str), "use_correction": True})
            term = f"{uptake}:china:post"
            rows.append({"model": f"{'saturated' if saturated else 'naive'}_{uptake}",
                         "term": term, "estimate": model.params.get(term, np.nan),
                         "std_error": model.bse.get(term, np.nan), "p_value": model.pvalues.get(term, np.nan),
                         "n": int(model.nobs)})
    pd.DataFrame(rows).to_csv(out / "firm_ddd.csv", index=False)
    # 2013 pre-shock descriptions and Welch tests (Tables A3-A5), standard dates only.
    q = d.loc[(d["loc"] == "CHN") & (d.year == "2013") & d.std_quarter].copy()
    for grp, label in [(1, "data_intensive"), (0, "other_firms")]:
        desc = q.loc[q.treat == grp, ["logrev", "logat", "logche", "logcstk", "loglt", "logseq"]].describe().T
        desc.to_csv(out / f"firm_2013_{label}_summary.csv")
    from scipy.stats import ttest_ind
    tests = []
    for col in ["logrev", "logat", "logche", "logcstk", "loglt", "logseq"]:
        a = q.loc[q.treat == 1, col].dropna(); b = q.loc[q.treat == 0, col].dropna()
        res = ttest_ind(a, b, equal_var=False)
        tests.append({"variable": col, "treated_mean": a.mean(), "control_mean": b.mean(),
                      "difference": a.mean()-b.mean(), "t_statistic": res.statistic, "p_value": res.pvalue,
                      "n_treated": len(a), "n_control": len(b)})
    pd.DataFrame(tests).to_csv(out / "firm_2013_ttests.csv", index=False)


def patent_sector_tables(root: Path, out: Path) -> None:
    """Rebuild patent-based data-intensity sector frequencies and Table A2 list."""
    patents = pd.read_csv(one_file(root, "patents_xi.csv"), dtype={"permno": "string", "class": "string"},
                          usecols=["permno", "class"], low_memory=False)
    stocks = []
    for filename in ["NASDAQ.csv", "NYSE.csv"]:
        stock = pd.read_csv(one_file(root, filename), dtype={"PERMNO": "string", "date": "string", "NAICS": "string"},
                            usecols=["PERMNO", "date", "NAICS"], low_memory=False)
        stocks.append(stock.loc[stock.date.eq("20090930")])
    stock09 = pd.concat(stocks, ignore_index=True)
    # Outer merge as in R (d5); "all_patents" therefore also counts stock rows
    # without a matched patent, exactly like the author's tab2.
    d = patents.merge(stock09, left_on="permno", right_on="PERMNO", how="outer")
    d["class3"] = d["class"].str.replace(r"\.0$", "", regex=True).str.strip()
    d["data_patent"] = d.class3.isin(PATENT_CLASSES)
    d["naics"] = clean_naics(d.NAICS)
    data_counts = d.loc[d.data_patent & d.naics.notna()].groupby("naics").size().rename("data_patents")
    sector_codes = data_counts.index
    all_counts = d.loc[d.naics.isin(sector_codes)].groupby("naics").size().rename("all_patents")
    table = pd.concat([data_counts, all_counts], axis=1).fillna(0).reset_index(names="NAICS")
    table["share_data_patents"] = table.data_patents / table.all_patents.replace(0, np.nan)
    table.to_csv(out / "table_A1_patent_data_intensity.csv", index=False)
    alt = sorted(NAICS_ALT)
    pd.DataFrame({"NAICS": alt, "internet_keyword_sector": 1}).to_csv(out / "table_A2_internet_keyword_sectors.csv", index=False)


# ---------------------------------------------------------------------------
# Firm event study (PanelMatch approximation)
# ---------------------------------------------------------------------------

class EventStudy:
    """Nearest-Mahalanobis approximation of the authors' PanelMatch calls.

    Time is indexed by the sorted list of observed quarter-ends, mirroring
    R's `Date` index (1..N over unique dates), so leads/lags count observed
    periods. For each specification the first treated period is the first
    observed quarter after the R cutoff date and the baseline is the period
    before it; treated and control units are matched on their EVENT_LAGS
    pre-baseline histories.
    """

    def __init__(self, cn: pd.DataFrame, r_covariates: bool = True):
        wide = cn.pivot_table(index="gvkey", columns="q", values=["logrev_panel", "logat_panel", "loglt_panel"],
                              aggfunc="first")
        self.periods = sorted(cn.q.unique())
        self.y = wide["logrev_panel"].reindex(columns=self.periods).sort_index()
        at = wide["logat_panel"].reindex(columns=self.periods).sort_index()
        rev = self.y
        lt = wide["loglt_panel"].reindex(columns=self.periods).sort_index()
        if r_covariates:
            # Sun2024.R: covs.formula = ~ I(lag(at,1:10)) + I(lag(rev,1:10) + I(lag(lt,1:10)))
            # The parenthesis places lag(lt) inside the rev term, so PanelMatch
            # matches on lagged assets and on lagged (rev + lt).
            self.covariates = {"logat_panel": at, "logrev_plus_loglt": rev + lt}
        else:
            self.covariates = {"logat_panel": at, "logrev_panel": rev, "loglt_panel": lt}
        firm = cn.sort_values(["gvkey", "date"]).drop_duplicates("gvkey", keep="last").set_index("gvkey")
        self.naics = firm.naics.reindex(self.y.index)

    def first_treated_index(self, cutoff: str) -> int:
        cut = pd.Timestamp(cutoff)
        for i, q in enumerate(self.periods):
            if q.end_time.normalize() > cut:
                return i
        raise ValueError(f"No observed period after {cutoff}")

    def ids_in(self, codes: set[str]) -> tuple[pd.Index, pd.Index]:
        treated = self.naics.index[self.naics.isin(codes)]
        controls = self.naics.index[~self.naics.isin(codes)]
        return treated, controls

    def run(self, name: str, treated_ids, control_ids, cutoff: str, max_matches: int) -> list[dict]:
        from scipy.spatial.distance import cdist
        first = self.first_treated_index(cutoff)
        base = first - 1
        if base - EVENT_LAGS + 1 < 0:
            raise ValueError(f"{name}: fewer than {EVENT_LAGS} periods before {cutoff}")
        hist_periods = self.periods[base - EVENT_LAGS + 1: base + 1]
        hist = pd.concat({k: v.reindex(columns=hist_periods) for k, v in self.covariates.items()}, axis=1)
        hist = hist.replace([np.inf, -np.inf], np.nan)
        treated_ids = pd.Index(sorted(set(treated_ids) & set(hist.index)))
        control_ids = pd.Index(sorted(set(control_ids) & set(hist.index)))
        x1, x0 = hist.loc[treated_ids], hist.loc[control_ids]
        # Units with no observed pre-period history cannot be matched; with
        # median imputation they would all tie at the median profile.
        x1, x0 = x1.loc[x1.notna().any(axis=1)], x0.loc[x0.notna().any(axis=1)]
        if not len(x1) or not len(x0):
            return []
        med = pd.concat([x1, x0]).median()
        x1, x0 = x1.fillna(med), x0.fillna(med)
        cov = np.cov(pd.concat([x1, x0]).to_numpy(), rowvar=False)
        inv = np.linalg.pinv(cov + np.eye(cov.shape[0]) * 1e-5)
        dist = cdist(x1.to_numpy(), x0.to_numpy(), metric="mahalanobis", VI=inv)
        k = min(max_matches, len(x0))
        nearest = np.argsort(dist, axis=1, kind="stable")[:, :k]
        y1, y0 = self.y.loc[x1.index], self.y.loc[x0.index]
        base_q = self.periods[base]
        rows = []
        for lead in EVENT_LEADS:
            t = first + lead
            if t >= len(self.periods):
                break
            target = self.periods[t]
            td = (y1[target] - y1[base_q]).to_numpy()
            cd = (y0[target] - y0[base_q]).to_numpy()
            effects = []
            for i in range(len(x1)):
                if np.isnan(td[i]):
                    continue
                cv = cd[nearest[i]]
                cv = cv[~np.isnan(cv)]
                if len(cv):
                    effects.append(td[i] - cv.mean())
            est = float(np.mean(effects)) if effects else np.nan
            rows.append({"specification": name, "quarter_after_date": lead, "baseline_quarter": str(base_q),
                         "target_quarter": str(target), "estimate_log_points": est,
                         "approx_revenue_pct": (np.exp(est) - 1) * 100 if np.isfinite(est) else np.nan,
                         "treated_firms": len(effects), "matched_controls_per_firm": k})
        return rows


# (name, treated NAICS set, R cutoff such that treatment = date > cutoff, max matches)
EVENT_SPECS = [("main_4003", PAT_ALL, "2014-05-31", 4003),
               ("main_20", PAT_ALL, "2014-05-31", 20),
               ("high_intensity", PAT_HIGH, "2014-05-31", 4003),
               ("alternative_naics", NAICS_ALT, "2014-05-31", 4003),
               ("false_date_2008", PAT_ALL, "2008-06-29", 4003),
               ("pretrend_2012", PAT_ALL, "2012-02-28", 4003)]


def firm_event_studies(d: pd.DataFrame, out: Path, r_covariates: bool = True, placebo: bool = True) -> None:
    """Main event study (Fig 4) plus the supplementary sensitivity checks."""
    import matplotlib.pyplot as plt
    es = EventStudy(china_matching_panel(d), r_covariates=r_covariates)
    results = []
    for name, codes, cutoff, nmatch in EVENT_SPECS:
        treated, controls = es.ids_in(codes)
        logging.info("Event study %s: %d treated, %d control firms", name, len(treated), len(controls))
        results.extend(es.run(name, treated, controls, cutoff, nmatch))
    rdf = pd.DataFrame(results)

    main = rdf.loc[rdf.specification == "main_4003"].drop(columns="specification").rename(
        columns={"quarter_after_date": "quarter_after_shock"})
    main.to_csv(out / "firm_panelmatch_approx.csv", index=False)
    if len(main):
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.plot(main.quarter_after_shock, main.estimate_log_points, marker="o")
        ax.axhline(0, color="black", linewidth=.8)
        ax.set(xlabel="Quarters after 2014 shock", ylabel="Estimated log revenue effect",
               title="Firm revenue event study (Python match approximation)")
        fig.tight_layout(); fig.savefig(out / "figure4_firm_event_study_approx.png", dpi=200); plt.close(fig)

    placebo_rows = []
    if placebo:
        # 30 seeded placebo samples of 216 non-data-intensive firms (R: Fig A5).
        # As in R, every firm outside the placebo sample, including the real
        # data-intensive firms, is an eligible control.
        rng = np.random.default_rng(2024)
        _, pool = es.ids_in(PAT_ALL)
        pool = pd.Index(sorted(pool))
        n_treat = min(216, len(pool))
        for draw in range(30):
            treated = pd.Index(rng.choice(pool, size=n_treat, replace=False))
            controls = es.y.index.difference(treated)
            placebo_rows.extend(es.run(f"placebo_draw_{draw+1:02d}", treated, controls, "2014-05-31", 4003))
    pd.DataFrame(results + placebo_rows).to_csv(out / "firm_panel_robustness_approx.csv", index=False)
    if len(rdf):
        fig, ax = plt.subplots(figsize=(10, 6))
        for name, group in rdf.groupby("specification"):
            ax.plot(group.quarter_after_date, group.estimate_log_points, marker="o", label=name)
        ax.axhline(0, color="black", linewidth=.8)
        ax.set(xlabel="Quarters after assigned date", ylabel="Estimated log revenue effect",
               title="Firm event study sensitivity checks (Python approximation)")
        ax.legend(fontsize=8, ncol=2); fig.tight_layout()
        fig.savefig(out / "figure_A2_A4_robustness_approx.png", dpi=200); plt.close(fig)
    if placebo_rows:
        pdf = pd.DataFrame(placebo_rows)
        pdf.groupby("quarter_after_date").agg(mean_estimate=("estimate_log_points", "mean"),
            sd_across_draws=("estimate_log_points", "std"), draws=("estimate_log_points", "count")).reset_index().to_csv(
                out / "firm_placebo_30_draw_summary.csv", index=False)


# ---------------------------------------------------------------------------
# Citations
# ---------------------------------------------------------------------------

CITATION_COLS = ["PY", "TC", "SO", "AU"]


def _citation_frame(chunk: pd.DataFrame, field: str) -> pd.DataFrame:
    chunk = chunk.copy()
    chunk["PY"] = pd.to_numeric(chunk.PY, errors="coerce")
    chunk = chunk.loc[chunk.PY.isin(YEARS)].copy()
    chunk["authors"] = chunk.AU.fillna("").str.count(";") + 1
    chunk["field"] = field
    return chunk[["PY", "TC", "SO", "authors", "field"]]


def _read_with_bad_line_count(path: Path, **kwargs):
    """read_csv that logs, rather than silently drops, malformed rows."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = pd.read_csv(path, on_bad_lines="warn", **kwargs)
        if kwargs.get("chunksize"):
            result = list(result)
    bad = sum(str(w.message).count("Skipping line") for w in caught)
    if bad:
        logging.warning("%s: skipped %d malformed row(s)", path.name, bad)
    return result


def read_citations(root: Path, folder: str) -> pd.DataFrame:
    """Read WoS tab-delimited extracts (one file per field), keeping 2011-20."""
    base = one_dir(root, folder)
    frames = []
    files = sorted(base.glob("*.txt"))
    if not files:
        raise FileNotFoundError(f"No .txt extracts in {base}")
    for p in files:
        logging.info("Reading citation extract %s/%s", folder, p.name)
        chunks = _read_with_bad_line_count(p, sep="\t", dtype=str, usecols=lambda c: c.strip().lstrip("﻿") in CITATION_COLS,
                                           chunksize=250_000, low_memory=False, encoding_errors="replace")
        for chunk in chunks:
            chunk.columns = [c.strip().lstrip("﻿") for c in chunk.columns]
            missing = set(CITATION_COLS) - set(chunk.columns)
            if missing:
                raise ValueError(f"{p} is missing columns {sorted(missing)}")
            part = _citation_frame(chunk, p.stem)
            if len(part):
                frames.append(part)
    if not frames:
        raise ValueError(f"No article rows for 2011-2020 found in {folder}")
    return pd.concat(frames, ignore_index=True)


def read_citations_csv(root: Path, folder: str) -> pd.DataFrame:
    """CN1120new is distributed as discipline-level CSV extracts (R: read.csv)."""
    base = one_dir(root, folder)
    files = sorted(list(base.glob("*.csv")) + list(base.glob("*.tab")))
    if not files:
        raise FileNotFoundError(f"No .csv extracts in {base}")
    frames = []
    for p in files:
        logging.info("Reading citation extract %s/%s", folder, p.name)
        z = _read_with_bad_line_count(p, dtype=str, low_memory=False, encoding_errors="replace")
        z.columns = [c.strip().lstrip("﻿") for c in z.columns]
        missing = set(CITATION_COLS) - set(z.columns)
        if missing:
            raise ValueError(f"{p} is missing columns {sorted(missing)}")
        frames.append(_citation_frame(z[CITATION_COLS], p.stem))
    return pd.concat(frames, ignore_index=True)


def read_rpp(root: Path) -> pd.DataFrame:
    base = one_dir(root, "RPP2010")
    files = sorted(base.glob("*.xls"))
    if not files:
        raise FileNotFoundError(f"No RPP2010 .xls workbooks in {base}")
    vals = []
    for p in files:
        frame = pd.read_excel(p, engine="xlrd")
        frame["field"] = p.stem
        vals.append(frame)
    raw = pd.concat(vals, ignore_index=True)
    ref = pd.to_numeric(raw["Cited Reference Count"], errors="coerce")
    pages = pd.to_numeric(raw["Number of Pages"], errors="coerce")
    return pd.DataFrame({"field": raw["Research Areas"], "rp_raw": ref, "pages": pages}).groupby("field", as_index=False).sum(min_count=1).assign(rp=lambda x: x.rp_raw / x.pages)


def _nb2_loglik(y, mu, alpha):
    from scipy.special import gammaln
    r = 1.0 / alpha
    return float(np.sum(gammaln(y + r) - gammaln(r) - gammaln(y + 1)
                        + r * (np.log(r) - np.log(r + mu)) + y * (np.log(mu) - np.log(r + mu))))


def _column_scale(A: np.ndarray) -> np.ndarray:
    d = np.sqrt(np.clip(np.diag(A), 0, None))
    # Columns with no within-group variation (fully absorbed) are dropped.
    return np.where(d > 1e-12 * max(1.0, d.max()), d, np.inf)


def _scaled_solve(A: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Solve A x = b after symmetric Jacobi scaling (A is X'WX)."""
    d = _column_scale(A)
    As = A / np.outer(d, d)
    As[~np.isfinite(As)] = 0.0
    return np.linalg.lstsq(As, b / d, rcond=1e-12)[0] / d


def _scaled_pinv(A: np.ndarray) -> np.ndarray:
    d = _column_scale(A)
    As = A / np.outer(d, d)
    As[~np.isfinite(As)] = 0.0
    return np.linalg.pinv(As, rcond=1e-12) / np.outer(d, d)


def nb2_fe_fit(data: pd.DataFrame, slopes: list[str], absorb: str, dummies: list[str], cluster: str,
               tol: float = 1e-11, maxiter: int = 200) -> dict:
    """NB2 maximum likelihood with one absorbed fixed effect, like fixest::fenegbin.

    The journal (`absorb`) effects are profiled out: for given slopes and
    alpha each group's effect solves its own score equation by a safeguarded
    1-D Newton iteration. The slopes then take Newton steps on the profiled
    likelihood (Hessian from weighted within-group demeaned regressors) with
    backtracking, and alpha is updated by 1-D maximization. Plain IRLS was
    unstable here because a few articles with citation counts far above their
    journal mean make the working response explode. Additional
    low-dimensional fixed effects (`dummies`, e.g. the 31 fields) enter as
    explicit indicator regressors, giving the same slopes as absorbing them.
    As in fixest, absorbed groups whose outcome is all zero are dropped.
    Standard errors are cluster-robust sandwich errors with the fixest
    small-sample correction and t(G-1) p-values.
    """
    from scipy.optimize import minimize_scalar
    from scipy.stats import t as student_t

    y_all = pd.to_numeric(data.TC, errors="coerce").to_numpy(float)
    keep = pd.Series(y_all).groupby(data[absorb].astype(str).to_numpy()).transform("sum").to_numpy() > 0
    data = data.loc[keep]
    y = y_all[keep]
    n = len(y)
    cols = [pd.to_numeric(data[c], errors="coerce").to_numpy(float) for c in slopes]
    for name in dummies:
        codes, levels = pd.factorize(data[name].astype(str), sort=True)
        cols.extend((codes == j).astype(float) for j in range(1, len(levels)))
    X = np.column_stack(cols)
    del cols
    k = X.shape[1]
    g, fe_levels = pd.factorize(data[absorb].astype(str), sort=True)
    J = len(fe_levels)
    gsum = lambda v: np.bincount(g, weights=v, minlength=J)

    def solve_fe(xb, alpha, c):
        """Per-group c solving sum_i (y_i - mu_i)/(1 + alpha mu_i) = 0."""
        c = c.copy()
        for _ in range(100):
            mu = np.exp(np.clip(xb + c[g], -50, 50))
            f = gsum((y - mu) / (1 + alpha * mu))
            fp = gsum(mu * (1 + alpha * y) / (1 + alpha * mu) ** 2)
            delta = np.clip(f / np.maximum(fp, 1e-300), -2.0, 2.0)
            c += delta
            if np.max(np.abs(delta)) < 1e-10:
                break
        return c

    def state(beta, alpha, c):
        xb = X @ beta
        c = solve_fe(xb, alpha, c)
        mu = np.exp(np.clip(xb + c[g], -50, 50))
        return c, mu, _nb2_loglik(y, mu, alpha)

    def demeaned(mu, alpha):
        w = mu / (1 + alpha * mu)
        dw = gsum(w)
        Xd = X.copy()
        for j in range(k):
            Xd[:, j] -= (gsum(w * Xd[:, j]) / dw)[g]
        return Xd, w

    beta = np.zeros(k)
    alpha = 1.0
    c0 = np.log(gsum(y) / np.bincount(g, minlength=J))
    c, mu, ll = state(beta, alpha, c0)
    converged = False
    for it in range(maxiter):
        Xd, w = demeaned(mu, alpha)
        score = (y - mu) / (1 + alpha * mu)
        H = Xd.T @ (w[:, None] * Xd)
        grad = Xd.T @ score
        delta = _scaled_solve(H, grad)
        del Xd
        step = 1.0
        while True:
            c_try, mu_try, ll_try = state(beta + step * delta, alpha, c)
            if ll_try >= ll or step < 1e-6:
                break
            step /= 2
        if ll_try >= ll:
            beta, c, mu = beta + step * delta, c_try, mu_try
        res = minimize_scalar(lambda th: -_nb2_loglik(y, mu, math.exp(th)), bounds=(-12, 8), method="bounded",
                              options={"xatol": 1e-9})
        alpha = math.exp(res.x)
        c, mu, ll_new = state(beta, alpha, c)
        rel = abs(ll_new - ll) / max(1.0, abs(ll))
        ll = ll_new
        logging.debug("NB2 iter %d: loglik %.6f alpha %.6f step %.3g max|delta| %.2e",
                      it + 1, ll, alpha, step, float(np.max(np.abs(step * delta))))
        if rel < tol and np.max(np.abs(step * delta)) < 1e-7:
            converged = True
            break
    # Sandwich at the solution, using the demeaned (profiled) regressors.
    Xd, w = demeaned(mu, alpha)
    score = (y - mu) / (1 + alpha * mu)
    bread = _scaled_pinv(Xd.T @ (w[:, None] * Xd))
    cl_codes, cl_levels = pd.factorize(data[cluster].astype(str), sort=True)
    G = len(cl_levels)
    meat_scores = np.column_stack([np.bincount(cl_codes, weights=Xd[:, j] * score, minlength=G) for j in range(k)])
    meat = meat_scores.T @ meat_scores
    correction = (G / max(1, G - 1)) * ((n - 1) / max(1, n - (k + J)))
    vcov = bread @ meat @ bread * correction
    ses = np.sqrt(np.maximum(0, np.diag(vcov)))[:len(slopes)]
    b = beta[:len(slopes)]
    pvals = 2 * student_t.sf(np.abs(b / np.maximum(ses, 1e-300)), max(1, G - 1))
    return {"converged": converged, "iterations": it + 1, "alpha": alpha, "n": n, "n_dropped_all_zero_fe": int((~keep).sum()),
            "coef": dict(zip(slopes, map(float, b))), "se": dict(zip(slopes, map(float, ses))),
            "p": dict(zip(slopes, map(float, pvals))), "loglike": ll}


def citation_models(root: Path, out: Path) -> None:
    cn = pd.concat([read_citations(root, "CN0020"), read_citations_csv(root, "CN1120new")], ignore_index=True)
    us = read_citations(root, "US1120")
    rpp = read_rpp(root)
    cn["china"] = 1
    us["china"] = 0
    d = pd.concat([cn, us], ignore_index=True, sort=False)
    for c in ["PY", "TC"]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d.dropna(subset=["TC", "SO", "field", "PY"]).copy()
    d["age"] = 2023 - d.PY
    d["post"] = (d.PY > 2014).astype(int)
    d["authors"] = pd.to_numeric(d.authors, errors="coerce")
    d = d.merge(rpp[["field", "rp"]], on="field", how="left")
    unmatched = sorted(set(d.loc[d.rp.isna(), "field"]))
    if unmatched:
        logging.warning("Fields without an RPP2010 match (log_rp missing): %s", unmatched)
    d["log_rp"] = np.log(d.rp)
    cn_rp = d.loc[d.china == 1, "log_rp"]
    median_rp, mu, sd = cn_rp.median(), cn_rp.mean(), cn_rp.std()
    d["high_knowledge"] = np.where(d.log_rp.isna(), np.nan, (d.log_rp >= median_rp).astype(float))
    d["extreme_knowledge"] = np.select([d.log_rp < mu - sd, d.log_rp > mu + sd], [0, 1], default=np.nan)
    d["field_year"] = d.field.astype(str) + "_" + d.PY.astype(int).astype(str)
    # H2 models use China only; cross-country DiD keeps US and China.
    cn = d.loc[d.china == 1].copy()
    cn50 = cn.loc[cn.TC > cn.groupby("field_year").TC.transform("median")].copy()
    records = []

    def fit_count(df, family, rhs, name, dummies):
        left, right = [x.strip() for x in rhs.split("*")]
        slopes = [left, right, f"{left}:{right}", "age", "authors"]
        needed = ["TC", "age", "authors", "SO", "field", left, right]
        sample = df.dropna(subset=list(dict.fromkeys(needed))).copy()
        sample[f"{left}:{right}"] = sample[left].astype(float) * sample[right].astype(float)
        if family == "nb":
            fitted = nb2_fe_fit(sample, slopes, absorb="SO", dummies=dummies, cluster="field")
            estimates, errors, p_values = fitted["coef"], fitted["se"], fitted["p"]
            status = "converged" if fitted["converged"] else f"nb2_did_not_converge_after_{fitted['iterations']}"
            n_used, alpha = fitted["n"], fitted["alpha"]
            if not fitted["converged"]:
                logging.warning("%s did not converge", name)
        else:
            import pyfixest as pf
            extra = "".join(f" + C({x})" for x in dummies)
            formula = f"TC ~ {rhs} + age + authors{extra} | SO"
            model = pf.fepois(formula, data=sample, vcov={"CRV1": "field"}, copy_data=False, store_data=False)
            tab = model.tidy()
            tab = tab.loc[~tab.index.astype(str).str.startswith("C(")]
            estimates = tab["Estimate"].to_dict()
            errors = tab["Std. Error"].to_dict()
            pcol = next((c for c in tab.columns if "Pr(>" in c), None)
            p_values = tab[pcol].to_dict() if pcol else {}
            status, n_used, alpha = "converged", int(model._N), np.nan
        fe_label = "SO" + "".join(f" + {x}" for x in dummies)
        for term, estimate in estimates.items():
            records.append({"model": name, "term": term, "estimate": estimate,
                            "std_error": errors.get(term, np.nan), "p_value": p_values.get(term, np.nan),
                            "incidence_rate_ratio": np.exp(estimate), "n": n_used,
                            "fixed_effects": fe_label, "converged": status, "nb2_alpha": alpha})

    for fam in ["nb", "poisson"]:
        for label, frame in [("all", cn), ("top_half", cn50)]:
            fit_count(frame, fam, "post * log_rp", f"{fam}_{label}_continuous", [])
        for var in ["high_knowledge", "extreme_knowledge"]:
            fit_count(cn.dropna(subset=[var]), fam, f"post * {var}", f"{fam}_all_{var}", [])
        fit_count(d, fam, "post * china", f"{fam}_china_us_did", ["field"])
    # Pre-treatment trend check matching Table A9.
    trend = cn.loc[cn.PY < 2015].copy()
    trend["logtc"] = np.log(trend.TC + .1)
    import pyfixest as pf
    trend = trend.dropna(subset=["logtc", "PY", "high_knowledge", "age", "authors", "SO", "field"])
    m = pf.feols("logtc ~ PY * high_knowledge + age + authors | SO", data=trend,
                 vcov={"CRV1": "field"}, copy_data=False, store_data=False)
    trend_tab = m.tidy()
    tname = next((x for x in trend_tab.index if set(str(x).split(":")) == {"PY", "high_knowledge"}), "PY:high_knowledge")
    records.append({"model": "pretreatment_trend", "term": tname, "estimate": m.coef().get(tname),
                    "std_error": m.se().get(tname), "p_value": m.pvalue().get(tname), "n": int(m._N),
                    "fixed_effects": "SO", "converged": "converged"})
    pd.DataFrame(records).to_csv(out / "citation_models.csv", index=False)
    # Table A6 style field summaries and Fig A6 series.
    cn.groupby("field").agg(n=("TC", "size"), citations_mean=("TC", "mean"), age_mean=("age", "mean"), authors_mean=("authors", "mean")).to_csv(out / "citation_summary_by_field.csv")
    trends = cn.dropna(subset=["high_knowledge"]).assign(
        knowledge_group=lambda x: np.where(x.high_knowledge.eq(1), "knowledge-intensive", "other"))
    trends.assign(PY=trends.PY.astype(int)).groupby(["PY", "knowledge_group"]).TC.sum().unstack().to_csv(out / "citation_trends.csv")


def visualize(root: Path, out: Path) -> None:
    import matplotlib.pyplot as plt
    # Figure 1: StatCounter series supplied by the authors.
    try:
        p = one_file(root, "CNsearch.csv")
        x = pd.read_csv(p)
        ax = x.plot(x="Date", y=["Google", "Baidu"], figsize=(10, 5))
        ax.set_ylabel("Relative share (%)")
        ax.figure.tight_layout(); ax.figure.savefig(out / "figure1_search_substitution.png", dpi=200); plt.close(ax.figure)
    except Exception as e:
        logging.warning("Figure 1 skipped: %s", e)
    # Figure 3: accessibility history; missing observations are linearly filled.
    try:
        p = one_file(root, "gfwfinal.csv")
        x = pd.read_csv(p)
        vals = x.iloc[:, 1:101].apply(pd.to_numeric, errors="coerce").interpolate(limit_direction="both")
        fig, ax = plt.subplots(figsize=(12, 6)); ax.imshow(vals.T, aspect="auto", interpolation="nearest", cmap="RdYlGn")
        ax.set_xlabel("Date index"); ax.set_ylabel("Top 100 websites"); fig.tight_layout()
        fig.savefig(out / "figure3_internet_control.png", dpi=200); plt.close(fig)
    except Exception as e:
        logging.warning("Figure 3 skipped: %s", e)
    try:
        rpp = read_rpp(root).dropna(subset=["rp"]).sort_values("rp")
        fig, ax = plt.subplots(figsize=(12, 6)); ax.bar(rpp.field, np.log(rpp.rp))
        ax.set_ylabel("Logged references per page"); ax.tick_params(axis="x", rotation=70)
        fig.tight_layout(); fig.savefig(out / "figure_A1_knowledge_intensity.png", dpi=200); plt.close(fig)
    except Exception as e:
        logging.warning("Figure A1 skipped: %s", e)
    try:
        trends = pd.read_csv(out / "citation_trends.csv", index_col=0)
        fig, ax = plt.subplots(figsize=(8, 5))
        for col in trends.columns:
            ax.plot(trends.index, np.log(pd.to_numeric(trends[col], errors="coerce").clip(lower=1)), marker="o", label=col)
        ax.axvline(2014.5, color="black", linestyle="--", linewidth=1)
        ax.set(xlabel="Publication year", ylabel="Logged total citations", title="Citation trends by knowledge intensity")
        ax.legend(); fig.tight_layout(); fig.savefig(out / "figure_A6_citation_trends.png", dpi=200); plt.close(fig)
    except Exception as e:
        logging.warning("Figure A6 skipped: citation_trends.csv unavailable (%s)", e)


def record_completion(metadata_path: Path, data_dir: Path, analysis: str, settings: dict) -> None:
    """Record an analysis only after it finished successfully."""
    from datetime import datetime, timezone
    prior = {}
    if metadata_path.exists():
        try:
            prior = json.loads(metadata_path.read_text(encoding="utf-8"))
        except ValueError:
            prior = {}
    try:
        shown = data_dir.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        shown = "<external --data-dir>"
    runs = prior.get("completed", {}) if isinstance(prior.get("completed"), dict) else {}
    runs[analysis] = {"finished_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), **settings}
    metadata_path.write_text(json.dumps({"data_dir": shown, "completed": dict(sorted(runs.items()))}, indent=2),
                             encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", type=Path, default=ROOT / "data" / "author_replication_data")
    ap.add_argument("--results-dir", type=Path, default=ROOT / "results")
    ap.add_argument("--analysis", choices=["all", "firm", "citations", "figures", "patents", "panelrobust"], default="all")
    ap.add_argument("--fx-exact-date", action="store_true",
                    help="Reproduce R's exact-date exchange-rate join (drops weekend quarter-ends).")
    ap.add_argument("--separate-match-covariates", action="store_true",
                    help="Match on lagged at, rev and lt separately instead of R's effective at and rev+lt.")
    ap.add_argument("--rebuild-panel", action="store_true", help="Ignore the prepared firm panel cache.")
    args = ap.parse_args()
    args.results_dir.mkdir(parents=True, exist_ok=True)
    metadata_path = args.results_dir / "run_metadata.json"
    firm_settings = {"fx_exact_date": args.fx_exact_date,
                     "r_match_covariates": not args.separate_match_covariates}
    selected = (["patents", "firm", "citations", "figures"] if args.analysis == "all" else [args.analysis])
    for analysis in selected:
        settings = {}
        if analysis in ("firm", "panelrobust"):
            firm = load_firm_panel(args.data_dir, args.results_dir, args.fx_exact_date, args.rebuild_panel)
            if analysis == "firm":
                model_ddd(firm, args.results_dir)
            # "firm" includes the sensitivity checks; "panelrobust" runs only them.
            firm_event_studies(firm, args.results_dir, r_covariates=not args.separate_match_covariates)
            settings = firm_settings
        elif analysis == "patents":
            patent_sector_tables(args.data_dir, args.results_dir)
        elif analysis == "citations":
            citation_models(args.data_dir, args.results_dir)
        elif analysis == "figures":
            visualize(args.data_dir, args.results_dir)
        record_completion(metadata_path, args.data_dir, analysis, settings)
    logging.info("Finished. Results: %s", args.results_dir)


if __name__ == "__main__":
    main()
