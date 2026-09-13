# Anomaly Detection in Time Series

A project for detecting anomalies in time series data, covering statistical
methods, classical machine learning, and deep learning approaches.

## Project layout

```
data/                          # Raw and processed datasets (git-ignored)
notebooks/                     # Exploratory analysis notebooks
models/                        # Trained model artifacts (git-ignored)
src/anomaly_detection/
    data/                      # Data loading and preprocessing
    models/                    # Anomaly detection methods
tests/                         # Unit and integration tests
```

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Testing

```bash
pytest
```

## Roadmap

See [TODO.md](TODO.md) for the planned methods (statistical thresholding,
Isolation Forest / One-Class SVM / LOF, ARIMA/SARIMA residual analysis,
LSTM/Transformer autoencoders) and evaluation approach.
