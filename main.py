"""Entry point: process every PDF in data/invoices/ into the ledger."""
from spend_predictor.flow import run_all


def main() -> None:
    run_all()


if __name__ == "__main__":
    main()
