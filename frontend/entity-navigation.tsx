import * as React from "react";

export type EntityNavigate = (
  page: string,
  params?: Record<string, unknown>,
) => void;

type EntityReferenceProps = {
  entity: "customer" | "vehicle" | "document" | "product" | "supplier";
  id?: string | null;
  kind?: string;
  navigate: EntityNavigate;
  children: React.ReactNode;
  className?: string;
  disabled?: boolean;
};

// Navigation is state-based in both the desktop app and its local preview.
// Keep every reference on the same guarded route transition as the sidebar.
export function EntityReference({
  entity,
  id,
  kind = "invoice",
  navigate,
  children,
  className = "",
  disabled = false,
}: EntityReferenceProps) {
  if (!id) return <>{children}</>;
  const label =
    typeof children === "string" && !children.trim()
      ? {
          customer: "Consultar cliente",
          vehicle: "Consultar vehículo",
          document: "Consultar documento",
          product: "Consultar artículo",
          supplier: "Consultar proveedor",
        }[entity]
      : children;
  return (
    <button
      type="button"
      className={`entity-reference ${className}`.trim()}
      disabled={disabled}
      onClick={(event) => {
        event.stopPropagation();
        if (disabled) return;
        const page = {
          document: "editor",
          product: "catalogue",
          supplier: "suppliers",
          customer: "customer",
          vehicle: "vehicle",
        }[entity];
        navigate(page, {
          id,
          ...(entity === "document" ? { kind } : {}),
        });
      }}
    >
      {label}
    </button>
  );
}
