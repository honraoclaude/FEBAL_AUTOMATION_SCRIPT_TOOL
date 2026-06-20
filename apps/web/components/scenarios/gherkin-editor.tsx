"use client";

/**
 * Gherkin editor (06-UI-SPEC §Design System note + §2 "Gherkin" section).
 *
 * A styled-NATIVE <textarea> — deliberately NOT a vendored shadcn block (the textarea block is
 * NOT added this phase; zero-add constraint). It reuses the exact token classes the vendored
 * input.tsx uses (border-input, focus ring, disabled treatment) rendered as a fixed-min-height,
 * vertically-resizable, monospace code area with an associated <label> "Gherkin" (a11y §).
 *
 * "Save edits" is enabled only when the text differs from the saved value; "Cancel" reverts to
 * the saved text (non-destructive, no confirmation). If the save fails the syntax lint, the
 * parser error renders INLINE above the editor (the parent passes `lintError`) and the text is
 * preserved — never a toast.
 */

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";

interface GherkinEditorProps {
  /** The current (possibly edited) text. */
  value: string;
  /** The last server-saved text — Save enables only when value !== saved. */
  saved: string;
  onChange: (next: string) => void;
  onSave: () => void;
  onCancel: () => void;
  /** True while a save is in flight (disables the controls). */
  saving?: boolean;
  /** An inline syntax-lint error to render above the editor (mono detail), if the save 422'd. */
  lintError?: string | null;
}

export function GherkinEditor({
  value,
  saved,
  onChange,
  onSave,
  onCancel,
  saving = false,
  lintError = null,
}: GherkinEditorProps) {
  const dirty = value !== saved;

  return (
    <div className="flex flex-col gap-2">
      <Label htmlFor="gherkin-editor">Gherkin</Label>

      {lintError ? (
        <div
          role="alert"
          className="flex flex-col gap-1 rounded-md border border-l-2 border-l-[var(--status-fail)] bg-card p-3"
        >
          <p className="text-sm text-[var(--status-fail)]">
            This Gherkin doesn&apos;t parse. Fix the syntax — the parser detail is below.
          </p>
          <pre className="overflow-x-auto font-mono text-xs text-muted-foreground">
            {lintError}
          </pre>
        </div>
      ) : null}

      <textarea
        id="gherkin-editor"
        aria-label="Gherkin"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={saving}
        spellCheck={false}
        className={
          "min-h-[20rem] w-full resize-y rounded-md border border-input bg-input/30 px-3 py-2 " +
          "font-mono text-sm text-foreground outline-none transition-[color,box-shadow] " +
          "placeholder:text-muted-foreground " +
          "focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 " +
          "disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50"
        }
      />

      <div className="flex items-center gap-2">
        <Button variant="outline" onClick={onSave} disabled={!dirty || saving}>
          Save edits
        </Button>
        <Button
          variant="ghost"
          onClick={onCancel}
          disabled={!dirty || saving}
        >
          Cancel
        </Button>
      </div>
    </div>
  );
}
