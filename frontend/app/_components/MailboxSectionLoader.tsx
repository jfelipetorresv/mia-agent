"use client";

import { Suspense } from "react";
import MailboxSection from "@/app/_components/MailboxSection";

export default function MailboxSectionLoader() {
  return (
    <Suspense fallback={<p className="text-sm text-muted-foreground">Cargando…</p>}>
      <MailboxSection />
    </Suspense>
  );
}
