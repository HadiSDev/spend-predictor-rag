"""Orchestrate plan -> enrich -> render -> ERP -> fixture bundle. CLI entry point."""
from __future__ import annotations

import argparse
import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

from ..rag.indexer import load_accounts
from .bundle import append_manifest, category_from_account, write_labels
from .content import enrich_descriptions
from .erp import build_journal
from .render.renderer import render_invoice_pdf
from .sampler import sample_plans


def generate_dataset(
    n: int, seed: int, out_dir: Path, *,
    enrich_fn=enrich_descriptions, render_fn=render_invoice_pdf, cryptic: bool = False,
) -> int:
    """Generate `n` fixture bundles under out_dir. Returns the number written."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = out_dir / "manifest.jsonl"
    accounts = load_accounts()
    plans = sample_plans(n, seed, accounts=accounts)

    written = 0
    for i, plan in enumerate(plans):
        fixture_id = f"{i:05d}"
        fdir = out_dir / fixture_id
        try:
            invoice = enrich_fn(plan, cryptic=cryptic)
            fdir.mkdir(parents=True, exist_ok=True)
            render_fn(invoice, fdir / "invoice.pdf", buyer_name=plan.buyer.name,
                      template_name=("classic" if i % 2 else "modern"))
            category = category_from_account(plan.account, plan.level1)
            journal = build_journal(invoice, plan.account["account_code"],
                                    plan.account["account_name"])
            write_labels(fdir, invoice=invoice, category=category,
                         buyer=plan.buyer, journal=journal)
            append_manifest(manifest, {
                "id": fixture_id, "account_code": plan.account["account_code"],
                "level1": plan.level1, "vat_regime": plan.vat_regime,
                "buyer": plan.buyer.name,
            })
            written += 1
        except Exception as exc:  # noqa: BLE001 - skip the item, keep the batch going
            logger.warning("skip %s: %s", fixture_id, exc)
            shutil.rmtree(fdir, ignore_errors=True)
    print(f"Wrote {written}/{n} fixtures to {out_dir}")
    return written


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate synthetic invoice fixtures.")
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", type=Path, default=Path("data/synthetic"))
    ap.add_argument("--cryptic", action="store_true",
                    help="ask the model for terse/cryptic line-item descriptions (only with --live)")
    ap.add_argument("--live", action="store_true",
                    help="use the local LLM to write descriptions (requires vLLM + curator)")
    args = ap.parse_args()

    if args.cryptic and not args.live:
        logger.warning("--cryptic only affects the LLM path (--live); it is ignored without --live")

    if args.live:
        from .content import _default_generate  # noqa: PLC0415

        def _live_enrich(plan, *, cryptic: bool = False):
            return enrich_descriptions(plan, cryptic=cryptic, generate_fn=_default_generate)

        enrich_fn = _live_enrich
    else:
        enrich_fn = enrich_descriptions  # default: deterministic catalog descriptions

    generate_dataset(args.n, args.seed, args.out, enrich_fn=enrich_fn, cryptic=args.cryptic)


if __name__ == "__main__":
    main()
