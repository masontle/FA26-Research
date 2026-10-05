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

Choose `--analysis firm`, `citations`, `figures`, `patents`, or `panelrobust` to run a section alone. To use another copy of the data, pass `--data-dir PATH`. The first firm run also writes `results/firm_panel_prepared.parquet`, which later firm runs reuse.

## Analyses represented

The workflow prepares the Compustat quarterly firm panel, produces 2013 firm summary tables and t-tests, and fits the naive and covariate-adjusted China–US triple-difference specifications under all three sector classifications. It recreates the patent-based sector frequencies and alternative Internet-sector list (Tables A1–A2). The firm event study constructs ten-quarter histories and estimates post-shock revenue changes. It also runs 20-match, high-intensity, alternative-sector, false-date, pretrend-date, and 30-draw placebo sensitivity checks. Figures cover Google/Baidu search substitution, Great Firewall history, references per page, the firm event study, sensitivity checks, and annual citation trends.

For research output, it fits the article-level negative-binomial and Poisson specifications, including the upper-half citation sample and median/extreme knowledge-intensity terms; the China–US difference-in-differences; the pre-shock trend model; field summaries; and annual citation trend data. Tables are written as CSV.

## Interpretation and limits

This is a Python reimplementation, not a coefficient-identical execution of the authors’ R code. The original firm design uses the `PanelMatch` package’s period-specific matched risk sets, matching options (including propensity-score, covariate-balancing, and weighting methods), and bootstrapped standard errors. The Python firm study uses nearest Mahalanobis matches on firm-level histories, without the original period-specific risk sets or bootstrap. The matching, placebo, false-date, and pretrend sensitivity results are therefore labeled `approx`; the placebo draws are reproducible (seed 2024). The authors’ propensity-score, covariate-balancing, and propensity-weighting sensitivity estimators are not included. For count models, Poisson estimates use PyFixest with absorbed fixed effects. The NB2 models use a sparse maximum-likelihood implementation with journal fixed effects and discipline-clustered sandwich errors; inspect each row’s `converged` field in `citation_models.csv` before interpreting a coefficient. These estimator and inference differences can change results.

The paper’s interview-based state-strategy evidence is qualitative and the deposit has no interview transcripts or computational coding file, so it cannot be statistically re-estimated here. Several supplementary matching algorithms (propensity-score, covariate-balancing, and propensity weighting) are also not reproduced; the available nearest-Mahalanobis approximations are documented above.

## Data terms

The deposit includes licensed Compustat, CRSP, and Web of Science extracts along with code and derivative data. Keep the data local for personal research, and consult the Dataverse metadata and source-provider terms before sharing the archive or derived records.
