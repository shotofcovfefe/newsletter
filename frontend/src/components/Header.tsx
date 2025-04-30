'use client'
import Link from 'next/link'

export default function Header() {
  return (
    <header className="w-full px-6 py-4 flex justify-center items-center text-sm font-medium border-b border-white/10 bg-black/30 backdrop-blur-md text-white fixed top-0 left-0 z-50">
      <div className="w-full max-w-6xl flex justify-between items-center">
        <Link href="/" className="text-lg font-bold">
          unfog.london
        </Link>
        <nav className="space-x-6">
          <Link href="/about" className="hover:underline">
            About
          </Link>
        </nav>
      </div>
    </header>
  )
}
