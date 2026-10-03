/**
 * The rounding every written figure shares with eval/check_readme.py (`_fixed`): the shortest decimal form of the number that
 * reads back as the same float (`String`, what Python's `repr` also gives), times 10**shift, rounded half up to `digits`
 * decimals. Decimal arithmetic on that string, never the binary float that `toFixed` rounds: 2.25 → 2.3, 2.55 → 2.6,
 * 2.449999999999 → 2.4, 1.005 → 1.01. Any size (BigInt), and no negative zero: what rounds to zero is written unsigned
 * (-0.01 → 0.0). rounding-cases.json holds the cases both sides test.
 */
export function roundHalfUp(value: number | string, digits: number, shift = 0): string {
  const text = typeof value === 'number' ? String(value) : value
  const match = /^(-?)(\d+)(?:\.(\d+))?(?:e([+-]?\d+))?$/i.exec(text)
  if (!match) throw new Error(`not a decimal number: ${text}`)
  const [, sign, whole, fraction = '', exponent = '0'] = match
  // value = units × 10**power, with every digit of the decimal form in `units`.
  const units = BigInt(whole + fraction)
  const power = Number(exponent) - fraction.length + shift + digits // the power of 10 once scaled to `digits` decimals
  let scaled: bigint
  if (power >= 0) scaled = units * 10n ** BigInt(power)
  else {
    const divisor = 10n ** BigInt(-power)
    scaled = units / divisor + ((units % divisor) * 2n >= divisor ? 1n : 0n)
  }
  const digitsText = scaled.toString().padStart(digits + 1, '0')
  const out = digits ? `${digitsText.slice(0, -digits)}.${digitsText.slice(-digits)}` : digitsText
  return sign && scaled !== 0n ? `-${out}` : out
}

/**
 * The power of ten a scale stands for (100 → 2, 0.001 → −3), read exactly from its decimal text: a 1 with only zeros before or
 * after it, or 1e±n. Anything else (3e-13, 1.3e-12, 0.010000000000000002) is refused, so the rounding stays decimal.
 */
export function powerOfTen(scale: number): number {
  const text = String(scale)
  const exponent = /^1e([+-]?\d+)$/.exec(text)
  if (exponent) return Number(exponent[1])
  const whole = /^1(0*)$/.exec(text)
  if (whole) return whole[1].length
  const fraction = /^0\.(0*)1$/.exec(text)
  if (fraction) return -(fraction[1].length + 1)
  throw new Error(`scale ${text} is not a power of ten`)
}
