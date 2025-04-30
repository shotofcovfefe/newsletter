import './globals.css'
import { Inter, EB_Garamond } from 'next/font/google'
import Header from '@/components/Header'
import Footer from '@/components/Footer'
import FogOverlay from '@/components/FogOverlay'

const inter = Inter({ subsets: ['latin'], variable: '--font-inter' })
const garamond = EB_Garamond({ subsets: ['latin'], variable: '--font-garamond' })

export const metadata = {
  title: 'Weekend Picks',
  description: 'Five cool things to do in London every weekend.',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`dark ${inter.variable} ${garamond.variable}`}>
      <body className="font-sans bg-[#0A0A0A] text-white relative transition-colors duration-300">
        <Header />
        <div className="relative z-10">
          <main>{children}</main>
          <FogOverlay />
        </div>
        <Footer />
      </body>
    </html>
  )
}
