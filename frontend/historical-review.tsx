import * as React from "react";
import { api, Button, Confirm, Field, money, Modal, Notice } from "./core.js";
import { Textarea, TextInput } from "./controls.js";
import { Presence, useClosing } from "./overlays.js";

export type HistoricalReview = {
  state: "estimated" | "pending_review" | "verified";
  version: number;
  tax_rate: string | null;
  base_cents: number | null;
  tax_cents: number | null;
  total_cents: number | null;
  issues: { code: string; message: string }[];
  reason: string;
  evidence: string;
  policy: string;
  history?: (HistoricalReview & { action: string; created_at: string })[];
};

const labels = {
  estimated: "Estimada",
  pending_review: "Pendiente de revisión",
  verified: "Contrastada con original",
};

export function HistoricalReviewBadge({ review }: { review: HistoricalReview }) {
  return <span className={`badge historical-review-badge review-${review.state}`}>{labels[review.state]}</span>;
}

export function HistoricalTotal({ total, review }: {
  total: number | null;
  review?: HistoricalReview | null;
}) {
  if (total != null || review?.total_cents == null) return <>{money(total ?? null)}</>;
  return <span className="historical-list-total">
    <span>{money(review.total_cents)}</span>
    <small>{review.state === "verified" ? "Contrastado con original" : "Estimado"}</small>
  </span>;
}

function ReviewAmounts({ review }: { review: HistoricalReview }) {
  const suffix = review.state === "verified" ? "contrastada" : "estimada";
  return <dl className="historical-review-amounts">
    <div><dt>Base {suffix}</dt><dd>{money(review.base_cents)}</dd></div>
    <div><dt>IVA {review.state === "verified" ? "contrastado" : "estimado"}{review.tax_rate != null ? ` (${review.tax_rate} %)` : ""}</dt><dd>{money(review.tax_cents)}</dd></div>
    <div className="historical-review-total"><dt>Total {review.state === "verified" ? "contrastado" : "estimado"}</dt><dd>{money(review.total_cents)}</dd></div>
  </dl>;
}

function ReviewIssues({ review }: { review: HistoricalReview }) {
  if (!review.issues.length) return null;
  return <ul className="historical-review-issues">
    {review.issues.map((issue, index) => <li key={`${issue.code}-${index}`}>{issue.message}</li>)}
  </ul>;
}

export function HistoricalReviewPanel({ identifier, review, disabled = false, onChanged }: {
  identifier: string;
  review: HistoricalReview;
  disabled?: boolean;
  onChanged: (review: HistoricalReview) => void;
}) {
  const [mode, setMode] = React.useState<"adjust" | "reset" | null>(null);
  return <section className="panel padded historical-review-panel" aria-label="Estimación del histórico">
    <h2>Estimación del histórico</h2>
    <HistoricalReviewBadge review={review} />
    <p className="historical-review-copy">
      {review.state === "verified"
        ? "Importes cotejados con el original. La revisión se conserva por separado de los datos importados."
        : "Cálculo orientativo de las líneas conservadas. El tipo propuesto por fecha no acredita el IVA aplicado en el original."}
    </p>
    <ReviewAmounts review={review} />
    <ReviewIssues review={review} />
    <p className="historical-review-copy">Esta revisión no modifica el PDF, los cobros ni los registros fiscales.</p>
    <Button tone="full" disabled={disabled} onClick={() => setMode("adjust")}>Revisar estimación</Button>
    <details className="historical-review-details">
      <summary>Hipótesis y revisiones</summary>
      <p>{review.policy}</p>
      {review.reason && <p><strong>Motivo: </strong>{review.reason}</p>}
      {review.evidence && <p><strong>Evidencia: </strong>{review.evidence}</p>}
      {Boolean(review.history?.length) && <ol className="historical-review-history">
        {review.history!.map(entry => <li key={entry.version}>
          <strong>Revisión {entry.version} · {labels[entry.state]}</strong>
          <span>{entry.tax_rate != null ? `IVA ${entry.tax_rate} % · ` : ""}{money(entry.total_cents)}</span>
          {entry.reason && <p>{entry.reason}</p>}
          {entry.evidence && <p>Evidencia: {entry.evidence}</p>}
        </li>)}
      </ol>}
      {review.version > 0 && <Button disabled={disabled} onClick={() => setMode("reset")}>Restablecer estimación automática</Button>}
    </details>
    <Presence>{mode && <HistoricalReviewForm
      identifier={identifier}
      review={review}
      reset={mode === "reset"}
      onClose={() => setMode(null)}
      onChanged={next => { onChanged(next); setMode(null); }}
    />}</Presence>
  </section>;
}

function HistoricalReviewForm({ identifier, review, reset, onClose, onChanged }: {
  identifier: string;
  review: HistoricalReview;
  reset: boolean;
  onClose: () => void;
  onChanged: (review: HistoricalReview) => void;
}) {
  const [rate, setRate] = React.useState(review.tax_rate ?? "");
  const [reason, setReason] = React.useState("");
  const [evidence, setEvidence] = React.useState("");
  const [verified, setVerified] = React.useState(false);
  const [preview, setPreview] = React.useState<HistoricalReview | null>(null);
  const [calculating, setCalculating] = React.useState(true);
  const [previewError, setPreviewError] = React.useState("");
  const [error, setError] = React.useState("");
  const [conflict, setConflict] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [retry, setRetry] = React.useState(0);
  const [discard, setDiscard] = React.useState<"close" | "reload" | null>(null);
  const sequence = React.useRef(0);
  const saving = React.useRef(false);
  const mounted = React.useRef(true);
  const expectedVersion = React.useRef(review.version);
  const closing = useClosing();
  const dirty = rate !== (review.tax_rate ?? "") || Boolean(reason || evidence || verified);
  const complete = preview != null && preview.issues.length === 0 && preview.base_cents != null && preview.tax_cents != null && preview.total_cents != null;

  React.useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; sequence.current++; };
  }, []);
  React.useEffect(() => {
    const token = ++sequence.current;
    if (closing) return;
    setCalculating(true);
    setPreview(null);
    setPreviewError("");
    const timer = window.setTimeout(() => {
      const taxRate = rate.trim().replace(",", ".");
      api<HistoricalReview>("historical.review_preview", {
        identifier,
        ...(!reset && taxRate ? { tax_rate: taxRate } : {}),
      }).then(next => {
        if (token !== sequence.current || !mounted.current) return;
        if (next.version !== expectedVersion.current) {
          setConflict(true);
          setPreviewError("La revisión ha cambiado en otra ventana. Cierra y actualiza la revisión antes de guardar.");
          return;
        }
        setPreview(next);
      }).catch((failure: Error) => {
        if (token === sequence.current && mounted.current) setPreviewError(failure.message);
      }).finally(() => {
        if (token === sequence.current && mounted.current) setCalculating(false);
      });
    }, 180);
    return () => { window.clearTimeout(timer); sequence.current++; };
  }, [identifier, rate, reset, retry, closing]);
  React.useEffect(() => {
    const beforeUnload = (event: BeforeUnloadEvent) => {
      if (dirty || saving.current) { event.preventDefault(); event.returnValue = ""; }
    };
    window.addEventListener("beforeunload", beforeUnload);
    return () => window.removeEventListener("beforeunload", beforeUnload);
  }, [dirty]);

  function requestClose() {
    if (saving.current) return;
    if (dirty) setDiscard("close");
    else { sequence.current++; onClose(); }
  }
  async function reload() {
    if (saving.current) return;
    saving.current = true;
    setBusy(true);
    setError("");
    try {
      const document = await api<{ historical_review: HistoricalReview | null }>("documents.get", { identifier });
      if (!document.historical_review) throw new Error("Este documento ya no admite revisión histórica. Vuelve al listado para actualizarlo.");
      if (mounted.current) onChanged(document.historical_review);
    } catch (failure: any) {
      if (mounted.current) setError(failure.message);
    } finally {
      saving.current = false;
      if (mounted.current) setBusy(false);
    }
  }
  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (saving.current || calculating || !preview || conflict || !reason.trim()) return;
    if (!reset && (!rate.trim() || (verified && (!complete || !evidence.trim())))) return;
    saving.current = true;
    setBusy(true);
    setError("");
    try {
      const next = await api<HistoricalReview>(reset ? "historical.review_reset" : "historical.review_save", {
        identifier,
        expected_version: expectedVersion.current,
        reason: reason.trim(),
        ...(!reset ? { tax_rate: rate.trim().replace(",", "."), verified, evidence: verified ? evidence.trim() : "" } : {}),
      });
      sequence.current++;
      if (mounted.current) onChanged(next);
    } catch (failure: any) {
      if (mounted.current) {
        setError(failure.message);
        if (failure.code === "conflict") setConflict(true);
      }
    } finally {
      saving.current = false;
      if (mounted.current) setBusy(false);
    }
  }
  return <Modal title={reset ? "Restablecer estimación automática" : "Revisar estimación"} onClose={requestClose}>
    <form className="historical-review-form" onSubmit={save}>
      <p className="dialog-copy">{reset
        ? "Se recuperará la propuesta automática. El motivo y las revisiones anteriores quedarán conservados."
        : "Ajusta la hipótesis de IVA y explica el motivo. Guardar un tipo no confirma que coincida con la factura original."}</p>
      {!reset && <Field label="Tipo de IVA (%)" required hint="Tipos generales habituales: 16 %, 18 % y 21 %. Puedes indicar otro tipo justificado.">
        <TextInput name="historical_tax_rate" inputMode="decimal" autoComplete="off" required value={rate} disabled={busy} onChange={event => {
          sequence.current++;
          setPreview(null);
          setCalculating(true);
          setPreviewError("");
          setVerified(false);
          setRate(event.target.value);
        }} />
      </Field>}
      <div className="historical-preview" aria-busy={calculating}>
        <p className="historical-preview-status" role="status">{calculating ? "Calculando estimación…" : preview ? "Estimación actualizada" : "No se ha podido calcular la estimación"}</p>
        {preview && <><ReviewAmounts review={{ ...preview, state: "estimated" }} /><ReviewIssues review={preview} /><p className="historical-review-copy">{preview.policy}</p></>}
      </div>
      {previewError && <Notice tone="error">{previewError}</Notice>}
      {previewError && !conflict && <Button disabled={busy || calculating} onClick={() => setRetry(value => value + 1)}>Reintentar cálculo</Button>}
      <Field label={reset ? "Motivo del restablecimiento" : "Motivo de la revisión"} required>
        <Textarea name="historical_review_reason" required value={reason} disabled={busy} rows={3} onChange={event => setReason(event.target.value)} />
      </Field>
      {!reset && <div className="historical-verification">
        <label className="historical-verification-check">
          <input type="checkbox" checked={verified} disabled={busy || calculating || !complete || conflict} onChange={event => setVerified(event.target.checked)} />
          <span>He cotejado estos importes con el documento original</span>
        </label>
        <p className="historical-review-copy">Comprueba base, IVA y total. Sólo esta confirmación y una evidencia permiten marcar «Contrastada con original».</p>
        {verified && <Field label="Evidencia del contraste" required hint="Identifica el original consultado y los importes cotejados.">
          <Textarea name="historical_review_evidence" required value={evidence} disabled={busy} rows={3} onChange={event => setEvidence(event.target.value)} />
        </Field>}
      </div>}
      {error && <Notice tone="error">{error}</Notice>}
      {conflict && <Button disabled={busy} onClick={() => dirty ? setDiscard("reload") : void reload()}>Cerrar y actualizar revisión</Button>}
      <div className="form-actions">
        <Button disabled={busy} onClick={requestClose}>Volver</Button>
        <Button type="submit" tone="primary" busy={busy} disabled={calculating || !preview || conflict || !reason.trim() || (!reset && (!rate.trim() || (verified && (!complete || !evidence.trim()))))}>
          {reset ? "Restablecer estimación" : "Guardar revisión"}
        </Button>
      </div>
    </form>
    <Presence>{discard && <Confirm
      title="Revisión sin guardar"
      text="Los cambios de esta revisión aún no se han guardado. Puedes volver para conservarlos o descartarlos."
      confirm={discard === "reload" ? "Descartar y actualizar" : "Descartar cambios"}
      danger
      onClose={() => setDiscard(null)}
      onConfirm={async () => {
        sequence.current++;
        if (discard === "reload") await reload();
        else onClose();
      }}
    />}</Presence>
  </Modal>;
}
