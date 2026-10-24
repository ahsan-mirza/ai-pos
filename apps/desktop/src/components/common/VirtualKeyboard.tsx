import { useState } from "react";
import type { KeyboardLayout } from "../../hooks/useVirtualKeyboard";

const LETTERS = ["qwertyuiop", "asdfghjkl", "zxcvbnm"];
const NUMBERS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"];

function KeyButton({
  label,
  onPress,
  wide = false,
  active = false,
}: {
  label: string;
  onPress: () => void;
  wide?: boolean;
  active?: boolean;
}) {
  return (
    <button
      type="button"
      onMouseDown={(event) => event.preventDefault()}
      onClick={onPress}
      className={`flex h-12 items-center justify-center rounded-lg text-base font-semibold text-slate-100 active:bg-orange-600 ${
        active ? "bg-orange-600" : "bg-slate-800"
      } ${wide ? "min-w-[4.5rem] px-3" : "min-w-10 flex-1"}`}
    >
      {label}
    </button>
  );
}

/** Slides up over the register. Key presses keep focus in the field the cashier was typing into. */
export function VirtualKeyboard({
  layout,
  onKey,
  onHide,
}: {
  layout: KeyboardLayout;
  onKey: (key: string) => void;
  onHide: () => void;
}) {
  const [shifted, setShifted] = useState(false);
  const typeLetter = (letter: string) => {
    onKey(shifted ? letter.toUpperCase() : letter);
    setShifted(false);
  };

  return (
    <div
      data-virtual-keyboard-root
      className="fixed bottom-0 left-0 right-0 z-50 border-t border-slate-700 bg-slate-900 px-2 pb-3 pt-2 shadow-2xl"
      style={{ animation: "ai-pos-keyboard-slide 180ms ease-out" }}
    >
      <style>{"@keyframes ai-pos-keyboard-slide{from{transform:translateY(100%)}to{transform:translateY(0)}}"}</style>
      {layout === "numeric" ? (
        <div className="mx-auto grid w-full max-w-sm grid-cols-3 gap-1.5">
          {["1", "2", "3", "4", "5", "6", "7", "8", "9", ".", "0"].map((key) => (
            <KeyButton key={key} label={key} onPress={() => onKey(key)} />
          ))}
          <KeyButton label="⌫" onPress={() => onKey("backspace")} />
          <KeyButton label="Clear" wide onPress={() => onKey("clear")} />
          <KeyButton label="Enter" wide onPress={() => onKey("enter")} />
          <KeyButton label="Hide" wide onPress={onHide} />
        </div>
      ) : (
        <div className="mx-auto flex w-full max-w-4xl flex-col gap-1.5">
          <div className="flex gap-1">
            {NUMBERS.map((key) => (
              <KeyButton key={key} label={key} onPress={() => onKey(key)} />
            ))}
            <KeyButton label="⌫" wide onPress={() => onKey("backspace")} />
          </div>
          {LETTERS.map((row) => (
            <div key={row} className="flex justify-center gap-1">
              {row.split("").map((letter) => (
                <KeyButton key={letter} label={shifted ? letter.toUpperCase() : letter} onPress={() => typeLetter(letter)} />
              ))}
            </div>
          ))}
          <div className="flex gap-1">
            <KeyButton label="Shift" wide active={shifted} onPress={() => setShifted((current) => !current)} />
            <KeyButton label="space" onPress={() => onKey("space")} />
            <KeyButton label="." onPress={() => onKey(".")} />
            <KeyButton label="-" onPress={() => onKey("-")} />
            <KeyButton label="Enter" wide onPress={() => onKey("enter")} />
            <KeyButton label="Hide" wide onPress={onHide} />
          </div>
        </div>
      )}
    </div>
  );
}
