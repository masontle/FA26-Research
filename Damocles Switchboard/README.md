# Python replication

Python port of the quantitative workflow for Meicen Sun, “Damocles’s Switchboard: Information Externalities and the Autocratic Logic of Internet Control,” *International Organization* 78(3), 2024.

## Contents

- `code/replicate.py`: Python analysis pipeline.
- `code/source/`: author-provided R scripts, retained for comparison.
- `data/raw/author_replication_data.zip`: the Harvard Dataverse deposit.
- `data/author_replication_data/`: extracted deposit (about 7.5 GB).
- `results/`: generated tables, model outputs, and figures.

The paper and deposit are linked at [Cambridge Core](https://doi.org/10.1017/S0020818324000237) and [Harvard Dataverse, DOI 10.7910/DVN/OX6G1A](https://doi.org/10.7910/DVN/OX6G1A).

## Run

The project includes a local virtual environment. From this folder:

```powershell
.venv\Scripts\Activate.ps1
python code\replicate.py --analysis all
```

Choose `--analysis firm`, `citations`, `figures`, `patents`, or `panelrobust` to run a section alone. To use another copy of the data, pass `--data-dir PATH`. The first firm run also writes `results/firm_panel_prepared.parquet` with a `.json` stamp; later firm runs reuse it only when the stamp (panel version, data directory, exchange-rate mode) matches. Pass `--rebuild-panel` to force a rebuild.

Options for comparing with the R output:

- `--fx-exact-date` reproduces R's exact-date join to the H.10 exchange-rate file. That file has business days only, so the join drops every quarter-end that falls on a weekend (for example 2012Q1, 2013Q2, 2016Q4). By default the script carries each currency's latest quote forward up to 7 days instead.
- `--separate-match-covariates` matches on lagged assets, revenue, and liabilities separately. By default the script copies what the R `covs.formula` actually does: a misplaced parenthesis puts `lag(lt)` inside the `lag(rev)` term, so PanelMatch matches on lagged assets and lagged (revenue + liabilities).

`results/run_metadata.json` records each analysis after it finishes successfully, with its settings and a UTC timestamp.

## Analyses represented

The workflow prepares the Compustat quarterly firm panel, produces 2013 firm summary tables and t-tests, and fits the naive and covariate-adjusted China–US triple-difference specifications under all three sector classifications. It recreates the patent-based sector frequencies and alternative Internet-sector list (Tables A1–A2). The firm event study constructs ten-quarter histories and estimates post-shock revenue changes. It also runs 20-match, high-intensity, alternative-sector, false-date, pretrend-date, and 30-draw placebo sensitivity checks. Figures cover Google/Baidu search substitution, Great Firewall history, references per page, the firm event study, sensitivity checks, and annual citation trends.

For research output, it fits the article-level negative-binomial and Poisson specifications, including the upper-half citation sample and median/extreme knowledge-intensity terms; the China–US difference-in-differences; the pre-shock trend model; field summaries; and annual citation trend data. Tables are written as CSV.

## Interpretation and limits

This is a Python reimplementation, not a coefficient-identical execution of the authors’ R code. The original firm design uses the `PanelMatch` package’s period-specific matched risk sets, matching options (including propensity-score, covariate-balancing, and weighting methods), and bootstrapped standard errors. The Python firm study uses nearest Mahalanobis matches on firm-level histories, without the original period-specific risk sets or bootstrap, so the event-study estimates have **no standard errors**. Time is indexed by observed quarter-ends, as R's `Date` index is. Each specification's first treated quarter is the first quarter after the R cutoff date (2014-05-31, 2008-06-29, or 2012-02-28), and the baseline is the quarter before it. Firms with no observed pre-period history are excluded from matching, and the remaining missing values are median-imputed. As in R, the placebo draws use every firm outside the placebo sample as a potential control. The matching, placebo, false-date, and pretrend sensitivity results are labeled `approx`; the placebo draws are reproducible (seed 2024). The authors’ propensity-score, covariate-balancing, and propensity-weighting sensitivity estimators are not included.

The DDD models use every Chinese and US reporting date after 2010, as R's `dnew` does. The matching analysis keeps only the four calendar quarter-ends.

For count models, Poisson estimates use PyFixest with absorbed journal fixed effects. The NB2 models use a profiled maximum-likelihood fit (`nb2_fe_fit`). Each journal's fixed effect solves its own score equation exactly; the slopes take line-searched Newton steps; alpha is updated by 1-D maximization. Journals whose citations are all zero are dropped, as `fixest::fenegbin` does. On a subsample, the fit matches statsmodels' NB2 with explicit journal dummies. Note that only 14 of the 5,881 Chinese journals span more than one field, so the main effect of `log_rp` is identified almost entirely from those few journals (in R as well); the `post:log_rp` interaction is identified within journals. In the China–US models, the 31 field fixed effects enter as explicit indicators, which gives the same slopes as absorbing them and avoids the two-way demeaning failure. Standard errors are clustered by discipline. Check each row's `converged` field in `citation_models.csv` before interpreting a coefficient. These estimator and inference differences can change results.

The paper’s interview-based state-strategy evidence is qualitative and the deposit has no interview transcripts or computational coding file, so it cannot be statistically re-estimated here. Several supplementary matching algorithms (propensity-score, covariate-balancing, and propensity weighting) are also not reproduced; the available nearest-Mahalanobis approximations are documented above.

## Data terms

The deposit includes licensed Compustat, CRSP, and Web of Science extracts along with code and derivative data. Keep the data local for personal research, and consult the Dataverse metadata and source-provider terms before sharing the archive or derived records.
