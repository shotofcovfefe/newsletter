export default function Footer() {
  return (
    <footer className="w-full px-6 py-8 text-center text-sm text-neutral-500 border-t border-neutral-300">
      &copy; {new Date().getFullYear()} Weekend Picks ·{' '}
      <a href="#" className="underline hover:opacity-80">Privacy</a> ·{' '}
      <a href="#" className="underline hover:opacity-80">Contact</a>
    </footer>
  )
}