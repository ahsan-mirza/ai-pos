import { richPieces } from "./richText.ts";

export function RichText({ text }: { text: string }) {
  const pieces = richPieces(text);
  return (
    <>
      {pieces.map((piece, index) =>
        piece.href ? (
          <a key={index} href={piece.href} className="font-semibold text-primary underline-offset-2 hover:underline">
            {piece.label}
          </a>
        ) : (
          <span key={index}>{piece.text}</span>
        ),
      )}
    </>
  );
}
