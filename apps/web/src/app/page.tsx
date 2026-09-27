import { ApiStatus } from "@/components/api-status";
import { PRODUCT_NAME } from "@/components/app-shell";

export default function HomePage() {
  return (
    <section aria-labelledby="page-title" className="space-y-6">
      <h1 id="page-title" className="text-3xl font-semibold tracking-tight sm:text-4xl">
        {PRODUCT_NAME}
      </h1>
      <p className="text-lg text-muted">Engineering foundation initialized.</p>
      <ApiStatus />
    </section>
  );
}
