import { useEffect } from "react";
import { AiMark } from "../../components/ui/AiMark";
import { useAssistant } from "./AssistantProvider";

/** Bookmark for /assistant. The conversation itself lives in the drawer, so this page does not replace the portal. */
export function AssistantPage() {
  const assistant = useAssistant();
  useEffect(() => {
    assistant.openDrawer();
  }, [assistant.openDrawer]);

  return (
    <section className="mx-auto max-w-lg p-6">
      <h1 className="flex items-center gap-2 text-xl font-semibold">
        <AiMark size={18} /> AI Assistant
      </h1>
      <p className="mt-2 text-sm text-charcoal/60">
        The assistant opens beside your work. Closing it leaves this page, your filters, and anything you have not saved exactly as they were.
      </p>
      {assistant.open ? null : (
        <button
          type="button"
          onClick={assistant.openDrawer}
          className="mt-4 rounded-full bg-accent px-4 py-2 text-sm font-semibold text-white hover:bg-accent-hover"
        >
          Open AI Assistant
        </button>
      )}
    </section>
  );
}
