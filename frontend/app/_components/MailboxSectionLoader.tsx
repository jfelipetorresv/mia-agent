"use client";

import { Suspense } from "react";
import MailboxSection from "@/app/_components/MailboxSection";

export default function MailboxSectionLoader() {
  return (
    <Suspense fallback={<p className="text-sm text-gray-400">Cargando…</p>}>
      <MailboxSection />
    </Suspense>
  );
}
