import { toBlocks } from './format'

/** The API's plain text as paragraphs and bullet lists. They are direct children of the message text, which is where the kit styles them. */
export function Blocks({ text }: { text: string }) {
  return (
    <>
      {toBlocks(text).map((block, i) =>
        block.type === 'ul' ? (
          <ul key={i} className="chat-list">{block.items.map((item, j) => <li key={j}>{item}</li>)}</ul>
        ) : (
          <p key={i}>{block.text}</p>
        ),
      )}
    </>
  )
}
