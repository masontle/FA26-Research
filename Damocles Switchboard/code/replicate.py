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
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PAT_ALL = {"211111", "221112", "324110", "325110", "331312", "334413", "454111", "517110", "517210", "518210", "519130", "524113", "541612"}
PAT_HIGH = {"454111", "517110", "518210", "519130", "524113", "541612"}
NAICS_ALT = {"454111", "454112", "511110", "511120", "511130", "511140", "511191", "511199", "515112", "517110", "517210", "517919", "519130", "541511", "561422"}
PATENT_CLASSES = {"702", "703", "700", "706", "715", "707", "710", "717", "709", "704", "341", "705", "701"}
YEARS = set(range(2011, 2021))
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def files_under(root: Path, name: str) -> list[Path]:
    found = [p for p in root.rglob(name) if p.is_file()]
    if not found:
        raise FileNotFoundError(f"Could not find {name} under {root}")
    return found


def one_file(root: Path, name: str) -> Path:
    found = files_under(root, name)
    if len(found) > 1:
        # File names may be repeated in country-labelled subdirectories; callers
        # that need a unique file should pass a specific path.
        raise ValueError(f"Expected one {name}; found {len(found)}")
    return found[0]


def read_firm_data(root: Path) -> pd.DataFrame:
    """Convert Compustat extracts to a quarterly, currency-adjusted panel."""
    fx = pd.read_csv(one_file(root, "exchange_rates.csv"), low_memory=False)
    fx_date = fx.iloc[:, 0].astype(str)
    def col(fragment: str) -> pd.Series:
        norm = lambda s: re.sub(r"[^A-Z]", "", s.upper())
        c = next((x for x in fx.columns if norm(fragment) in norm(x)), None)
        if c is None:
            raise KeyError(f"Exchange rate column containing {fragment!r} not found")
        return pd.to_numeric(fx[c], errors="coerce")
    fx = pd.DataFrame({"date": pd.to_datetime(fx_date, errors="coerce"),
                       "ca": col("CANADA"), "cn": col("CHINA"),
                       "sg": col("SINGAPORE"), "hk": col("HONG KONG")}).iloc[5:12073]
    parts = []
    for filename, country in (("ss.csv", "CHN"), ("na.csv", "USA"), ("hk8719.csv", "HK")):
        logging.info("Reading %s", filename)
        needed = ["gvkey", "loc", "naics", "datadate", "curcdq", "revtq", "atq", "ltq", "cheq", "cstkq", "lseq", "seqq"]
        d = pd.read_csv(one_file(root, filename), usecols=needed, low_memory=False)
        d["date"] = pd.to_datetime(d["datadate"].astype(str), format="%Y%m%d", errors="coerce")
        d = d.merge(fx, on="date", how="inner")
        rate = {"CHN": "cn", "USA": "ca", "HK": None}[country]
        cur = d["curcdq"].astype(str)
        def usd(var: str) -> pd.Series:
            v = pd.to_numeric(d[var], errors="coerce")
            if country == "HK":
                divisor = np.select([cur.eq("CNY"), cur.eq("HKD")],
                                    [d.cn, d.hk], default=d.sg)
                return pd.Series(np.where(cur.eq("USD"), v, v / divisor), index=d.index)
            return pd.Series(np.where(cur.eq("USD"), v, v / d[rate]), index=d.index)
        q = pd.DataFrame({"date": d.date, "gvkey": d.gvkey.astype(str),
                          "loc": d["loc"].astype(str), "naics": d.naics.astype(str).str.replace(r"\.0$", "", regex=True),
                          "rev": usd("revtq"), "at": usd("atq"), "lt": usd("ltq"),
                          "che": usd("cheq"), "cstk": usd("cstkq"), "lse": usd("lseq"), "seq": usd("seqq")})
        parts.append(q)
    d = pd.concat(parts, ignore_index=True)
    d = d.loc[(d.date > "1999-12-31") & d["loc"].isin(["CHN", "USA"])]
    d = d.loc[d.date.dt.strftime("%m-%d").isin(["03-31", "06-30", "09-30", "12-31"])]
    d = d.loc[~((d["loc"] == "CHN") & (d.date == "2010-12-31"))].copy()
    d = d.drop_duplicates(["date", "gvkey"])
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


def model_ddd(d: pd.DataFrame, out: Path) -> None:
    import statsmodels.formula.api as smf
    d = d.loc[d.date > "2010-12-31"].dropna(subset=["naics"]).copy()
    d["china"] = (d["loc"] == "CHN").astype(int)
    rows = []
    for uptake in ["treat", "treat_high", "treat_alt"]:
        for saturated in [False, True]:
            rhs = f"{uptake} * china * post"
            if saturated:
                rhs += " + logat + loglt"
            cols = ["logrev", uptake, "china", "post", "year", "naics"] + (["logat", "loglt"] if saturated else [])
            sample = d.dropna(subset=cols)
            model = smf.ols("logrev ~ " + rhs + " + C(year)", data=sample).fit(
                cov_type="cluster", cov_kwds={"groups": sample.naics, "use_correction": True})
            term = f"{uptake}:china:post"
            rows.append({"model": f"{'saturated' if saturated else 'naive'}_{uptake}",
                         "term": term, "estimate": model.params.get(term, np.nan),
                         "std_error": model.bse.get(term, np.nan), "p_value": model.pvalues.get(term, np.nan),
                         "n": int(model.nobs)})
    pd.DataFrame(rows).to_csv(out / "firm_ddd.csv", index=False)
    # 2013 pre-shock descriptions and Welch tests (Tables A3–A5).
    q = d.loc[(d["loc"] == "CHN") & (d.year == "2013")].copy()
    q = q.loc[q.date.dt.strftime("%m-%d").isin(["03-31", "06-30", "09-30", "12-31"])]
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
    d = patents.merge(stock09, left_on="permno", right_on="PERMNO", how="outer")
    classes = {"702", "703", "700", "706", "715", "707", "710", "717", "709", "704", "341", "705", "701"}
    d["class3"] = d["class"].str.replace(r"\.0$", "", regex=True).str.strip()
    d["data_patent"] = d.class3.isin(classes)
    d["naics"] = d.NAICS.str.replace(r"\.0$", "", regex=True).str.strip()
    data_counts = d.loc[d.data_patent & d.naics.notna()].groupby("naics").size().rename("data_patents")
    sector_codes = data_counts.index
    all_counts = d.loc[d.naics.isin(sector_codes)].groupby("naics").size().rename("all_patents")
    table = pd.concat([data_counts, all_counts], axis=1).fillna(0).reset_index(names="NAICS")
    table["share_data_patents"] = table.data_patents / table.all_patents.replace(0, np.nan)
    table.to_csv(out / "table_A1_patent_data_intensity.csv", index=False)
    alt = sorted(NAICS_ALT)
    pd.DataFrame({"NAICS": alt, "internet_keyword_sector": 1}).to_csv(out / "table_A2_internet_keyword_sectors.csv", index=False)


def panel_match_approx(d: pd.DataFrame, out: Path) -> None:
    """Approximate PanelMatch ATT/event study with nearest Mahalanobis sets.

    Constructs each firm's ten-quarter pre-shock history, matches treated firms
    to up to 4,003 controls, and reports post-period differences in log revenue.
    The R package's exact unit-period risk sets and bootstrap are not reproduced.
    """
    from scipy.spatial.distance import cdist
    cn = d.loc[d["loc"] == "CHN"].copy()
    cn["q"] = cn.date.dt.to_period("Q")
    panel = cn.pivot_table(index="gvkey", columns="q", values=["logrev_panel", "logat_panel", "loglt_panel"], aggfunc="first")
    quarter_cols = sorted([q for q in cn.q.unique() if q <= pd.Period("2014Q1")])[-10:]
    features = []
    for var in ["logat_panel", "logrev_panel", "loglt_panel"]:
        for q in quarter_cols:
            features.append((var, q))
    hist = panel.reindex(columns=pd.MultiIndex.from_tuples(features))
    hist.columns = [f"{v}_{q}" for v, q in features]
    hist = hist.replace([np.inf, -np.inf], np.nan)
    active = cn.drop_duplicates("gvkey").set_index("gvkey")
    treat = active.naics.isin(PAT_ALL)
    treated_ids = hist.index.intersection(active.index[treat])
    control_ids = hist.index.intersection(active.index[~active.naics.isin(PAT_ALL)])
    x1, x0 = hist.loc[treated_ids], hist.loc[control_ids]
    # Pairwise missingness is handled by median imputation, followed by a
    # regularized inverse covariance Mahalanobis metric.
    med = pd.concat([x1, x0]).median()
    x1, x0 = x1.fillna(med), x0.fillna(med)
    cov = np.cov(pd.concat([x1, x0]).to_numpy(), rowvar=False)
    inv = np.linalg.pinv(cov + np.eye(cov.shape[0]) * 1e-5)
    dist = cdist(x1.to_numpy(), x0.to_numpy(), metric="mahalanobis", VI=inv)
    nearest = np.argsort(dist, axis=1)[:, :min(4003, len(control_ids))]
    weight = 1.0 / np.maximum(1, nearest.shape[1])
    baseline_q = pd.Period("2014Q1")
    events = []
    for lead in range(0, 11):
        target = baseline_q + lead + 1  # first post quarter is 2014Q2
        y = panel["logrev_panel"]
        if baseline_q not in y.columns or target not in y.columns:
            continue
        tdelta = y.reindex(treated_ids)[target] - y.reindex(treated_ids)[baseline_q]
        cdelta = y.reindex(control_ids)[target] - y.reindex(control_ids)[baseline_q]
        estimates = []
        for i, tid in enumerate(treated_ids):
            js = nearest[i]
            vals = cdelta.iloc[js].dropna()
            tv = tdelta.loc[tid]
            if pd.notna(tv) and len(vals):
                estimates.append(tv - vals.mean())
        events.append({"quarter_after_shock": lead, "estimate_log_points": np.mean(estimates) if estimates else np.nan,
                       "approx_revenue_pct": (np.exp(np.mean(estimates)) - 1) * 100 if estimates else np.nan,
                       "treated_firms": len(estimates), "matched_controls_per_firm": nearest.shape[1]})
    event_frame = pd.DataFrame(events)
    event_frame.to_csv(out / "firm_panelmatch_approx.csv", index=False)
    if len(event_frame):
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.plot(event_frame.quarter_after_shock, event_frame.estimate_log_points, marker="o")
        ax.axhline(0, color="black", linewidth=.8)
        ax.set(xlabel="Quarters after 2014 shock", ylabel="Estimated log revenue effect",
               title="Firm revenue event study (Python match approximation)")
        fig.tight_layout(); fig.savefig(out / "figure4_firm_event_study_approx.png", dpi=200); plt.close(fig)


def panel_robustness_approx(d: pd.DataFrame, out: Path) -> None:
    """Python sensitivity checks corresponding to the supplementary PanelMatch runs.

    Uses nearest Mahalanobis firm-level histories in place of PanelMatch's
    period-specific matched risk sets. Estimates are descriptive approximations.
    """
    from scipy.spatial.distance import cdist
    import matplotlib.pyplot as plt
    cn = d.loc[d["loc"] == "CHN"].copy()
    cn["q"] = cn.date.dt.to_period("Q")
    panel = cn.pivot_table(index="gvkey", columns="q", values=["logrev_panel", "logat_panel", "loglt_panel"], aggfunc="first")
    firm = cn.sort_values("date").drop_duplicates("gvkey").set_index("gvkey")
    specs = [("main_4003", PAT_ALL, "2014Q1", 4003),
             ("main_20", PAT_ALL, "2014Q1", 20),
             ("high_intensity", PAT_HIGH, "2014Q1", 4003),
             ("alternative_naics", NAICS_ALT, "2014Q1", 4003),
             ("false_date_2008", PAT_ALL, "2008Q2", 4003),
             ("pretrend_2012", PAT_ALL, "2012Q1", 4003)]
    results = []
    rng = np.random.default_rng(2024)

    def run_spec(name: str, treated_ids: pd.Index, control_ids: pd.Index, baseline: pd.Period, max_matches: int, leads=range(0, 11)):
        hist_q = sorted([q for q in panel["logrev_panel"].columns if q <= baseline])[-10:]
        features = [(v, q) for v in ("logat_panel", "logrev_panel", "loglt_panel") for q in hist_q]
        hist = panel.reindex(columns=pd.MultiIndex.from_tuples(features))
        hist.columns = [f"{v}_{q}" for v, q in features]
        x1, x0 = hist.reindex(treated_ids), hist.reindex(control_ids)
        med = pd.concat([x1, x0]).median()
        x1, x0 = x1.fillna(med), x0.fillna(med)
        if not len(x1) or not len(x0):
            return []
        vals = pd.concat([x1, x0]).to_numpy()
        cov = np.cov(vals, rowvar=False)
        inv = np.linalg.pinv(cov + np.eye(cov.shape[0]) * 1e-5)
        dist = cdist(x1.to_numpy(), x0.to_numpy(), metric="mahalanobis", VI=inv)
        nearest = np.argsort(dist, axis=1)[:, :min(max_matches, len(control_ids))]
        y = panel["logrev_panel"]
        rows = []
        for lead in leads:
            target = baseline + lead + 1
            if baseline not in y.columns or target not in y.columns:
                continue
            td = y.reindex(treated_ids)[target] - y.reindex(treated_ids)[baseline]
            cd = y.reindex(control_ids)[target] - y.reindex(control_ids)[baseline]
            effects = []
            for i, tid in enumerate(treated_ids):
                cv = cd.iloc[nearest[i]].dropna()
                if pd.notna(td.loc[tid]) and len(cv):
                    effects.append(td.loc[tid] - cv.mean())
            est = float(np.mean(effects)) if effects else np.nan
            rows.append({"specification": name, "quarter_after_date": lead, "estimate_log_points": est,
                         "approx_revenue_pct": (np.exp(est)-1)*100 if np.isfinite(est) else np.nan,
                         "treated_firms": len(effects), "matched_controls_per_firm": nearest.shape[1]})
        return rows

    for name, treat_codes, baseline_str, nmatch in specs:
        treated = firm.index[firm.naics.isin(treat_codes)]
        controls = firm.index[~firm.naics.isin(treat_codes)]
        results.extend(run_spec(name, treated, controls, pd.Period(baseline_str), nmatch))

    # 30 seeded placebo samples of 216 non-treated firms, matching the R script's
    # sample size while keeping this implementation deterministic.
    placebo_pool = firm.index[~firm.naics.isin(PAT_ALL)]
    placebo_treat_n = min(216, len(placebo_pool))
    placebo_rows = []
    for draw in range(30):
        treated = pd.Index(rng.choice(placebo_pool, size=placebo_treat_n, replace=False))
        controls = placebo_pool.difference(treated)
        placebo_rows.extend(run_spec(f"placebo_draw_{draw+1:02d}", treated, controls, pd.Period("2014Q1"), 4003))
    pd.DataFrame(results + placebo_rows).to_csv(out / "firm_panel_robustness_approx.csv", index=False)
    rdf = pd.DataFrame(results)
    if len(rdf):
        fig, ax = plt.subplots(figsize=(10, 6))
        for name, group in rdf.groupby("specification"):
            ax.plot(group.quarter_after_date, group.estimate_log_points, marker="o", label=name)
        ax.axhline(0, color="black", linewidth=.8)
        ax.set(xlabel="Quarters after assigned date", ylabel="Estimated log revenue effect",
               title="Firm event study sensitivity checks (Python approximation)")
        ax.legend(fontsize=8, ncol=2); fig.tight_layout()
        fig.savefig(out / "figure_A2_A4_robustness_approx.png", dpi=200); plt.close(fig)
    if len(placebo_rows):
        pdf = pd.DataFrame(placebo_rows)
        pdf.groupby("quarter_after_date").agg(mean_estimate=("estimate_log_points", "mean"),
            sd_across_draws=("estimate_log_points", "std"), draws=("estimate_log_points", "count")).reset_index().to_csv(
                out / "firm_placebo_30_draw_summary.csv", index=False)


def read_citations(root: Path, folder: str) -> pd.DataFrame:
    """Stream WoS text extracts, retaining 2011–20 records and needed columns."""
    base_dirs = [p for p in root.rglob(folder) if p.is_dir()]
    if not base_dirs:
        raise FileNotFoundError(f"Could not find {folder} directory under {root}")
    frames = []
    for base in base_dirs:
        for p in base.glob("*.txt"):
            logging.info("Reading citation extract %s", p.name)
            try:
                chunks = pd.read_csv(p, sep="\t", dtype=str, usecols=["PY", "TC", "SO", "AU"], chunksize=250_000, low_memory=False,
                                     on_bad_lines="skip", encoding_errors="replace")
                for chunk in chunks:
                    chunk.columns = [c.strip().lstrip("\ufeff") for c in chunk.columns]
                    if "PY" not in chunk or "TC" not in chunk:
                        continue
                    chunk["PY"] = pd.to_numeric(chunk.PY, errors="coerce")
                    chunk = chunk.loc[chunk.PY.isin(YEARS)].copy()
                    if len(chunk):
                        chunk["authors"] = chunk.AU.fillna("").str.count(";") + 1
                        chunk["field"] = p.stem
                        frames.append(chunk[["PY", "TC", "SO", "authors", "field"]])
            except Exception as e:
                logging.warning("Skipping unreadable file %s: %s", p.name, e)
    if not frames:
        raise ValueError(f"No article rows for 2011–2020 found in {folder}")
    return pd.concat(frames, ignore_index=True)


def read_rpp(root: Path) -> pd.DataFrame:
    import openpyxl  # pandas engine
    vals = []
    for p in root.rglob("*.xls"):
        try:
            frame = pd.read_excel(p, engine="xlrd")
        except Exception as e:
            logging.warning("RPP workbook %s could not be read: %s", p.name, e)
            continue
        frame["field"] = p.stem
        vals.append(frame)
    if not vals:
        raise FileNotFoundError("Could not read RPP2010 .xls workbooks (install xlrd)")
    raw = pd.concat(vals, ignore_index=True)
    ref = pd.to_numeric(raw["Cited Reference Count"], errors="coerce")
    pages = pd.to_numeric(raw["Number of Pages"], errors="coerce")
    return pd.DataFrame({"field": raw["Research Areas"], "rp_raw": ref, "pages": pages}).groupby("field", as_index=False).sum(min_count=1).assign(rp=lambda x: x.rp_raw / x.pages)


def nb2_fe_fit(data: pd.DataFrame, rhs: str, fixed_effects: list[str], cluster: str) -> dict:
    """NB2 MLE with sparse categorical fixed effects and cluster-robust slope SEs."""
    from scipy import sparse
    from scipy.optimize import minimize
    from scipy.special import digamma, gammaln

    left, right = [x.strip() for x in rhs.split("*")]
    numeric_names = [left, right, f"{left}:{right}", "age", "authors"]
    numeric = {}
    for name in [left, right, "age", "authors"]:
        numeric[name] = pd.to_numeric(data[name], errors="coerce").to_numpy(float)
    numeric[f"{left}:{right}"] = numeric[left] * numeric[right]
    z = np.column_stack([numeric[n] for n in numeric_names])
    y = pd.to_numeric(data.TC, errors="coerce").to_numpy(float)
    n = len(data)
    blocks, groups, init = [], [], []
    fe_names = []
    for idx, name in enumerate(fixed_effects):
        codes, levels = pd.factorize(data[name].astype(str), sort=True)
        groups.append(codes)
        width = len(levels)
        block = sparse.csr_matrix((np.ones(n), (np.arange(n), codes)), shape=(n, width))
        if idx > 0:
            block = block[:, 1:]
        blocks.append(block)
        fe_names.append(name)
        if idx == 0:
            sums = np.bincount(codes, weights=y, minlength=width)
            counts = np.bincount(codes, minlength=width)
            init.extend(np.log((sums + .1) / np.maximum(counts, 1)))
        else:
            init.extend(np.zeros(max(0, width - 1)))
    X = sparse.hstack(blocks + [sparse.csr_matrix(z)], format="csr")
    p_fe = X.shape[1] - len(numeric_names)
    init = np.asarray(init + [0.] * len(numeric_names) + [math.log(.5)], dtype=float)
    log_y_factor = gammaln(y + 1)

    def objective(params):
        beta, theta = params[:-1], params[-1]
        alpha = math.exp(float(np.clip(theta, -12, 8)))
        r = 1.0 / alpha
        eta = np.clip(np.asarray(X @ beta).ravel(), -30, 30)
        mu = np.exp(eta)
        logden = np.logaddexp(math.log(r), eta)
        ll = (gammaln(y + r) - gammaln(r) - log_y_factor
              + r * (math.log(r) - logden) + y * (eta - logden))
        s_eta = (y - mu) / (1.0 + alpha * mu)
        dldr = (digamma(y + r) - digamma(r) + math.log(r) + 1.0 - logden
                - (y + r) / (r + mu))
        grad = np.empty_like(params)
        grad[:-1] = -np.asarray(X.T @ s_eta).ravel()
        grad[-1] = r * np.sum(dldr)
        return -float(np.sum(ll)), grad

    opt = minimize(objective, init, method="L-BFGS-B", jac=True,
                   bounds=[(None, None)] * (len(init) - 1) + [(-12, 8)],
                   options={"maxiter": 150, "ftol": 1e-9, "maxls": 30})
    beta, theta = opt.x[:-1], opt.x[-1]
    alpha = math.exp(float(np.clip(theta, -12, 8)))
    eta = np.clip(np.asarray(X @ beta).ravel(), -30, 30)
    mu = np.exp(eta)
    weight = mu / (1 + alpha * mu)
    score = (y - mu) / (1 + alpha * mu)
    # Partial out fixed effects from the small set of slope regressors.
    zr = z.copy()
    for _ in range(100):
        max_change = 0.0
        for codes in groups:
            denom = np.bincount(codes, weights=weight)
            for j in range(zr.shape[1]):
                num = np.bincount(codes, weights=weight * zr[:, j])
                mean = num / np.maximum(denom, 1e-20)
                change = mean[codes]
                zr[:, j] -= change
                max_change = max(max_change, float(np.nanmax(np.abs(change))))
        if max_change < 1e-8:
            break
    bread = np.linalg.pinv(zr.T @ (weight[:, None] * zr))
    cluster_codes, cluster_levels = pd.factorize(data[cluster].astype(str), sort=True)
    meat_scores = np.zeros((len(cluster_levels), zr.shape[1]))
    for j in range(zr.shape[1]):
        meat_scores[:, j] = np.bincount(cluster_codes, weights=zr[:, j] * score, minlength=len(cluster_levels))
    meat = meat_scores.T @ meat_scores
    correction = (len(cluster_levels) / max(1, len(cluster_levels) - 1)) * ((n - 1) / max(1, n - len(init)))
    vcov = bread @ meat @ bread * correction
    ses = np.sqrt(np.maximum(0, np.diag(vcov)))
    from scipy.stats import t as student_t
    dof = max(1, len(cluster_levels) - 1)
    pvals = 2 * student_t.sf(np.abs(beta[-len(numeric_names):] / np.maximum(ses, 1e-20)), dof)
    result = {"converged": bool(opt.success), "alpha": alpha, "n": n,
              "coef": {}, "se": {}, "p": {}, "loglike": -objective(opt.x)[0]}
    slopes = beta[-len(numeric_names):]
    for j, term in enumerate(numeric_names):
        result["coef"][term] = float(slopes[j])
        result["se"][term] = float(ses[j])
        result["p"][term] = float(pvals[j])
    return result


def citation_models(root: Path, out: Path) -> None:
    cn = read_citations(root, "CN0020")
    # CN1120new is distributed as discipline-level CSV extracts.
    cn_new_frames = []
    for base in [p for p in root.rglob("CN1120new") if p.is_dir()]:
        for p in list(base.glob("*.csv")) + list(base.glob("*.tab")):
            try:
                z = pd.read_csv(p, dtype=str, usecols=["PY", "TC", "SO", "AU"], low_memory=False, sep=",")
                z["PY"] = pd.to_numeric(z.PY, errors="coerce")
                z = z.loc[z.PY.isin(YEARS)].copy()
                z["authors"] = z.AU.fillna("").str.count(";") + 1
                z["field"] = p.stem
                cn_new_frames.append(z[["PY", "TC", "SO", "authors", "field"]])
            except Exception as e:
                logging.warning("Skipping CN1120new file %s: %s", p.name, e)
    if cn_new_frames:
        cn = pd.concat([cn, *cn_new_frames], ignore_index=True)
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
    d["log_rp"] = np.log(d.rp)
    cn_rp = d.loc[d.china == 1, "log_rp"]
    median_rp, mu, sd = cn_rp.median(), cn_rp.mean(), cn_rp.std()
    d["high_knowledge"] = (d.log_rp >= median_rp).astype(int)
    d["extreme_knowledge"] = np.select([d.log_rp < mu - sd, d.log_rp > mu + sd], [0, 1], default=np.nan)
    d["field_year"] = d.field.astype(str) + "_" + d.PY.astype(str)
    # H2 models use China only; cross-country DiD keeps US and China.
    cn = d.loc[d.china == 1].copy()
    cn50 = cn.loc[cn.TC > cn.groupby("field_year").TC.transform("median")].copy()
    records = []
    def fit_count(df, family, rhs, name, fe):
        needed = ["TC", "age", "authors", "SO", "field", "post"] + re.findall(r"[A-Za-z_]+", rhs)
        sample = df.dropna(subset=list(set(needed)))
        if family == "nb":
            fitted = nb2_fe_fit(sample, rhs, [part.strip() for part in fe.split("+")], "field")
            estimates, errors, p_values = fitted["coef"], fitted["se"], fitted["p"]
            fe_status = "full_fixed_effects" if fitted["converged"] else "nb2_did_not_converge"
        else:
            import pyfixest as pf
            formula = f"TC ~ {rhs} + age + authors | {fe}"
            try:
                model = pf.fepois(formula, data=sample, vcov={"CRV1": "field"}, copy_data=False, store_data=False)
                fe_status = "full_fixed_effects"
            except ValueError as exc:
                if "+" not in fe:
                    raise
                # The two-way absorbed Poisson can fail to converge on this
                # sparse publisher/journal structure. Keep the journal FE and
                # report the degraded fallback explicitly in the CSV.
                model = pf.fepois(f"TC ~ {rhs} + age + authors | SO", data=sample,
                                  vcov={"CRV1": "field"}, copy_data=False, store_data=False)
                fe_status = f"SO_only_fallback: {exc}"
            tab = model.tidy()
            estimates = tab["Estimate"].to_dict()
            errors = tab["Std. Error"].to_dict()
            pcol = next((c for c in tab.columns if "Pr(>" in c), None)
            p_values = tab[pcol].to_dict() if pcol else {}
        for term, estimate in estimates.items():
            records.append({"model": name, "term": term, "estimate": estimate,
                            "std_error": errors.get(term, np.nan), "p_value": p_values.get(term, np.nan),
                            "incidence_rate_ratio": np.exp(estimate), "n": fitted["n"] if family == "nb" else len(sample),
                            "converged": fe_status, "nb2_alpha": fitted["alpha"] if family == "nb" else np.nan})
    for fam in ["nb", "poisson"]:
        for label, frame in [("all", cn), ("top_half", cn50)]:
            fit_count(frame, fam, "post * log_rp", f"{fam}_{label}_continuous", "SO")
        for var in ["high_knowledge", "extreme_knowledge"]:
            fit_count(cn.dropna(subset=[var]), fam, f"post * {var}", f"{fam}_all_{var}", "SO")
        fit_count(d, fam, "post * china", f"{fam}_china_us_did", "field + SO")
    # Pre-treatment trend check matching Table A9.
    trend = cn.loc[cn.PY < 2015].copy()
    trend["logtc"] = np.log(trend.TC + .1)
    import pyfixest as pf
    trend = trend.dropna(subset=["logtc", "PY", "high_knowledge", "age", "authors", "SO", "field"])
    m = pf.feols("logtc ~ PY * high_knowledge + age + authors | SO", data=trend,
                  vcov={"CRV1": "field"}, copy_data=False, store_data=False)
    trend_tab = m.tidy()
    tname = next((x for x in trend_tab.index if set(str(x).split(":")) == {"PY", "high_knowledge"}), None)
    if tname is None:
        tname = "PY:high_knowledge"
    records.append({"model": "pretreatment_trend", "term": tname, "estimate": m.coef().get(tname),
                    "std_error": m.se().get(tname), "p_value": m.pvalue().get(tname), "n": len(trend),
                    "converged": "full_fixed_effects"})
    pd.DataFrame(records).to_csv(out / "citation_models.csv", index=False)
    # Table A6 style field summaries and Fig A6 series.
    cn.groupby("field").agg(n=("TC", "size"), citations_mean=("TC", "mean"), age_mean=("age", "mean"), authors_mean=("authors", "mean")).to_csv(out / "citation_summary_by_field.csv")
    cn.assign(knowledge_group=np.where(cn.high_knowledge.eq(1), "knowledge-intensive", "other")).groupby(["PY", "knowledge_group"]).TC.sum().unstack().to_csv(out / "citation_trends.csv")


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
        ax.set(xlabel="Publication year", ylabel="Logged total citations", title="Citation trends by knowledge intensity")
        ax.legend(); fig.tight_layout(); fig.savefig(out / "figure_A6_citation_trends.png", dpi=200); plt.close(fig)
    except Exception as e:
        logging.warning("Figure A6 skipped: citation_trends.csv unavailable (%s)", e)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", type=Path, default=ROOT / "data" / "author_replication_data")
    ap.add_argument("--results-dir", type=Path, default=ROOT / "results")
    ap.add_argument("--analysis", choices=["all", "firm", "citations", "figures", "patents", "panelrobust"], default="all")
    args = ap.parse_args()
    args.results_dir.mkdir(parents=True, exist_ok=True)
    metadata_path = args.results_dir / "run_metadata.json"
    prior = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}
    completed = set(prior.get("analyses_completed", []))
    if args.analysis == "all":
        completed.update(["firm", "citations", "figures", "patents", "panelrobust"])
    else:
        completed.add(args.analysis)
    manifest = {"data_dir": str(args.data_dir), "analysis_requested": args.analysis,
                "analyses_completed": sorted(completed)}
    metadata_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    if args.analysis in ("all", "firm"):
        cache = args.results_dir / "firm_panel_prepared.parquet"
        if cache.exists():
            firm = pd.read_parquet(cache)
            logging.info("Using prepared firm panel cache %s", cache)
        else:
            firm = read_firm_data(args.data_dir)
            firm.to_parquet(cache, index=False)
        model_ddd(firm, args.results_dir)
        panel_match_approx(firm, args.results_dir)
        panel_robustness_approx(firm, args.results_dir)
        patent_sector_tables(args.data_dir, args.results_dir)
    if args.analysis == "panelrobust":
        cache = args.results_dir / "firm_panel_prepared.parquet"
        firm = pd.read_parquet(cache) if cache.exists() else read_firm_data(args.data_dir)
        panel_robustness_approx(firm, args.results_dir)
    if args.analysis == "patents":
        patent_sector_tables(args.data_dir, args.results_dir)
    if args.analysis in ("all", "citations"):
        citation_models(args.data_dir, args.results_dir)
    if args.analysis in ("all", "figures"):
        visualize(args.data_dir, args.results_dir)
    logging.info("Finished. Results: %s", args.results_dir)


if __name__ == "__main__":
    main()
