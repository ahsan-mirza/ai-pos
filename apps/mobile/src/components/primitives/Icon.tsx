import Svg, { Circle, Path, Rect } from "react-native-svg";

export type IconName = "store" | "user" | "lock" | "eye" | "eyeOff" | "search" | "bell" | "home" | "business" | "inventory" | "finance" | "more";

export function Icon(props: { name: IconName; size?: number; color: string }) {
  const size = props.size ?? 20;
  const stroke = props.color;
  const common = { stroke, strokeWidth: 1.8, strokeLinecap: "round" as const, strokeLinejoin: "round" as const, fill: "none" };
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" accessibilityElementsHidden>
      {props.name === "store" ? (
        <>
          <Path {...common} d="M4 20h16" />
          <Path {...common} d="M6 20V10l6-6 6 6v10" />
          <Path {...common} d="M10 20v-5h4v5" />
        </>
      ) : null}
      {props.name === "user" ? (
        <>
          <Circle {...common} cx="12" cy="8" r="3.2" />
          <Path {...common} d="M5.5 19.5c1.4-3 3.6-4.5 6.5-4.5s5.1 1.5 6.5 4.5" />
        </>
      ) : null}
      {props.name === "lock" ? (
        <>
          <Rect {...common} x="6" y="11" width="12" height="9" rx="2" />
          <Path {...common} d="M8.5 11V8.2a3.5 3.5 0 0 1 7 0V11" />
        </>
      ) : null}
      {props.name === "eye" ? (
        <>
          <Path {...common} d="M2.5 12S6 6.5 12 6.5 21.5 12 21.5 12 18 17.5 12 17.5 2.5 12 2.5 12z" />
          <Circle {...common} cx="12" cy="12" r="2.4" />
        </>
      ) : null}
      {props.name === "eyeOff" ? (
        <>
          <Path {...common} d="M4 5l16 14" />
          <Path {...common} d="M9.2 9.4A3.2 3.2 0 0 0 14.6 14" />
          <Path {...common} d="M7 7.8C4.6 9.3 2.8 12 2.8 12S6.2 17.5 12 17.5c1.4 0 2.7-.3 3.8-.8" />
          <Path {...common} d="M14.8 6.8C18.6 7.8 21.2 12 21.2 12s-.8 1.4-2.2 2.8" />
        </>
      ) : null}
      {props.name === "search" ? (
        <>
          <Circle {...common} cx="11" cy="11" r="6" />
          <Path {...common} d="M16 16l4 4" />
        </>
      ) : null}
      {props.name === "bell" ? (
        <>
          <Path {...common} d="M6 16V11a6 6 0 1 1 12 0v5l1.5 2H4.5L6 16z" />
          <Path {...common} d="M10 19a2 2 0 0 0 4 0" />
        </>
      ) : null}
      {props.name === "home" ? <Path {...common} d="M4 11.5 12 4l8 7.5V20H4z" /> : null}
      {props.name === "business" ? (
        <>
          <Rect {...common} x="4" y="7" width="16" height="13" rx="2" />
          <Path {...common} d="M8 7V5h8v2M9 12h2M13 12h2M9 16h2M13 16h2" />
        </>
      ) : null}
      {props.name === "inventory" ? (
        <>
          <Path {...common} d="M4 8l8-4 8 4-8 4-8-4z" />
          <Path {...common} d="M4 8v8l8 4 8-4V8" />
          <Path {...common} d="M12 12v8" />
        </>
      ) : null}
      {props.name === "finance" ? (
        <>
          <Path {...common} d="M4 18V6M4 18h16" />
          <Path {...common} d="M8 15V11M12 15V8M16 15v-3" />
        </>
      ) : null}
      {props.name === "more" ? (
        <>
          <Circle cx="6" cy="12" r="1.4" fill={stroke} />
          <Circle cx="12" cy="12" r="1.4" fill={stroke} />
          <Circle cx="18" cy="12" r="1.4" fill={stroke} />
        </>
      ) : null}
    </Svg>
  );
}
