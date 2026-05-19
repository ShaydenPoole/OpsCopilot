# Data Pipeline

One-shot scripts that build the project's two data artifacts:

1. **`flights.duckdb`** — 2 years × top 50 US airports of BTS On-Time Performance data. Lands in U2.
2. **`corpus_index.lance/`** — chunked + embedded FAA AIM corpus. Lands in U3.

Both artifacts are written to a Modal Volume (`aviation-copilot-data`) in production and to local `data/` for development. The orchestrator is `hydrate_volume.py` (U2/U3).

## Layout (after U2/U3 land)

```
data_pipeline/
├── download_bts_otp.py        # download + filter BTS CSV monthly archives
├── build_flight_duckdb.py     # transform CSVs to DuckDB
├── download_faa_aim.py        # fetch FAA AIM HTML
├── build_corpus_index.py      # chunk + embed → LanceDB
├── hydrate_volume.py          # Modal function — writes both artifacts to Volume
└── probe_queries.jsonl        # 10 labeled retrieval probes (U3 verification)
```

## Running locally

```bash
cd backend
uv run python ../data_pipeline/download_bts_otp.py --years 2 --top-airports 50
uv run python ../data_pipeline/build_flight_duckdb.py --out ../data/flights.duckdb
uv run python ../data_pipeline/download_faa_aim.py --out ../data/faa_aim/
uv run python ../data_pipeline/build_corpus_index.py --in ../data/faa_aim/ --out ../data/corpus_index.lance/
```

BTS download is ~5 GB raw. AIM is ~50 MB. End-to-end pipeline takes 15-30 min on a typical laptop.
