// app/layout.tsx
import './globals.css'
import { Inter, EB_Garamond } from 'next/font/google'
import Header from '@/components/Header' // Ensure this path is correct
import Footer from '@/components/Footer' // Ensure this path is correct

// Initialize fonts
const inter = Inter({ subsets: ['latin'], variable: '--font-inter' })
const garamond = EB_Garamond({ subsets: ['latin'], variable: '--font-garamond' })

// Define metadata for the site
export const metadata = {
  title: 'Unfog London',
  description: 'Curated London events, tailored to your postcode and interests.',
  icons: {
    icon: [
      { url: '/favicon.ico', sizes: 'any' },
      { url: '/favicon-32x32.png', type: 'image/png' }
    ],
    apple: { url: '/apple-touch-icon.png', type: 'image/png' }
  }
}

// Define the RootLayout component
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${garamond.variable}`}>
      <body
        className={
          `font-sans bg-white dark:bg-[#0A0A0A] text-black dark:text-white ` + // These dark: styles will now apply conditionally
          `relative transition-colors duration-300 ` +
          `flex flex-col min-h-screen`
        }
      >
        {/* Site Header */}
        <Header />

        {/* Main content area that grows to fill space */}
        <div className="relative z-10 flex-grow w-full">
          {children} {/* Page content will be rendered here */}
        </div>

        {/* Site Footer */}
        <Footer />
      </body>
    </html>
  )
}