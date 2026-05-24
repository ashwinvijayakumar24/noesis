import { Link } from 'react-router-dom'
import { NoesisLogo } from '../components/ui/NoesisLogo'

export default function NotFound() {
  return (
    <main className="min-h-screen bg-bg-void text-text-primary flex items-center justify-center px-6">
      <section className="w-full max-w-2xl text-center">
        <div className="mb-8 flex justify-center">
          <NoesisLogo size="lg" />
        </div>

        <div className="rounded-xl border border-border-default bg-bg-surface p-8 sm:p-12">
          <p className="mb-3 font-mono text-sm uppercase tracking-widest text-accent-primary">
            404 Not Found
          </p>
          <h1 className="mb-4 font-heading text-4xl font-semibold tracking-tight text-text-primary sm:text-5xl">
            This page is unavailable
          </h1>
          <p className="mx-auto mb-8 max-w-lg text-base leading-relaxed text-text-secondary sm:text-lg">
            Noesis beta access is paused while the product is being reworked. The public home page remains available with the current product information.
          </p>
          <Link
            to="/"
            className="inline-flex items-center justify-center rounded-md border border-accent-primary/40 bg-accent-light px-5 py-3 text-sm font-semibold text-accent-primary transition-colors duration-150 hover:border-accent-primary"
          >
            Back to Home
          </Link>
        </div>
      </section>
    </main>
  )
}
