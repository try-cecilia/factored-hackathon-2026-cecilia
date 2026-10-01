// The API answers in plain text: dash lines for lists, and numbered options inside one sentence
// ("¿Sobre cuál de tus productos? 1) A (USD); 2) B (USD)"). These helpers give that text structure, and
// fall back to showing it as written when it does not have the expected shape.

export type Block = { type: 'p'; text: string } | { type: 'ul'; items: string[] }

export function toBlocks(text: string): Block[] {
  const blocks: Block[] = []
  for (const line of text.split('\n')) {
    const item = /^\s*[-•]\s+(.*)$/.exec(line)
    const last = blocks.at(-1)
    if (item) {
      if (last?.type === 'ul') last.items.push(item[1])
      else blocks.push({ type: 'ul', items: [item[1]] })
    } else if (line.trim()) {
      blocks.push({ type: 'p', text: line.trim() })
    }
  }
  return blocks
}

export type Options = {
  lead: string
  options: string[]
  tail: string
  // A pending movement is picked by its number (the code resolves it); a product by its name (the model does).
  kind: 'movement' | 'product'
}

/**
 * The numbered options inside a clarification, or null when the text has none. What the options are (`kind`) is not read from
 * the text: the API says it (`choice` on the reply), because the words before the options can be anything, such as an answered
 * list of pending movements ahead of a question about which product. Without it the options are products, answered by name.
 */
export function parseOptions(text: string, kind: Options['kind'] = 'product'): Options | null {
  const first = /(?:^|\s)1\)\s/.exec(text)
  if (!first) return null
  const lead = text.slice(0, first.index).trim()
  const parts = text.slice(first.index + first[0].length).split(/;\s*(?=\d+\)\s)/)
  // The last option runs to the end of the sentence; what follows it is a question to the customer.
  const lastPart = parts.pop() ?? ''
  const cut = /\.\s+(?=[¿¡A-ZÁÉÍÓÚ])/.exec(lastPart)
  parts.push(cut ? lastPart.slice(0, cut.index) : lastPart)
  const tail = cut ? lastPart.slice(cut.index + 1).trim() : ''
  const options = parts.map((part, i) => (i === 0 ? part : part.replace(/^\d+\)\s*/, '')).trim()).filter(Boolean)
  if (options.length < 2) return null
  return { lead, options, tail, kind }
}

// What choosing option n sends as the customer's next message.
export function optionAnswer(parsed: Options, n: number): string {
  if (parsed.kind === 'movement') return String(n + 1)
  return parsed.options[n].replace(/\s*\([A-Z]{3}\)\s*$/, '')
}
