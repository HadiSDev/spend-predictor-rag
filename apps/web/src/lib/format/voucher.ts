/** How a voucher is named on screen, and whether that name is its ERP number. */
export interface VoucherLabel {
  text: string
  numbered: boolean
}

/** The ERP's voucher number, never the voucher id we key on. */
export function voucherLabel(voucher: {
  voucher_id: string | null
  voucher_number?: string | null
}): VoucherLabel {
  if (voucher.voucher_number) {
    return { text: voucher.voucher_number, numbered: true }
  }
  if (voucher.voucher_id === null) {
    return { text: 'No voucher', numbered: false }
  }
  return { text: 'No number', numbered: false }
}
