import * as React from "react";
import { createPortal } from "react-dom";

const ExitContext = React.createContext(false);
export const useClosing = () => React.useContext(ExitContext);
const duration = () =>
  window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 140;

/** Keep the last rendered dialog alive just long enough to animate its exit. */
export function Presence({ children }: { children: React.ReactNode }) {
  const present = Boolean(children);
  const [retained, setRetained] = React.useState<React.ReactNode>(null);
  const [phase, setPhase] = React.useState({ present, generation: 0 });
  if (phase.present !== present)
    setPhase({ present, generation: phase.generation + (present ? 1 : 0) });
  React.useLayoutEffect(() => {
    if (present) {
      setRetained(children);
      return;
    }
    const timer = window.setTimeout(() => setRetained(null), duration());
    return () => window.clearTimeout(timer);
  }, [children, present]);
  return (
    <ExitContext.Provider value={!present}>
      <React.Fragment key={phase.generation}>
        {present ? children : retained}
      </React.Fragment>
    </ExitContext.Provider>
  );
}

// Shared by dialogs and mobile pickers. Preserve nesting, background inertness and focus.
const layers: HTMLElement[] = [];
const inertBefore = new Map<HTMLElement, boolean>();
const companions = new Map<HTMLElement, HTMLElement>();
let overflowBefore = "";
let returnFocus: HTMLElement | null = null;
let observer: MutationObserver | null = null;
function syncLayers() {
  const top = layers.at(-1);
  for (const node of Array.from(document.body.children)) {
    if (!(node instanceof HTMLElement)) continue;
    if (!inertBefore.has(node)) inertBefore.set(node, node.inert);
    node.inert =
      node !== top &&
      !(companions.has(node) && top?.contains(companions.get(node)!));
  }
}
function mountLayer(node: HTMLElement, previous: HTMLElement | null) {
  if (!layers.length) {
    overflowBefore = document.body.style.overflow;
    returnFocus = previous;
    observer = new MutationObserver(syncLayers);
    observer.observe(document.body, { childList: true });
  }
  layers.push(node);
  document.body.style.overflow = "hidden";
  syncLayers();
  return () => {
    const index = layers.indexOf(node);
    if (index >= 0) layers.splice(index, 1);
    if (layers.length) {
      syncLayers();
      if (previous?.isConnected && layers.at(-1)?.contains(previous))
        previous.focus({ preventScroll: true });
    } else {
      observer?.disconnect();
      observer = null;
      for (const [element, inert] of inertBefore) element.inert = inert;
      inertBefore.clear();
      document.body.style.overflow = overflowBefore;
      const target = returnFocus;
      returnFocus = null;
      queueMicrotask(() => {
        if (!layers.length && target?.isConnected)
          target.focus({ preventScroll: true });
      });
    }
  };
}
const focusable =
  'button:not([disabled]),input:not([disabled]):not([type="hidden"]),select:not([disabled]),textarea:not([disabled]),a[href],[tabindex="0"]';
function trapTab(event: KeyboardEvent, root: HTMLElement) {
  if (event.key !== "Tab") return;
  const items = Array.from(
    root.querySelectorAll<HTMLElement>(focusable),
  ).filter((el) => el.getClientRects().length && el.tabIndex >= 0);
  const first = items[0],
    last = items.at(-1);
  if (!first) {
    event.preventDefault();
    root.focus();
  } else if (
    event.shiftKey &&
    (document.activeElement === first || !root.contains(document.activeElement))
  ) {
    event.preventDefault();
    last?.focus();
  } else if (
    !event.shiftKey &&
    (document.activeElement === last || !root.contains(document.activeElement))
  ) {
    event.preventDefault();
    first.focus();
  }
}
export function CloseButton({
  onClick,
  label = "Cerrar ventana",
}: {
  onClick: () => void;
  label?: string;
}) {
  return (
    <button
      type="button"
      className="button ghost icon-only"
      aria-label={label}
      onClick={onClick}
    >
      <svg
        width="20"
        height="20"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        aria-hidden="true"
      >
        <path d="m6 6 12 12M6 18 18 6" />
      </svg>
    </button>
  );
}
export type ModalProps = React.PropsWithChildren<{
  title: string;
  subtitle?: React.ReactNode;
  onClose: () => void;
  wide?: boolean;
}>;
export function Modal({
  title,
  subtitle,
  children,
  onClose,
  wide = false,
}: ModalProps) {
  const root = React.useRef<HTMLDivElement>(null);
  const close = React.useRef(onClose);
  close.current = onClose;
  const exiting = React.useContext(ExitContext);
  React.useLayoutEffect(() => {
    const el = root.current!;
    el.inert = exiting;
    if (exiting) return;
    const backdrop = el.parentElement!;
    const cleanup = mountLayer(
      backdrop,
      document.activeElement as HTMLElement | null,
    );
    const first =
      el.querySelector<HTMLElement>(
        'input:not([type="hidden"]):not([disabled]), textarea:not([disabled]), [role="combobox"]:not([disabled])',
      ) ?? el.querySelector<HTMLElement>(focusable);
    first?.focus({ preventScroll: true });
    const key = (event: KeyboardEvent) => {
      if (layers.at(-1) !== backdrop || event.defaultPrevented) return;
      if (event.key === "Escape") {
        event.preventDefault();
        close.current();
      }
      trapTab(event, el);
    };
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("keydown", key);
      cleanup();
    };
  }, [exiting]);
  return createPortal(
    <div
      className="modal-backdrop"
      data-state={exiting ? "closing" : "open"}
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !exiting) onClose();
      }}
    >
      <div
        className={"modal " + (wide ? "wide" : "")}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        aria-hidden={exiting || undefined}
        ref={root}
      >
        <header>
          <div>
            <h2>{title}</h2>
            {subtitle && <p>{subtitle}</p>}
          </div>
          <CloseButton onClick={onClose} />
        </header>
        <div className="modal-content">{children}</div>
      </div>
    </div>,
    document.body,
  );
}

export function useCompact() {
  const [compact, setCompact] = React.useState(
    () => window.matchMedia("(max-width: 640px)").matches,
  );
  React.useEffect(() => {
    const media = window.matchMedia("(max-width: 640px)");
    const update = () => setCompact(media.matches);
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);
  return compact;
}
type PopupProps = React.PropsWithChildren<{
  anchor: React.RefObject<HTMLElement>;
  title: string;
  onClose: () => void;
  className?: string;
  focusOnOpen?: boolean;
  dialog?: boolean;
}>;
/** Anchored on desktop, a focus-contained full-screen sheet on small windows. */
export function Popup({
  anchor,
  title,
  onClose,
  className = "",
  children,
  focusOnOpen = true,
  dialog = false,
}: PopupProps) {
  const root = React.useRef<HTMLDivElement>(null);
  const close = React.useRef(onClose);
  close.current = onClose;
  const compact = useCompact();
  const exiting = React.useContext(ExitContext);
  const [position, setPosition] = React.useState<React.CSSProperties>({
    visibility: "hidden",
  });
  React.useLayoutEffect(() => {
    const el = root.current!;
    el.inert = exiting;
    if (exiting) return;
    const source = anchor.current;
    const layer = el.parentElement!;
    // Pickers are modal even when anchored, except input-owned autocomplete lists.
    const modal = compact || focusOnOpen;
    if (!modal && source) {
      companions.set(layer, source);
      if (layers.length) syncLayers();
    }
    const focusTarget = source?.matches("input,button")
      ? source
      : (source?.querySelector<HTMLElement>("input,button") ?? source);
    const cleanup = modal ? mountLayer(layer, focusTarget) : undefined;
    const place = () => {
      if (compact || !source) {
        setPosition({});
        return;
      }
      const rect = source.getBoundingClientRect();
      const width = Math.min(
        Math.max(
          rect.width,
          parseFloat(getComputedStyle(el).minWidth) || 0,
          300,
        ),
        window.innerWidth - 24,
      );
      const below = window.innerHeight - rect.bottom - 12;
      const above = rect.top - 12;
      const upwards = below < Math.min(el.scrollHeight, 340) && above > below;
      setPosition({
        width,
        left: Math.min(Math.max(12, rect.left), window.innerWidth - width - 12),
        ...(upwards
          ? { bottom: window.innerHeight - rect.top + 6 }
          : { top: rect.bottom + 6 }),
        maxHeight: Math.max(100, upwards ? above - 6 : below - 6),
      });
    };
    place();
    const resize = new ResizeObserver(place);
    if (source) resize.observe(source);
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    const outside = (event: PointerEvent) => {
      if (
        !el.contains(event.target as Node) &&
        !source?.contains(event.target as Node)
      )
        close.current();
    };
    const key = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopImmediatePropagation();
        close.current();
      }
      if (modal) trapTab(event, el);
    };
    document.addEventListener("pointerdown", outside, true);
    document.addEventListener("keydown", key, true);
    return () => {
      resize.disconnect();
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
      document.removeEventListener("pointerdown", outside, true);
      document.removeEventListener("keydown", key, true);
      companions.delete(layer);
      cleanup?.();
    };
  }, [anchor, compact, focusOnOpen, exiting]);
  React.useLayoutEffect(() => {
    if (
      exiting ||
      position.visibility === "hidden" ||
      (!focusOnOpen && !compact)
    )
      return;
    const el = root.current!;
    const target =
      el.querySelector<HTMLElement>("[data-autofocus]:not([disabled])") ??
      Array.from(el.querySelectorAll<HTMLElement>(focusable)).find(
        (item) => item.getClientRects().length,
      );
    target?.focus({ preventScroll: true });
  }, [position.visibility, focusOnOpen, compact, exiting]);
  return createPortal(
    <div
      className={"picker-layer " + (compact ? "compact" : "")}
      data-state={exiting ? "closing" : "open"}
    >
      <div
        ref={root}
        className={"picker-panel " + className}
        style={position}
        role={compact || dialog ? "dialog" : undefined}
        aria-modal={compact || dialog ? true : undefined}
        aria-label={
          compact || dialog
            ? dialog
              ? "Calendario: " + title
              : title
            : undefined
        }
        aria-hidden={exiting || undefined}
      >
        <header className="picker-mobile-header">
          <h2>{title}</h2>
          <CloseButton label="Cerrar selector" onClick={onClose} />
        </header>
        {children}
      </div>
    </div>,
    document.body,
  );
}
