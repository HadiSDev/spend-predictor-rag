"""Prompt text shared by the text and vision extraction paths."""

TOTALS_BLOCK_CHARGES = (
    "A charge printed in or beside the totals block — shipping, freight, "
    "postage, packing, handling, a payment or card fee, a surcharge — is a line "
    "item like any other, even though it sits outside the line table. Return it "
    "as a line, named as the document names it. Do NOT return a discount, a "
    "rebate or a promotion as a line, and do not return the totals themselves "
    "(subtotal, VAT, total) as lines: those have fields of their own."
)
