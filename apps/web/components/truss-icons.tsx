import { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement> & {
  size?: number;
};

function SvgIcon({ children, size = 24, ...props }: IconProps) {
  return (
    <svg
      aria-hidden="true"
      className={`truss-icon ${props.className ?? ""}`}
      fill="none"
      height={size}
      viewBox="0 0 24 24"
      width={size}
      {...props}
    >
      {children}
    </svg>
  );
}

export function TrussMark(props: IconProps) {
  return (
    <SvgIcon {...props}>
      <path d="M4.5 19.5 12 4.5l7.5 15z" stroke="currentColor" />
      <path d="M7.5 13.5h9" stroke="currentColor" />
    </SvgIcon>
  );
}

export function FindingBboxIcon(props: IconProps) {
  return (
    <SvgIcon {...props}>
      <path d="M7 4H4v3M17 4h3v3M20 17v3h-3M4 17v3h3" stroke="currentColor" />
      <circle cx="12" cy="12" r="2.25" stroke="currentColor" />
    </SvgIcon>
  );
}

export function RegionSelectIcon(props: IconProps) {
  return (
    <SvgIcon {...props}>
      <path d="M5 7V5h2M17 5h2v2M19 17v2h-2M7 19H5v-2" stroke="currentColor" />
      <path d="M9 5h2M13 5h2M19 9v2M19 13v2M15 19h-2M11 19H9M5 15v-2M5 11V9" stroke="currentColor" />
    </SvgIcon>
  );
}

export function FocusRegionIcon(props: IconProps) {
  return (
    <SvgIcon {...props}>
      <path d="M12 4v4M12 16v4M4 12h4M16 12h4" stroke="currentColor" />
      <path d="M9 9h6v6H9z" stroke="currentColor" />
    </SvgIcon>
  );
}

export function ConfidenceBarsIcon(props: IconProps) {
  return (
    <SvgIcon {...props}>
      <path d="M5 19h14" stroke="currentColor" />
      <path d="M7 15v2M11 12v5M15 8v9M19 5v12" stroke="currentColor" />
    </SvgIcon>
  );
}

export function SheetIcon(props: IconProps) {
  return (
    <SvgIcon {...props}>
      <path d="M6 4h12v16H6z" stroke="currentColor" />
      <path d="M8.5 15.5h7M8.5 17.5h7M14.5 13.5h1" stroke="currentColor" />
    </SvgIcon>
  );
}
