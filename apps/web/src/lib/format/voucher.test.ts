import { describe, expect, it } from 'vitest'
import { voucherLabel } from './voucher'

describe('voucherLabel', () => {
  it('shows the ERP voucher number', () => {
    expect(
      voucherLabel({
        voucher_id: 'TIf8g2QFRYmblef0MtxBpA',
        voucher_number: '15',
      }),
    ).toEqual({ text: '15', numbered: true })
  })

  it('never shows the internal voucher id in place of a number', () => {
    expect(
      voucherLabel({
        voucher_id: 'TIf8g2QFRYmblef0MtxBpA',
        voucher_number: null,
      }),
    ).toEqual({ text: 'No number', numbered: false })
  })

  it('says so when the postings have no voucher at all', () => {
    expect(voucherLabel({ voucher_id: null })).toEqual({
      text: 'No voucher',
      numbered: false,
    })
  })
})
