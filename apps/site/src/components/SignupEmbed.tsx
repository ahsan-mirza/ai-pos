import { SIGNUP_EMBED_MESSAGE, SIGNUP_EMBED_PARAM } from "@ai-pos/shared-types";
import { useEffect, useState } from "react";
import { signupUrl } from "../env";

function embedSrc(): string {
  const url = new URL(signupUrl);
  url.searchParams.set(SIGNUP_EMBED_PARAM, "1");
  return url.toString();
}

/** The real signup wizard, framed so Step 1 and every later step stay the portal implementation. */
export function SignupEmbed() {
  const src = embedSrc();
  const origin = new URL(src).origin;
  const [height, setHeight] = useState(720);

  useEffect(() => {
    const onMessage = (event: MessageEvent) => {
      if (event.origin !== origin) return;
      const data = event.data as { type?: string; height?: number } | null;
      if (!data || data.type !== SIGNUP_EMBED_MESSAGE) return;
      if (typeof data.height !== "number" || data.height < 240 || data.height > 4000) return;
      setHeight(Math.ceil(data.height));
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [origin]);

  return (
    <iframe
      title="Create your AxizPOS account"
      src={src}
      style={{ height }}
      className="block w-full bg-white"
      scrolling="no"
    />
  );
}
